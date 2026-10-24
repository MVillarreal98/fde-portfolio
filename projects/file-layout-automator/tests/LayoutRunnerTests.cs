using System.IO;

using DocumentLayoutAutomator.Services;
using Xunit;

namespace LayoutTransformerTests;

/// <summary>
/// The shared run (WPF window and tools/LayoutCli): fail-closed write, stable
/// file names, and the committed sample_output/ being exactly what it produces.
/// </summary>
public sealed class LayoutRunnerTests : IDisposable
{
    private static readonly string Fixtures = Path.Combine(AppContext.BaseDirectory, "fixtures");
    private static readonly string CleanInput = Path.Combine(Fixtures, "data", "sample_input_cleaned.csv");
    private static readonly string BadInput = Path.Combine(Fixtures, "data", "sample_input.csv");

    private readonly string _outDir =
        Path.Combine(Path.GetTempPath(), "layout-runner-tests-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(_outDir)) Directory.Delete(_outDir, recursive: true);
    }

    [Fact]
    public void Rejected_run_writes_nothing()
    {
        var outcome = LayoutRunner.Run(BadInput, LayoutProfiles.DepositGuide, _outDir);

        Assert.Null(outcome.OutputPath);
        Assert.Equal(2, outcome.Result.AcceptedRows);
        Assert.Equal(6, outcome.Result.RejectedRows);
        Assert.False(Directory.Exists(_outDir));
    }

    [Fact]
    public void Clean_run_writes_fixed_width_ascii_file_named_with_the_profile_slug()
    {
        var outcome = LayoutRunner.Run(CleanInput, LayoutProfiles.DepositGuide, _outDir);

        Assert.Equal(Path.Combine(_outDir, "sample_input_cleaned_deposit_guide.txt"), outcome.OutputPath);
        var written = File.ReadAllLines(outcome.OutputPath!);
        Assert.Equal(8, written.Length);
        Assert.All(written, l => Assert.Equal(LayoutProfiles.DepositGuide.RecordWidth, l.Length));
        Assert.All(written, l => Assert.Matches("^[\\x20-\\x7E]+$", l));
    }

    [Fact]
    public void Default_output_dir_is_layout_output_next_to_the_source()
    {
        Assert.Equal(Path.Combine("data", "layout_output"),
            LayoutRunner.DefaultOutputDir(Path.Combine("data", "sample_input.csv")));
        Assert.Equal("sample_input_carrier_asn.txt",
            LayoutRunner.OutputFileName(Path.Combine("data", "sample_input.csv"), LayoutProfiles.CarrierASN));
    }

    [Fact]
    public void Profile_slugs_are_stable_distinct_ascii()
    {
        Assert.Equal("deposit_guide", LayoutProfiles.DepositGuide.OutputSlug);
        Assert.Equal("carrier_asn", LayoutProfiles.CarrierASN.OutputSlug);
        Assert.Matches("^[a-z0-9_]+$", LayoutProfiles.DepositGuide.OutputSlug);
        Assert.Matches("^[a-z0-9_]+$", LayoutProfiles.CarrierASN.OutputSlug);
    }

    // sample_output/ is regenerated with tools/LayoutCli (see README); these
    // tests fail if the committed artifacts drift from what the code produces.
    [Fact]
    public void Committed_success_sample_matches_the_engine()
    {
        var outcome = LayoutRunner.Run(CleanInput, LayoutProfiles.DepositGuide, _outDir);
        var committed = Path.Combine(Fixtures, "sample_output", "sample_input_cleaned_deposit_guide.txt");

        Assert.Equal(File.ReadAllLines(outcome.OutputPath!), File.ReadAllLines(committed));

        var summary = ReadNormalized("run_summary_success.txt");
        var expectedPath = Path.Combine("sample_output", "sample_input_cleaned_deposit_guide.txt");
        Assert.Contains(LayoutTransformer.BuildSummary(outcome.Result, expectedPath), summary);
    }

    [Fact]
    public void Committed_rejected_sample_matches_the_engine()
    {
        var outcome = LayoutRunner.Run(BadInput, LayoutProfiles.DepositGuide, _outDir);

        var summary = ReadNormalized("run_summary_rejected.txt");
        Assert.Contains(LayoutTransformer.BuildSummary(outcome.Result, null), summary);
        Assert.Contains("Archivo generado: ninguno", summary);
        Assert.False(File.Exists(Path.Combine(Fixtures, "sample_output", "sample_input_deposit_guide.txt")));
    }

    [Fact]
    public void Committed_samples_contain_no_absolute_local_paths()
    {
        foreach (var file in Directory.GetFiles(Path.Combine(Fixtures, "sample_output")))
            Assert.DoesNotMatch(@"[A-Za-z]:\\|\\Users\\|/Users/|OneDrive", File.ReadAllText(file));
    }

    private static string ReadNormalized(string name) =>
        File.ReadAllText(Path.Combine(Fixtures, "sample_output", name)).Replace("\r\n", "\n");
}
