param(
    [Parameter(Mandatory)] [string]$OutDir,   # screenshots + retroarch log go here
    [string[]]$Moves = @('Down:2.5', 'Up:2.5'), # key:seconds, keys = Down/Up/Left/Right
    [int]$ShotMs = 120
)
# Loads the "Xenogears (RUS) test" save state (saved on an area transition), then holds arrow keys in the
# RetroArch window while taking screenshots, to check HD sprite replacements during animation.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W32 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
}
"@
$vk = @{ Up = 0x26; Down = 0x28; Left = 0x25; Right = 0x27 }
$cfg = @"
network_cmd_enable = "true"
network_cmd_port = "55355"
config_save_on_exit = "false"
screenshot_directory = "$($OutDir -replace '\\','/')"
audio_mute_enable = "true"
pause_nonactive = "false"
savestate_auto_load = "false"
video_font_enable = "false"
log_to_file = "true"
log_to_file_timestamp = "false"
log_dir = "$($OutDir -replace '\\','/')"
log_verbosity = "true"
libretro_log_level = "1"
"@
$cfgPath = Join-Path $OutDir 'walk.cfg'
[IO.File]::WriteAllText($cfgPath, $cfg, [Text.Encoding]::ASCII)
$env:VK_LOADER_DRIVERS_DISABLE = '*nv-vk*.json'
$env:VK_LOADER_LAYERS_DISABLE = '~implicit~'
$p = Start-Process -FilePath <RETROARCH_DRIVE>\RetroArch\retroarch.exe -WorkingDirectory <RETROARCH_DRIVE>\RetroArch -PassThru -ArgumentList @(
    '-L', '"<RETROARCH_DRIVE>\RetroArch\cores\mednafen_psx_hw_libretro.dll"',
    '"<DATA_DRIVE>\Xenogears Rus\Xenogears (RUS)\Xenogears (RUS) test.m3u"',
    '--appendconfig', "`"$cfgPath`"")
$u = New-Object Net.Sockets.UdpClient
function Cmd($c) { $b = [Text.Encoding]::ASCII.GetBytes($c); [void]$u.Send($b, $b.Length, '127.0.0.1', 55355) }
while (-not $p.HasExited -and $p.MainWindowHandle -eq 0) { Start-Sleep -Milliseconds 300; $p.Refresh() }
Start-Sleep 8
Cmd 'LOAD_STATE'
Start-Sleep 7
Cmd 'SCREENSHOT'
Start-Sleep 1
[void][W32]::ShowWindow($p.MainWindowHandle, 9)
[void][W32]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 500
foreach ($m in $Moves) {
    $k, $sec = $m -split ':'
    $code = [byte]$vk[$k]
    [W32]::keybd_event($code, 0, 0, [UIntPtr]::Zero)
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt [double]$sec) {
        [W32]::keybd_event($code, 0, 0, [UIntPtr]::Zero)   # keep the key "held" (auto-repeat)
        Cmd 'SCREENSHOT'
        Start-Sleep -Milliseconds $ShotMs
    }
    [W32]::keybd_event($code, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 400
}
Start-Sleep 1
Cmd 'QUIT'; Start-Sleep 1; Cmd 'QUIT'
if (-not $p.WaitForExit(15000)) { Stop-Process -Id $p.Id -Force }
"shots: " + (Get-ChildItem $OutDir -Filter *.png).Count
