using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows;

using DocumentLayoutAutomator.Models;
using DocumentLayoutAutomator.Services;

namespace DocumentLayoutAutomator;

public partial class MainWindow : Window
{
    public MainWindow(string? initialSource = null)
    {
        InitializeComponent();
        ProfileBox.ItemsSource = new List<LayoutProfile>
        {
            LayoutProfiles.DepositGuide,
            LayoutProfiles.CarrierASN,
        };
        ProfileBox.SelectedIndex = 0;

        // Optional demo start (--source): pre-load a source and transform it with
        // the first profile. The scriptable entry point is tools/LayoutCli.
        if (!string.IsNullOrWhiteSpace(initialSource) && File.Exists(initialSource))
        {
            SourcePath.Text = initialSource;
            PreviewSource();
            TransformSource();
        }
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
        try
        {
            PreviewBox.Text = string.Join(Environment.NewLine, File.ReadLines(path).Take(15));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            DiagnosticsBox.Text = $"⚠ No se pudo leer el archivo (¿está abierto en Excel?):\n{ex.Message}";
            return;
        }
        PreviewGroup.Header = "Archivo de origen (primeras líneas)";
        StatusBarText.Text = $"Vista previa cargada: {path}";
    }

    private void TransformBtn_Click(object sender, RoutedEventArgs e)
    {
        TransformSource();
    }

    private void TransformSource()
    {
        var profile = SelectedProfile;
        if (profile is null) return;

        var path = SourcePath.Text.Trim();
        if (!File.Exists(path))
        {
            DiagnosticsBox.Text = $"⚠ El archivo no existe:\n{path}";
            return;
        }

        RunOutcome outcome;
        try
        {
            outcome = LayoutRunner.Run(path, profile, LayoutRunner.DefaultOutputDir(path));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            DiagnosticsBox.Text = $"⚠ No se pudo leer o escribir el archivo (¿está abierto en Excel?):\n{ex.Message}";
            StatusBarText.Text = "⚠ Error de archivo; no se generó nada.";
            return;
        }

        var result = outcome.Result;
        DiagnosticsBox.Text = LayoutTransformer.BuildSummary(result, outcome.OutputPath);

        if (outcome.OutputPath is { } outputPath)
        {
            PreviewGroup.Header = "Archivo generado (primeras líneas)";
            PreviewBox.Text = string.Join(Environment.NewLine, result.OutputLines.Take(15));
            StatusBarText.Text = $"✅ {result.AcceptedRows} filas transformadas → {outputPath}";
        }
        else
        {
            StatusBarText.Text = $"⚠ Corrige las {result.RejectedRows} filas rechazadas y vuelve a ejecutar.";
        }
    }
}
