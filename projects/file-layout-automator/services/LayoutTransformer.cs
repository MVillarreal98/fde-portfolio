using System.Collections.Generic;
using System.Globalization;
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
/// Every accepted line is exactly <see cref="LayoutProfile.RecordWidth"/> long:
/// a value that does not fit its field rejects the row, it is never truncated.
/// </summary>
public static class LayoutTransformer
{
    public static TransformResult Transform(IEnumerable<string> sourceLines, LayoutProfile profile)
    {
        var errors = new List<TransformError>();
        var output = new List<string>();
        var rejectedRows = 0;

        string[]? headers = null;
        foreach (var (line, index) in sourceLines.Select((l, i) => (l, i)))
        {
            var rowNumber = index + 1;                       // 1-based for the operator
            var cells = SplitCsv(line);

            if (headers is null)
            {
                headers = cells.Select(c => c.Trim()).ToArray();   // header row (1)
                continue;
            }

            if (cells.All(string.IsNullOrWhiteSpace))
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

                var (value, reason) = FormatCell(rule, raw);
                if (reason is not null)
                {
                    lineErrors.Add(new TransformError(rowNumber, rule.TargetField, reason));
                    continue;
                }

                sb.Append(Pad(rule, value!));
            }

            if (lineErrors.Count == 0)
            {
                output.Add(sb.ToString());
            }
            else
            {
                errors.AddRange(lineErrors);
                rejectedRows++;                              // rows, not incidents
            }
        }

        return new TransformResult(output, errors, output.Count, rejectedRows);
    }

    /// <summary>Build the tabular report the operator sees on screen.</summary>
    public static string BuildSummary(TransformResult result, string? outputPath) =>
        $"Filas aceptadas: {result.AcceptedRows}\n" +
        $"Filas rechazadas: {result.RejectedRows}\n" +
        $"Archivo generado: {outputPath ?? "ninguno (no se genera archivo mientras haya filas rechazadas)"}\n" +
        (result.Errors.Count == 0
            ? "Sin incidencias. Layout íntegro."
            : string.Join("\n",
                result.Errors.Select(e => $"Línea {e.Line} — {e.Field}: {e.Reason}")));

    /// <summary>
    /// Validate one cell and produce the value to pad, or the reason it is
    /// rejected. Order: ASCII only → pattern → real date → fits the width.
    /// </summary>
    private static (string? Value, string? Reason) FormatCell(ColumnMapping rule, string raw)
    {
        // The output is ASCII; anything else would be written as '?' in silence.
        if (raw.Any(c => c > '\u007F'))
            return (null, $"contiene caracteres no ASCII (acentos, Ñ, dígitos de ancho completo): \"{raw}\"");

        if (raw.Length == 0)
            return (raw, null);                              // optional field left blank

        if (rule.ValidationPattern is { } pattern &&
            !Regex.IsMatch(raw, $"^(?:{pattern})$"))
            return (null, $"no cumple formato esperado ({rule.FormatHint ?? pattern}): \"{raw}\"");

        var value = raw;
        if (rule.InputDateFormat is { } dateFormat)
        {
            if (!DateTime.TryParseExact(raw, dateFormat, CultureInfo.InvariantCulture,
                    DateTimeStyles.None, out var date))
                return (null, $"no es una fecha válida con formato {dateFormat}: \"{raw}\"");
            value = date.ToString(rule.OutputDateFormat, CultureInfo.InvariantCulture);
        }

        if (value.Length > rule.FixedWidth)
            return (null, $"excede el ancho fijo de {rule.FixedWidth} caracteres: \"{value}\"");

        return (value, null);
    }

    private static string Pad(ColumnMapping rule, string value)
    {
        if (rule.ZeroPad) return value.PadLeft(rule.FixedWidth, '0');

        return rule.PadDirection switch
        {
            "left"  => value.PadLeft(rule.FixedWidth, rule.PadChar),
            _       => value.PadRight(rule.FixedWidth, rule.PadChar),
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
