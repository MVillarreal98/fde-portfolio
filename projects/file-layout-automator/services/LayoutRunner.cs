using System.IO;
using System.Text;

using DocumentLayoutAutomator.Models;

namespace DocumentLayoutAutomator.Services;

public sealed record RunOutcome(TransformResult Result, string? OutputPath);

/// <summary>
/// One end-to-end run shared by the WPF window and the console tool, so both
/// produce the same artifact: read the source, transform, and write the
/// fixed-width file only when no row was rejected (fail-closed).
/// IO problems (locked or missing file) surface as exceptions to the caller.
/// </summary>
public static class LayoutRunner
{
    /// <summary>Default destination: a layout_output folder next to the source.</summary>
    public static string DefaultOutputDir(string sourcePath) =>
        Path.Combine(Path.GetDirectoryName(sourcePath) ?? "", "layout_output");

    /// <summary>"&lt;source name&gt;_&lt;profile slug&gt;.txt", ASCII and stable.</summary>
    public static string OutputFileName(string sourcePath, LayoutProfile profile) =>
        $"{Path.GetFileNameWithoutExtension(sourcePath)}_{profile.OutputSlug}.txt";

    public static RunOutcome Run(string sourcePath, LayoutProfile profile, string outputDir)
    {
        var result = LayoutTransformer.Transform(File.ReadLines(sourcePath), profile);
        if (result.RejectedRows > 0)
            return new RunOutcome(result, null);             // nothing written

        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, OutputFileName(sourcePath, profile));
        File.WriteAllLines(outputPath, result.OutputLines, Encoding.ASCII);
        return new RunOutcome(result, outputPath);
    }
}
