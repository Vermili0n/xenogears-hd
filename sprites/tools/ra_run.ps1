param(
    [string]$Keys = '',          # e.g. "Shot,Down:2,Shot,Wait:3,Shot" (Shot = screenshot, Wait:s = pause)
    [string]$OutDir = '<XENO_SPRITES>\ai\ingame',
    [string]$Content = '<DATA_DRIVE>\Xenogears Rus\Xenogears (RUS)\Xenogears (RUS).m3u',
    [int]$Slot = 0
)
# One-shot in-game check: start RetroArch, load the save state, play a key script with screenshots, quit.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W32c {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
}
"@
$vk = @{ Up = 0x26; Down = 0x28; Left = 0x25; Right = 0x27; Enter = 0x0D; X = 0x58; Z = 0x5A; A = 0x41; S = 0x53 }
$cfg = @"
network_cmd_enable = "true"
network_cmd_port = "55355"
config_save_on_exit = "false"
screenshot_directory = "$($OutDir -replace '\\','/')"
audio_mute_enable = "true"
pause_nonactive = "false"
savestate_auto_load = "false"
video_font_enable = "false"
state_slot = "$Slot"
"@
[IO.File]::WriteAllText("$OutDir\run.cfg", $cfg, [Text.Encoding]::ASCII)
$env:VK_LOADER_DRIVERS_DISABLE = '*nv-vk*.json'
$env:VK_LOADER_LAYERS_DISABLE = '~implicit~'
$p = Start-Process -FilePath <RETROARCH_DRIVE>\RetroArch\retroarch.exe -WorkingDirectory <RETROARCH_DRIVE>\RetroArch -PassThru -ArgumentList @(
    '-L', '"<RETROARCH_DRIVE>\RetroArch\cores\mednafen_psx_hw_libretro.dll"', "`"$Content`"", '--appendconfig', "`"$OutDir\run.cfg`"")
$u = New-Object Net.Sockets.UdpClient
function Cmd($c) { $b = [Text.Encoding]::ASCII.GetBytes($c); [void]$u.Send($b, $b.Length, '127.0.0.1', 55355) }
while (-not $p.HasExited -and $p.MainWindowHandle -eq 0) { Start-Sleep -Milliseconds 300; $p.Refresh() }
Start-Sleep 8
Cmd 'LOAD_STATE'
Start-Sleep 5
[void][W32c]::ShowWindow($p.MainWindowHandle, 9); [void][W32c]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 400
foreach ($m in ($Keys -split ',' | Where-Object { $_ })) {
    $k, $sec = $m -split ':'
    if ($k -eq 'Shot') { Cmd 'SCREENSHOT'; Start-Sleep -Milliseconds 400; continue }
    if ($k -eq 'Wait') { Start-Sleep -Milliseconds ([int]([double]$sec * 1000)); continue }
    $code = [byte]$vk[$k]
    $t0 = Get-Date
    [W32c]::keybd_event($code, 0, 0, [UIntPtr]::Zero)
    while (((Get-Date) - $t0).TotalSeconds -lt [double]$sec) { Start-Sleep -Milliseconds 50; [W32c]::keybd_event($code, 0, 0, [UIntPtr]::Zero) }
    [W32c]::keybd_event($code, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 150
}
Start-Sleep 1
Cmd 'QUIT'; Start-Sleep 1; Cmd 'QUIT'
if (-not $p.WaitForExit(15000)) { Stop-Process -Id $p.Id -Force }
Get-ChildItem $OutDir -Filter *.png | Sort-Object LastWriteTime | Select-Object -Last 12 | ForEach-Object Name
