using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows;

using DocumentLayoutAutomator.Models;
using DocumentLayoutAutomator.Services;

namespace DocumentLayoutAutomator;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        ProfileBox.ItemsSource = new List<LayoutProfile>
        {
            LayoutProfiles.DepositGuide,
            LayoutProfiles.CarrierASN,
        };
        ProfileBox.SelectedIndex = 0;
    }

    private LayoutProfile? SelectedProfile => ProfileBox.SelectedItem as LayoutProfile;

    private void ProfileBox_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (SelectedProfile is { } profile)
            ProfileHint.Text = profile.Description;
    }

    private void BrowseBtn_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Filter = "Archivos de datos|*.csv;*.txt|Todos|*.*",
            Title = "Selecciona el archivo de origen",
        };
        if (dialog.ShowDialog(this) == true)
        {
            SourcePath.Text = dialog.FileName;
            PreviewSource();
        }
    }

    private void PreviewBtn_Click(object sender, RoutedEventArgs e)
        => PreviewSource();

    private void PreviewSource()
    {
        var path = SourcePath.Text.Trim();
        if (!File.Exists(path))
        {
            DiagnosticsBox.Text = $"⚠ El archivo no existe:\n{path}";
            return;
        }
        var lines = File.ReadLines(path).Take(15);
        PreviewBox.Text = string.Join(Environment.NewLine, lines);
        StatusBarText.Text = $"Vista previa cargada: {path}";
    }

    private void TransformBtn_Click(object sender, RoutedEventArgs e)
    {
        var profile = SelectedProfile;
        if (profile is null) return;

        var path = SourcePath.Text.Trim();
        if (!File.Exists(path))
        {
            DiagnosticsBox.Text = $"⚠ El archivo no existe:\n{path}";
            return;
        }

        var result = LayoutTransformer.Transform(File.ReadLines(path), profile);

        if (result.RejectedRows == 0)
        {
            var outputDir = Path.Combine(Path.GetDirectoryName(path)!, "layout_output");
            Directory.CreateDirectory(outputDir);
            var outputPath = Path.Combine(
                outputDir,
                $"{Path.GetFileNameWithoutExtension(path)}_{profile.Name.Replace(' ', '_')}.txt");
            File.WriteAllLines(outputPath, result.OutputLines, Encoding.ASCII);

            DiagnosticsBox.Text = LayoutTransformer.BuildSummary(result, outputPath);
            PreviewBox.Text = string.Join(Environment.NewLine, result.OutputLines.Take(15));
            StatusBarText.Text = $"✅ {result.AcceptedRows} filas transformadas → {outputPath}";
        }
        else
        {
            DiagnosticsBox.Text = LayoutTransformer.BuildSummary(result, "(sin archivo)");
            StatusBarText.Text = $"⚠ Corrige las {result.RejectedRows} incidencias y vuelve a ejecutar.";
        }
    }
}
