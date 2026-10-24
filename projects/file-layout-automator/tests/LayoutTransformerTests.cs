using DocumentLayoutAutomator.Models;
using DocumentLayoutAutomator.Services;
using Xunit;

namespace LayoutTransformerTests;

public class LayoutTransformerTests
{
    private static readonly string[] DemoLines =
    {
        "record_type,currency,amount,reference,store_id,notes",
        "PKG,MXN,48.50,1203914,101,\"regular deposit\"",
        "PKG,MXN,120.00,1203915,102,",
        "PKG,MXN,,1203918,101,\"missing required amount\"",
        "PKG,MXN,ABC.99,1203919,102,\"amount fails regex\"",
        "PKG,MXN,990.00,1203971,10101,\"store id too long\"",
    };

    private const string DepositHeader = "record_type,currency,amount,reference,store_id,notes";
    private const string CarrierHeader = "store_id,boxes,weight_kg,ship_date,warehouse";

    private static LayoutProfile Profile(string slug) =>
        new[] { LayoutProfiles.DepositGuide, LayoutProfiles.CarrierASN }.Single(p => p.OutputSlug == slug);

    // Valid inputs per profile, including values that fill each field exactly.
    public static TheoryData<string, string[]> ValidInputs => new()
    {
        {
            "deposit_guide", new[]
            {
                DepositHeader,
                "PKG,MXN,48.50,1203914,101,",
                ",USD,999999.99,123456789012,9999,\"record type defaulted, every field full\"",
                "PKG,MXN,0.01,1,1,",
            }
        },
        {
            "carrier_asn", new[]
            {
                CarrierHeader,
                "12,3,42.10,2025-03-04,",
                "9999,999,99999.99,2024-02-29,MX02",
                "1,0,0.00,1999-12-31,A",
            }
        },
    };

    [Theory]
    [MemberData(nameof(ValidInputs))]
    public void Every_accepted_line_is_exactly_the_sum_of_the_field_widths(string slug, string[] lines)
    {
        var profile = Profile(slug);
        var result = LayoutTransformer.Transform(lines, profile);

        Assert.Empty(result.Errors);
        Assert.Equal(lines.Length - 1, result.AcceptedRows);
        Assert.Equal(profile.Columns.Sum(c => c.FixedWidth), profile.RecordWidth);
        Assert.All(result.OutputLines, l => Assert.Equal(profile.RecordWidth, l.Length));
    }

    [Fact]
    public void Profiles_declare_the_documented_record_widths()
    {
        Assert.Equal(31, LayoutProfiles.DepositGuide.RecordWidth);   // 3+3+9+12+4
        Assert.Equal(27, LayoutProfiles.CarrierASN.RecordWidth);     // 4+3+8+8+4
    }

    [Fact]
    public void Valid_rows_match_the_fixed_width_layout()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        Assert.Equal(2, result.AcceptedRows);
        // PKG(3) + MXN(3) + zero-padded amount(9) + reference(12) + zero-padded store(4)
        Assert.Equal("PKGMXN000048.501203914     0101", result.OutputLines[0]);
        Assert.Equal("PKGMXN000120.001203915     0102", result.OutputLines[1]);
    }

    [Fact]
    public void Carrier_profile_converts_the_date_and_defaults_empty_optional_warehouse()
    {
        var lines = new[] { CarrierHeader, "12,3,42.10,2025-03-04," };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.CarrierASN);

        Assert.Equal(1, result.AcceptedRows);
        // store(4) + boxes(3) + kilos(8) + yyyyMMdd(8) + warehouse(4)
        Assert.Equal("001200300042.1020250304MX01", result.OutputLines[0]);
    }

    [Fact]
    public void Missing_required_cell_rejects_the_row()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        var e = Assert.Single(result.Errors, e => e.Line == 4 && e.Field == "importe");
        Assert.Contains("vacío y requerido", e.Reason);
        Assert.Equal(3, result.RejectedRows);
    }

    [Fact]
    public void Regex_failures_report_the_field_and_offending_value_in_plain_language()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        var e = Assert.Single(result.Errors, e => e.Line == 5 && e.Field == "importe");
        Assert.Contains("ABC.99", e.Reason);
        Assert.Contains("no cumple formato", e.Reason);
        Assert.Contains("2 decimales", e.Reason);
        Assert.DoesNotContain("[0-9]", e.Reason);                     // no raw regex for the operator
    }

    [Fact]
    public void Store_id_longer_than_its_field_is_rejected_not_truncated()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        Assert.Contains(result.Errors, e => e.Field == "tienda" && e.Line == 6);
        Assert.DoesNotContain(result.OutputLines, l => l.Contains("1203971"));   // the row is not emitted at all
    }

    [Theory]
    [InlineData("deposit_guide", DepositHeader, "PKG,MXN,1234567.89,1203914,101,", "importe", 9)]
    [InlineData("carrier_asn", CarrierHeader, "12,1234,42.10,2025-03-04,", "boxes", 3)]
    [InlineData("carrier_asn", CarrierHeader, "12,3,123456.00,2025-03-04,", "kilos", 8)]
    [InlineData("carrier_asn", CarrierHeader, "12,3,42.10,2025-03-04,MX001", "warehouse", 4)]
    public void Value_longer_than_its_field_rejects_the_row_instead_of_overflowing(
        string slug, string header, string row, string field, int width)
    {
        var result = LayoutTransformer.Transform(new[] { header, row }, Profile(slug));

        Assert.Empty(result.OutputLines);
        Assert.Equal(1, result.RejectedRows);
        var e = Assert.Single(result.Errors);
        Assert.Equal(field, e.Field);
        Assert.Contains($"excede el ancho fijo de {width} caracteres", e.Reason);
    }

    [Theory]
    [InlineData("PSKG")]
    [InlineData("ABC")]
    [InlineData("pkg")]
    public void Record_type_other_than_PKG_is_rejected(string recordType)
    {
        var lines = new[] { DepositHeader, $"{recordType},MXN,60.25,1203916,103," };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.DepositGuide);

        Assert.Empty(result.OutputLines);
        var e = Assert.Single(result.Errors);
        Assert.Equal("tipo_registro", e.Field);
        Assert.Contains(recordType, e.Reason);
    }

    [Fact]
    public void Empty_record_type_defaults_to_PKG()
    {
        var lines = new[] { DepositHeader, ",MXN,60.25,1203916,103," };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.DepositGuide);

        Assert.Equal("PKGMXN000060.251203916     0103", Assert.Single(result.OutputLines));
    }

    [Theory]
    [InlineData("2025-02-30")]      // not a real day
    [InlineData("2025-13-01")]      // not a real month
    [InlineData("2023-02-29")]      // not a leap year
    [InlineData("20250304")]        // already compact: wrong input format
    [InlineData("04/03/2025")]
    public void Ship_date_must_be_a_real_date_in_the_input_format(string shipDate)
    {
        var lines = new[] { CarrierHeader, $"12,3,42.10,{shipDate}," };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.CarrierASN);

        Assert.Empty(result.OutputLines);
        var e = Assert.Single(result.Errors);
        Assert.Equal("ship_date", e.Field);
        Assert.Contains("no es una fecha válida con formato yyyy-MM-dd", e.Reason);
    }

    [Fact]
    public void Leap_day_is_written_as_yyyyMMdd()
    {
        var lines = new[] { CarrierHeader, "12,3,42.10,2024-02-29,MX01" };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.CarrierASN);

        Assert.Equal("20240229", Assert.Single(result.OutputLines).Substring(15, 8));
    }

    [Theory]
    [InlineData("602")]
    [InlineData("602.5")]
    [InlineData("602.500")]
    [InlineData("-602.50")]
    public void Amount_needs_exactly_two_decimals_so_it_has_one_representation(string amount)
    {
        var lines = new[] { DepositHeader, $"PKG,MXN,{amount},1203917,104," };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.DepositGuide);

        Assert.Empty(result.OutputLines);
        Assert.Equal("importe", Assert.Single(result.Errors).Field);
    }

    [Theory]
    [InlineData("PKG,MXÑ,48.50,1203914,101,", "moneda")]
    [InlineData("PKG,MXN,４８.５０,1203914,101,", "importe")]           // full-width digits
    public void Non_ascii_values_are_rejected_instead_of_written_as_question_marks(string row, string field)
    {
        var result = LayoutTransformer.Transform(new[] { DepositHeader, row }, LayoutProfiles.DepositGuide);

        Assert.Empty(result.OutputLines);
        var e = Assert.Single(result.Errors);
        Assert.Equal(field, e.Field);
        Assert.Contains("no ASCII", e.Reason);
    }

    [Fact]
    public void RejectedRows_counts_distinct_rows_not_errors()
    {
        var lines = new[]
        {
            DepositHeader,
            "PKG,MXN,,1203918,10101,\"two problems in one row\"",
            "PKG,XX,48.50,1203919,102,\"one problem\"",
            "PKG,MXN,48.50,1203920,103,",
        };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.DepositGuide);

        Assert.Equal(3, result.Errors.Count);
        Assert.Equal(2, result.Errors.Count(e => e.Line == 2));
        Assert.Equal(2, result.RejectedRows);
        Assert.Equal(1, result.AcceptedRows);
    }

    [Fact]
    public void Blank_lines_are_skipped_and_quoted_cells_keep_commas_and_quotes()
    {
        var lines = new[]
        {
            "notes,record_type,currency,amount,reference,store_id",   // columns in another order
            "",
            " , , , , , ",
            "\"note, with comma and \"\"quotes\"\"\",PKG,MXN,48.50,1203914,101",
        };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.DepositGuide);

        Assert.Empty(result.Errors);
        Assert.Equal("PKGMXN000048.501203914     0101", Assert.Single(result.OutputLines));
    }

    [Fact]
    public void Summary_without_output_path_says_no_file_was_generated()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);
        var summary = LayoutTransformer.BuildSummary(result, null);

        Assert.Contains("Filas rechazadas: 3", summary);
        Assert.Contains("Archivo generado: ninguno", summary);
        Assert.Contains("Línea 6 — tienda:", summary);
    }
}
