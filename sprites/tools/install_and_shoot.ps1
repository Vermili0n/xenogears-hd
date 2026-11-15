param(
    [Parameter(Mandatory)] [string]$Parts,   # folder with replacement PNGs to install (all files)
    [Parameter(Mandatory)] [string]$OutDir,  # where screenshots go
    [string]$Filter = 'nearest'
)
# Installs replacement parts into the HD pack (backing up pack files it overwrites once),
# then loads the "Xenogears (RUS) test" save state (saved on an area transition) and takes screenshots.
$ErrorActionPreference = 'Stop'
$pack = '<DATA_DRIVE>\Xenogears (USA) (Disc 1)\Xenogears (USA)-texture-replacements'
$bk   = '<DATA_DRIVE>\XenogearsHD_CD1+CD2\backup_replaced_by_sprites'
New-Item -ItemType Directory -Force $bk, $OutDir | Out-Null
$n = 0
foreach ($f in Get-ChildItem $Parts -Filter *.png) {
    $dst = Join-Path $pack $f.Name
    if ((Test-Path $dst) -and -not (Test-Path (Join-Path $bk $f.Name))) {
        $own = Get-Content "$bk\_installed_sprite_parts.txt" -ErrorAction SilentlyContinue
        if ($own -notcontains $f.Name) { Copy-Item $dst $bk }
    }
    Copy-Item $f.FullName $dst -Force
    Add-Content "$bk\_installed_sprite_parts.txt" $f.Name
    $n++
}
"installed $n parts"

$opt = '<RETROARCH_DRIVE>\RetroArch\config\Beetle PSX HW\Xenogears (RUS) test.opt'
$t = [IO.File]::ReadAllText($opt) -replace 'beetle_psx_hw_filter = "[^"]*"', "beetle_psx_hw_filter = `"$Filter`""
[IO.File]::WriteAllText($opt, $t, (New-Object Text.UTF8Encoding $false))
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
$cfgPath = Join-Path $OutDir 'shoot.cfg'
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
foreach ($w in 4, 4, 6) { Start-Sleep $w; Cmd 'SCREENSHOT' }
Start-Sleep 2
Cmd 'QUIT'; Start-Sleep 1; Cmd 'QUIT'
if (-not $p.WaitForExit(15000)) { Stop-Process -Id $p.Id -Force }
Get-ChildItem $OutDir -Filter *.png | Sort-Object LastWriteTime | ForEach-Object FullName
