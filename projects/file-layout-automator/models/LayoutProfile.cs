using System.Collections.Generic;
using System.Linq;

namespace DocumentLayoutAutomator.Models;

/// <summary>
/// One deterministic cell rule: how to obtain a target layout field from a
/// source column, pad/format it, and decide whether it is acceptable.
/// </summary>
public sealed class ColumnMapping
{
    public string TargetField { get; init; }
    public string SourceColumn { get; init; }
    public bool Required { get; init; } = true;
    public int? FixedWidth { get; init; }
    public string PadDirection { get; init; } = "right";   // right | left
    public char PadChar { get; init; } = ' ';
    /// <summary>Optional regex the final cell must match (money, dates, zips…)</summary>
    public string? ValidationPattern { get; init; }
    /// <summary>Value used when the source cell arrives empty (non-required fields).</summary>
    public string DefaultIfEmpty { get; init; } = "";
    /// <summary>Optional post-transform overrides, e.g. a flag zero-pad.</summary>
    public bool ZeroPad { get; init; }

    public string Apply(string raw) =>
        (ZeroPad ? raw.PadLeft(FixedWidth ?? raw.Length, '0') : raw);
}

public sealed class LayoutProfile
{
    public string Name { get; init; }
    public string Description { get; init; } = "";
    public IReadOnlyList<ColumnMapping> Columns { get; init; }
}
