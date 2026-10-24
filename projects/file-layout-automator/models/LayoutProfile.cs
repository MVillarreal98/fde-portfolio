using System.Collections.Generic;
using System.Linq;

namespace DocumentLayoutAutomator.Models;

/// <summary>
/// One deterministic cell rule: how to obtain a target layout field from a
/// source column, pad/format it, and decide whether it is acceptable.
/// </summary>
public sealed class ColumnMapping
{
    public required string TargetField { get; init; }
    public required string SourceColumn { get; init; }
    public bool Required { get; init; } = true;
    /// <summary>Exact width of the field in the output line. A longer value rejects the row.</summary>
    public required int FixedWidth { get; init; }
    public string PadDirection { get; init; } = "right";   // right | left
    public char PadChar { get; init; } = ' ';
    /// <summary>Optional regex the whole cell must match (money, codes, ids…), without ^/$.</summary>
    public string? ValidationPattern { get; init; }
    /// <summary>Plain-language description of ValidationPattern shown to the operator.</summary>
    public string? FormatHint { get; init; }
    /// <summary>When set, the cell must be a real calendar date in this format; it is re-emitted as OutputDateFormat.</summary>
    public string? InputDateFormat { get; init; }
    public string OutputDateFormat { get; init; } = "yyyyMMdd";
    /// <summary>Value used when the source cell arrives empty (non-required fields).</summary>
    public string DefaultIfEmpty { get; init; } = "";
    /// <summary>Left-pad with '0' instead of PadChar/PadDirection (numeric fields).</summary>
    public bool ZeroPad { get; init; }
}

public sealed class LayoutProfile
{
    public required string Name { get; init; }
    /// <summary>Stable ASCII slug used in output file names (e.g. "deposit_guide").</summary>
    public required string OutputSlug { get; init; }
    public string Description { get; init; } = "";
    public required IReadOnlyList<ColumnMapping> Columns { get; init; }

    /// <summary>Length every output line must have: the sum of the column widths.</summary>
    public int RecordWidth => Columns.Sum(c => c.FixedWidth);
}
