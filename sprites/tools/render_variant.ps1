param(
    [Parameter(Mandatory)] [string]$Name,
    [string]$Parts = 'none',          # folder with upscaled parts, or 'none' = original pack state
    [string]$Filter = 'nearest',      # beetle_psx_hw_filter value
    [string]$Adaptive = 'disabled'    # beetle_psx_hw_adaptive_smoothing
)
# Renders the user's F2 save state with one sprite variant and saves screenshots to scratch\variants\<Name>.
$ErrorActionPreference = 'Stop'
$s    = $PSScriptRoot
$pack = '<DATA_DRIVE>\Xenogears (USA) (Disc 1)\Xenogears (USA)-texture-replacements'
$bk   = '<DATA_DRIVE>\XenogearsHD_CD1+CD2\backup_replaced_by_sprites'
$names = Get-Content "$s\variant_names.txt"

# 1. put the variant's parts into the pack (or restore the pack's own files)
foreach ($n in $names) {
    $dst = Join-Path $pack $n
    if ($Parts -eq 'none') {
        if (Test-Path (Join-Path $bk $n)) { Copy-Item (Join-Path $bk $n) $dst -Force }
        elseif (Test-Path $dst) { Remove-Item $dst -Force }
    } else {
        $src = Join-Path $Parts $n
        if (Test-Path $src) { Copy-Item $src $dst -Force }
    }
}

# 2. core options of the test profile
$opt = '<RETROARCH_DRIVE>\RetroArch\config\Beetle PSX HW\Xenogears (RUS) test.opt'
$t = [IO.File]::ReadAllText($opt)
$t = $t -replace 'beetle_psx_hw_filter = "[^"]*"', "beetle_psx_hw_filter = `"$Filter`""
$t = $t -replace 'beetle_psx_hw_adaptive_smoothing = "[^"]*"', "beetle_psx_hw_adaptive_smoothing = `"$Adaptive`""
[IO.File]::WriteAllText($opt, $t, (New-Object Text.UTF8Encoding $false))

Add-Type @"
using System; using System.Runtime.InteropServices; using System.Threading;
public class KB3 {
  [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Explicit)] public struct U { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public U u; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] i, int cb);
  static void Send(ushort scan, uint flags) { INPUT[] a = new INPUT[1]; a[0].type = 1; a[0].u.ki.wScan = scan; a[0].u.ki.dwFlags = flags | 0x8; SendInput(1, a, Marshal.SizeOf(typeof(INPUT))); }
  public static void Key(ushort scan, int holdMs, bool ext) { uint e = ext ? 1u : 0u; Send(scan, e); Thread.Sleep(holdMs); Send(scan, e | 0x2); }
}
"@
# keys: S = Triangle (menu), Z = Cross (cancel), arrows are extended scancodes
function Press([int]$scan, [int]$ms, [bool]$ext = $false) { [KB3]::Key([uint16]$scan, $ms, $ext) }
# 3. run, load the state, screenshot, quit
$out = Join-Path $s "variants\$Name"; New-Item -ItemType Directory -Force $out | Out-Null
$cfg = @"
network_cmd_enable = "true"
network_cmd_port = "55355"
config_save_on_exit = "false"
screenshot_directory = "$($out -replace '\\','/')"
audio_mute_enable = "true"
pause_nonactive = "false"
savestate_auto_load = "false"
video_font_enable = "false"
"@
[IO.File]::WriteAllText("$s\variant.cfg", $cfg, [Text.Encoding]::ASCII)
$env:VK_LOADER_DRIVERS_DISABLE = '*nv-vk*.json'
$env:VK_LOADER_LAYERS_DISABLE = '~implicit~'
$p = Start-Process -FilePath <RETROARCH_DRIVE>\RetroArch\retroarch.exe -WorkingDirectory <RETROARCH_DRIVE>\RetroArch -PassThru -ArgumentList @(
    '-L', '"<RETROARCH_DRIVE>\RetroArch\cores\mednafen_psx_hw_libretro.dll"',
    '"<DATA_DRIVE>\Xenogears Rus\Xenogears (RUS)\Xenogears (RUS) test.m3u"',
    '--appendconfig', "`"$s\variant.cfg`"", '--verbose', '--log-file', "`"$out\ra.log`"")
$u = New-Object Net.Sockets.UdpClient
function Cmd($c) { $b = [Text.Encoding]::ASCII.GetBytes($c); [void]$u.Send($b, $b.Length, '127.0.0.1', 55355) }
while (-not $p.HasExited -and $p.MainWindowHandle -eq 0) { Start-Sleep -Milliseconds 300; $p.Refresh() }
Start-Sleep 8
Cmd 'LOAD_STATE'
foreach ($w in 3, 3, 4, 6) { Start-Sleep $w; Cmd 'SCREENSHOT' }
Start-Sleep 2
Cmd 'QUIT'; Start-Sleep 1; Cmd 'QUIT'
if (-not $p.WaitForExit(15000)) { Stop-Process -Id $p.Id -Force }
"$Name -> " + ((Get-ChildItem $out -Filter *.png | ForEach-Object Name) -join ', ')
