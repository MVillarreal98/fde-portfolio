using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;

namespace DocumentLayoutAutomator;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var args = e.Args.ToList();
        var sourceIdx = args.FindIndex(a => a.Equals("--source", StringComparison.OrdinalIgnoreCase));
        var source = sourceIdx >= 0 && sourceIdx + 1 < args.Count ? args[sourceIdx + 1] : null;

        var window = new MainWindow(source);
        window.Show();
    }
}
