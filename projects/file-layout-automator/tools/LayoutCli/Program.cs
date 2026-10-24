using System.Text;

using DocumentLayoutAutomator.Services;

// Console entry point: same LayoutRunner (engine + fail-closed write) as the
// WPF window. Exit codes: 0 = file generated, 1 = rows rejected (nothing
// written), 2 = usage or file error.
Console.OutputEncoding = Encoding.UTF8;

var profiles = new[] { LayoutProfiles.DepositGuide, LayoutProfiles.CarrierASN };

string? Arg(string name)
{
    var i = Array.FindIndex(args, a => a.Equals(name, StringComparison.OrdinalIgnoreCase));
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}

var source = Arg("--source");
var profile = profiles.FirstOrDefault(p => p.OutputSlug == Arg("--profile"));
if (source is null || profile is null)
{
    Console.Error.WriteLine(
        $"Uso: LayoutCli --profile <{string.Join("|", profiles.Select(p => p.OutputSlug))}> " +
        "--source <archivo.csv> [--out <carpeta>] [--summary <archivo.txt>]");
    return 2;
}

try
{
    var outcome = LayoutRunner.Run(source, profile, Arg("--out") ?? LayoutRunner.DefaultOutputDir(source));

    var summary =
        $"Perfil: {profile.Name} ({profile.OutputSlug}), {profile.RecordWidth} posiciones por línea\n" +
        $"Origen: {source}\n" +
        LayoutTransformer.BuildSummary(outcome.Result, outcome.OutputPath) + "\n";

    Console.Write(summary);
    if (Arg("--summary") is { } summaryPath)
        File.WriteAllText(summaryPath, summary, new UTF8Encoding(false));

    return outcome.OutputPath is null ? 1 : 0;
}
catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
{
    Console.Error.WriteLine($"Error de archivo: {ex.Message}");
    return 2;
}
