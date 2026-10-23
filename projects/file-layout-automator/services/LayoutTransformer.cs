using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

using DocumentLayoutAutomator.Models;

namespace DocumentLayoutAutomator.Services;

public sealed record TransformError(int Line, string Field, string Reason);

public sealed record TransformResult(
    IReadOnlyList<string> OutputLines,
    IReadOnlyList<TransformError> Errors,
    int AcceptedRows,
    int RejectedRows);

/// <summary>
/// The deterministic engine: header-aware CSV reader, per-row rule application,
/// and fixed-width line assembly with a per-row error channel (never throws on
/// data problems — reports them so the operator can fix exactly what is wrong).
/// </summary>
public static class LayoutTransformer
{
    public static TransformResult Transform(
        IEnumerable<string> sourceLines, LayoutProfile profile, bool skipHeader = true)
    {
        var materialized = sourceLines.ToList();
        var errors = new List<TransformError>();
        var output = new List<string>();

        string[]? headers = null;
        foreach (var (line, index) in materialized.Select((l, i) => (l, i)))
        {
            var rowNumber = index + 1;                       // 1-based for the operator
            var cells = SplitCsv(line);

            if (headers is null)
            {
                headers = cells.Select(c => c.Trim()).ToArray();   // header row (1)
                if (skipHeader) continue;
            }

            if (cells.All(string.IsNullOrWhiteSpace) || string.IsNullOrWhiteSpace(line))
                continue;                                    // silently drop blanks

            var lineErrors = new List<TransformError>();
            var sb = new StringBuilder();

            foreach (var rule in profile.Columns)
            {
                var raw = Lookup(headers, cells, rule.SourceColumn);

                if (string.IsNullOrWhiteSpace(raw))
                {
                    if (rule.Required)
                    {
                        lineErrors.Add(new TransformError(
                            rowNumber, rule.TargetField, "vacío y requerido"));
                        continue;
                    }
                    raw = rule.DefaultIfEmpty;
                }
                else
                {
                    raw = raw.Trim();
                }

                if (rule.ValidationPattern is { } pattern &&
                    !string.IsNullOrEmpty(raw) &&
                    !Regex.IsMatch(raw, $"^{pattern}$"))
                {
                    lineErrors.Add(new TransformError(
                        rowNumber, rule.TargetField,
                        $"no cumple formato esperado ({pattern}): \"{raw}\""));
                    continue;
                }

                sb.Append(Pad(rule, raw));
            }

            if (lineErrors.Count == 0)
                output.Add(sb.ToString());
            else
                errors.AddRange(lineErrors);
        }

        return new TransformResult(output, errors, output.Count, errors.Count);
    }

    /// <summary>Build the tabular report the operator sees on screen.</summary>
    public static string BuildSummary(TransformResult result, string outputPath) =>
        $"Filas aceptadas: {result.AcceptedRows}\n" +
        $"Filas rechazadas: {result.RejectedRows}\n" +
        $"Archivo generado: {outputPath}\n" +
        (result.Errors.Count == 0
            ? "Sin incidencias. Layout íntegro."
            : string.Join("\n",
                result.Errors.Select(e => $"Línea {e.Line} — {e.Field}: {e.Reason}")));

    private static string Pad(ColumnMapping rule, string raw)
    {
        var width = rule.FixedWidth ?? raw.Length;
        if (rule.ZeroPad) return raw.PadLeft(width, '0');

        return rule.PadDirection switch
        {
            "left"  => raw.PadLeft(width, rule.PadChar),
            _       => raw.PadRight(width, rule.PadChar),
        };
    }

    private static string Lookup(string[] headers, string[] cells, string column)
    {
        var idx = Array.IndexOf(headers, column);
        return idx >= 0 && idx < cells.Length ? cells[idx] : "";
    }

    /// <summary>Minimal CSV split honoring double-quoted cells with commas.</summary>
    private static string[] SplitCsv(string line)
    {
        var result = new List<string>();
        var field = new StringBuilder();
        var inQuotes = false;

        for (var i = 0; i < line.Length; i++)
        {
            var c = line[i];
            switch (c)
            {
                case '"' when inQuotes && i + 1 < line.Length && line[i + 1] == '"':
                    field.Append('"'); i++;
                    break;
                case '"':
                    inQuotes = !inQuotes;
                    break;
                case ',' when !inQuotes:
                    result.Add(field.ToString());
                    field.Clear();
                    break;
                default:
                    field.Append(c);
                    break;
            }
        }
        result.Add(field.ToString());
        return result.ToArray();
    }
}
