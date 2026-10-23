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

    [Fact]
    public void Valid_rows_match_the_fixed_width_layout()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        Assert.Equal(2, result.AcceptedRows);
        // PKG + MXN + zero-padded amount + reference + zero-padded store
        Assert.Equal("PKGMXN000048.501203914     0101", result.OutputLines[0]);
        Assert.Equal("PKGMXN000120.001203915     0102", result.OutputLines[1]);
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
    public void Regex_failures_report_the_field_and_offending_value()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        var e = Assert.Single(result.Errors, e => e.Line == 5 && e.Field == "importe");
        Assert.Contains("ABC.99", e.Reason);
        Assert.Contains("no cumple formato", e.Reason);
    }

    [Fact]
    public void Overflowing_zero_pad_field_stays_fixed_width()
    {
        var result = LayoutTransformer.Transform(DemoLines, LayoutProfiles.DepositGuide);

        // 10101 > width 4: only the regex rejects it; no silent truncation.
        Assert.Contains(result.Errors, e => e.Field == "tienda" && e.Line == 6);
        Assert.DoesNotContain(result.OutputLines, l => l.Contains("10101"));
    }

    [Fact]
    public void Carrier_profile_defaults_empty_optional_warehouse()
    {
        var lines = new[]
        {
            "store_id,boxes,weight_kg,ship_date,warehouse",
            "12,3,42.1,2025-03-04,",
        };
        var result = LayoutTransformer.Transform(lines, LayoutProfiles.CarrierASN);

        Assert.Equal(1, result.AcceptedRows);
        Assert.Equal("001200342.1    2025-03-04MX01", result.OutputLines[0]);
    }
}
