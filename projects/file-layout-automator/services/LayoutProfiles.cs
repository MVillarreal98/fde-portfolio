using DocumentLayoutAutomator.Models;
using System.Collections.Generic;

namespace DocumentLayoutAutomator.Services;

/// <summary>
/// The two built-in layouts, encoded once in code. The specs are synthetic
/// (documented field by field in the README), not a partner's real layout.
/// Deterministic: same source file always produces the exact same output.
/// </summary>
public static class LayoutProfiles
{
    /// <summary>
    /// Deposit guide: fixed-width control record for a deposit report.
    /// 31 characters per line.
    /// </summary>
    public static readonly LayoutProfile DepositGuide =
        new()
        {
            Name = "Guía Depósito",
            OutputSlug = "deposit_guide",
            Description = "Guía de depósito, 31 posiciones: TIPO(3) MON(3) IMP(9,0-pad) REF(12) TDA(4,0-pad)",
            Columns = new List<ColumnMapping>
            {
                new()
                {
                    TargetField = "tipo_registro", SourceColumn = "record_type",
                    Required = false, DefaultIfEmpty = "PKG", FixedWidth = 3,
                    ValidationPattern = "PKG",
                    FormatHint = "tipo de registro PKG",
                },
                new()
                {
                    TargetField = "moneda", SourceColumn = "currency",
                    Required = true, FixedWidth = 3,
                    ValidationPattern = "[A-Z]{3}",
                    FormatHint = "código de moneda de 3 letras, p. ej. MXN",
                },
                new()
                {
                    TargetField = "importe", SourceColumn = "amount",
                    Required = true, FixedWidth = 9, ZeroPad = true,
                    ValidationPattern = @"[0-9]+\.[0-9]{2}",
                    FormatHint = "importe con punto y 2 decimales, p. ej. 48.50",
                },
                new()
                {
                    TargetField = "referencia", SourceColumn = "reference",
                    Required = true, FixedWidth = 12,
                    ValidationPattern = "[0-9]{1,12}",
                    FormatHint = "referencia numérica de 1 a 12 dígitos",
                },
                new()
                {
                    TargetField = "tienda", SourceColumn = "store_id",
                    Required = true, FixedWidth = 4, ZeroPad = true,
                    ValidationPattern = "[0-9]{1,4}",
                    FormatHint = "número de tienda de 1 a 4 dígitos",
                },
            },
        };

    /// <summary>
    /// Carrier ASN head record: per-store packing totals for a carrier.
    /// 27 characters per line.
    /// </summary>
    public static readonly LayoutProfile CarrierASN =
        new()
        {
            Name = "Carrier ASN",
            OutputSlug = "carrier_asn",
            Description = "ASN transportista, 27 posiciones: TDA(4,0-pad) CAJAS(3,0-pad) KGS(8,0-pad) FECHA(8,yyyyMMdd) ALM(4)",
            Columns = new List<ColumnMapping>
            {
                new()
                {
                    TargetField = "store", SourceColumn = "store_id",
                    Required = true, FixedWidth = 4, ZeroPad = true,
                    ValidationPattern = "[0-9]{1,4}",
                    FormatHint = "número de tienda de 1 a 4 dígitos",
                },
                new()
                {
                    TargetField = "boxes", SourceColumn = "boxes",
                    Required = true, FixedWidth = 3, ZeroPad = true,
                    ValidationPattern = "[0-9]+",
                    FormatHint = "número entero de cajas",
                },
                new()
                {
                    TargetField = "kilos", SourceColumn = "weight_kg",
                    Required = true, FixedWidth = 8, ZeroPad = true,
                    ValidationPattern = @"[0-9]+\.[0-9]{2}",
                    FormatHint = "peso en kg con punto y 2 decimales, p. ej. 42.10",
                },
                new()
                {
                    TargetField = "ship_date", SourceColumn = "ship_date",
                    Required = true, FixedWidth = 8,
                    InputDateFormat = "yyyy-MM-dd", OutputDateFormat = "yyyyMMdd",
                },
                new()
                {
                    TargetField = "warehouse", SourceColumn = "warehouse",
                    Required = false, DefaultIfEmpty = "MX01", FixedWidth = 4,
                },
            },
        };
}
