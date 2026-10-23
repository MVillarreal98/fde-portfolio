Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class NativeW
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
'@

$proc = Get-Process DocumentLayoutAutomator -ErrorAction Stop
$h = $proc.MainWindowHandle
if ($h -eq [IntPtr]::Zero) { throw "sin MainWindowHandle; ¿la ventana está oculta/cerrada?" }

# Restore minimized windows first: GetWindowRect of iconic windows is meaningless.
if ([NativeW]::IsIconic($h)) { [NativeW]::ShowWindow($h, 9) | Out-Null }   # SW_RESTORE
Start-Sleep -Milliseconds 500

$rect = New-Object NativeW+RECT
[NativeW]::GetWindowRect($h, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left
$hgt = $rect.Bottom - $rect.Top
if ($w -le 0 -or $hgt -le 0) { throw "ventana con rectangulo invalido" }

# PW_RENDERFULLCONTENT (2): renders DirectX/WPF even if the window is occluded.
$bmp = New-Object System.Drawing.Bitmap $w, $hgt
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [NativeW]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
if (-not $ok) { throw "PrintWindow falló" }

New-Item -ItemType Directory -Force docs\screenshots | Out-Null
$bmp.Save("$PWD\docs\screenshots\app.png")
$g.Dispose()
$bmp.Dispose()
Write-Output "ventana capturada (oculta) $w x $hgt title='$($proc.MainWindowTitle)'"
