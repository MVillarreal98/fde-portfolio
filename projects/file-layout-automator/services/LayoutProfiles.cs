using DocumentLayoutAutomator.Models;
using System.Collections.Generic;

namespace DocumentLayoutAutomator.Services;

/// <summary>
/// The two layouts operators built by hand, now encoded once and reviewed.
/// Deterministic: same source file always produces the exact same output.
/// </summary>
public static class LayoutProfiles
{
    /// <summary>
    /// OXXO-style deposit guide: fixed-width control record for the deposit
    /// report the reconciliation feed consumes.
    /// </summary>
    public static LayoutProfile DepositGuide =
        new()
        {
            Name = "Guía Depósito",
            Description = "Guía de depósito de ancho fijo: PKG(3) CLV(2) IMP(9,0-pad) REF(12) TDA(4)",
            Columns = new List<ColumnMapping>
            {
                new()
                {
                    TargetField = "tipo_registro", SourceColumn = "record_type",
                    Required = false, DefaultIfEmpty = "PKG", FixedWidth = 3,
                },
                new()
                {
                    TargetField = "moneda", SourceColumn = "currency",
                    Required = true, FixedWidth = 2,
                },
                new()
                {
                    TargetField = "importe", SourceColumn = "amount",
                    Required = true, FixedWidth = 9, PadDirection = "left",
                    ZeroPad = true,
                    ValidationPattern = @"^\d+(\.\d{2})?$",
                },
                new()
                {
                    TargetField = "referencia", SourceColumn = "reference",
                    Required = true, FixedWidth = 12,
                    ValidationPattern = @"^\d{1,12}$",
                },
                new()
                {
                    TargetField = "tienda", SourceColumn = "store_id",
                    Required = true, FixedWidth = 4, PadDirection = "left",
                    ZeroPad = true,
                    ValidationPattern = @"^\d{1,4}$",
                },
            },
        };

    /// <summary>
    /// Carrier ASN head record: ships per-store packing totals the carrier's
    /// web portal used to be fed by hand.
    /// </summary>
    public static LayoutProfile CarrierASN =
        new()
        {
            Name = "Carrier ASN",
            Description = "ASN transportista: TDA(4) CAJAS(3) FKGS(8) FECHA(8) CET-2 prefijo",
            Columns = new List<ColumnMapping>
            {
                new()
                {
                    TargetField = "store", SourceColumn = "store_id",
                    Required = true, FixedWidth = 4, ZeroPad = true,
                    ValidationPattern = @"^\d{1,4}$",
                },
                new()
                {
                    TargetField = "boxes", SourceColumn = "boxes",
                    Required = true, FixedWidth = 3, ZeroPad = true,
                    ValidationPattern = @"^\d+$",
                },
                new()
                {
                    TargetField = "kilos", SourceColumn = "weight_kg",
                    Required = true, FixedWidth = 8, DefaultIfEmpty = "0",
                    ValidationPattern = @"^\d+(\.\d+)?$",
                },
                new()
                {
                    TargetField = "ship_date", SourceColumn = "ship_date",
                    Required = true, FixedWidth = 8,
                    ValidationPattern = @"^\d{4}-\d{2}-\d{2}$",
                },
                new()
                {
                    TargetField = "warehouse", SourceColumn = "warehouse",
                    Required = false, DefaultIfEmpty = "MX01", FixedWidth = 4,
                },
            },
        };
}
