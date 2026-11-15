param(
    [ValidateSet('start', 'cmd', 'keys', 'stop')] [string]$Action,
    [string]$Arg = '',            # cmd: network command (SCREENSHOT, LOAD_STATE...); keys: "Down:1.5,Enter:0.1,..."
    [string]$OutDir = '<XENO_SPRITES>\ai\ingame'
)
# Persistent RetroArch session for in-game checks: start once, then send network commands / held keys, stop at the end.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W32b {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
}
"@
function Cmd($c) { $u = New-Object Net.Sockets.UdpClient; $b = [Text.Encoding]::ASCII.GetBytes($c); [void]$u.Send($b, $b.Length, '127.0.0.1', 55355); $u.Close() }
$vk = @{ Up = 0x26; Down = 0x28; Left = 0x25; Right = 0x27; Enter = 0x0D; X = 0x58; Z = 0x5A; A = 0x41; S = 0x53 }
switch ($Action) {
    'start' {
        $cfg = @"
network_cmd_enable = "true"
network_cmd_port = "55355"
config_save_on_exit = "false"
screenshot_directory = "$($OutDir -replace '\\','/')"
audio_mute_enable = "true"
pause_nonactive = "false"
savestate_auto_load = "false"
video_font_enable = "false"
"@
        [IO.File]::WriteAllText("$OutDir\session.cfg", $cfg, [Text.Encoding]::ASCII)
        # detached launch: a child of this shell dies with it, so start through WMI with a cmd wrapper (env vars)
        $bat = "$OutDir\launch.cmd"
        $lines = @('@echo off', 'set VK_LOADER_DRIVERS_DISABLE=*nv-vk*.json', 'set VK_LOADER_LAYERS_DISABLE=~implicit~', 'cd /d <RETROARCH_DRIVE>\RetroArch',
                   ('start "" <RETROARCH_DRIVE>\RetroArch\retroarch.exe -L "<RETROARCH_DRIVE>\RetroArch\cores\mednafen_psx_hw_libretro.dll" ' +
                    '"<DATA_DRIVE>\Xenogears Rus\Xenogears (RUS)\Xenogears (RUS).m3u" --appendconfig "' + "$OutDir\session.cfg" + '"'))
        [IO.File]::WriteAllLines($bat, $lines, [Text.Encoding]::ASCII)
        $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = "cmd /c `"$bat`""}
        Start-Sleep 5
        "started (wrapper pid $($r.ProcessId)) ra=" + ((Get-Process retroarch -ErrorAction SilentlyContinue).Id -join ',')
    }
    'cmd' { Cmd $Arg; "sent $Arg" }
    'keys' {
        $p = Get-Process retroarch | Select-Object -First 1
        [void][W32b]::ShowWindow($p.MainWindowHandle, 9); [void][W32b]::SetForegroundWindow($p.MainWindowHandle)
        Start-Sleep -Milliseconds 300
        foreach ($m in $Arg -split ',') {
            $k, $sec = $m -split ':'
            if ($k -eq 'Shot') { Cmd 'SCREENSHOT'; Start-Sleep -Milliseconds 300; continue }
            if ($k -eq 'Wait') { Start-Sleep -Milliseconds ([int]([double]$sec * 1000)); continue }
            $code = [byte]$vk[$k]
            $t0 = Get-Date
            [W32b]::keybd_event($code, 0, 0, [UIntPtr]::Zero)
            while (((Get-Date) - $t0).TotalSeconds -lt [double]$sec) { Start-Sleep -Milliseconds 50; [W32b]::keybd_event($code, 0, 0, [UIntPtr]::Zero) }
            [W32b]::keybd_event($code, 0, 2, [UIntPtr]::Zero)
            Start-Sleep -Milliseconds 150
        }
        "keys done"
    }
    'stop' { Cmd 'QUIT'; Start-Sleep 1; Cmd 'QUIT'; Start-Sleep 3; Get-Process retroarch -ErrorAction SilentlyContinue | Stop-Process -Force; "stopped" }
}
