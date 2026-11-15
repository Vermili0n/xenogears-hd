"""Portable bundle (30.10): one zip with RetroArch + our Beetle core + BIOS + the HD pack (+ the -pages pack of NPC
sheets, 01.11) + the Russian disc + the player's Russian saves + a launcher with relative paths. Unpack anywhere on
another PC, run "Xenogears HD.cmd".

  python make_portable.py [--out <DATA_DRIVE>\\XenogearsHD_portable\\Xenogears_HD_RUS.zip] [--split-gb 2]   (RetroArch closed)
  --split-gb 2: independent zips _partNN.zip of <= 2 GB (10^9 bytes) that unpack into the same folder, + Raspakovat.cmd

Nothing is staged on disk (C: is nearly full): files go straight from their places into the zip.
PNG and the disc images are stored (already compressed / slow to deflate), the rest is deflated.
"""
import argparse
import os
import time
import zipfile

RA = r'<RETROARCH_DRIVE>\RetroArch'
PACK = os.path.join(RA, 'system', 'Xenogears (USA)-texture-replacements')
PAGES = os.path.join(RA, 'system', 'Xenogears (RUS)-texture-replacements-pages')   # page-aligned NPC sheets (01.11)
DISC = r'<DATA_DRIVE>\Xenogears Rus\Xenogears (RUS)'
NAME = 'Xenogears (RUS)'          # m3u base name = core options file = pack folder prefix
TOP = 'Xenogears HD RUS'
RA_DIRS = ['assets', 'autoconfig', 'filters', 'info', 'platforms']   # menu, gamepads, Qt plugin
RA_SKIP_EXT = ('.cmd', '.url', '.lpl')
RA_SKIP = {'uninstall.exe'}

LAUNCHER = r'''@echo off
rem Xenogears (RUS) + HD pack, portable: unpack anywhere (a path without Cyrillic is safest), run this file.
setlocal
set "ROOT=%~dp0"
rem Vulkan without implicit overlay layers (Steam, OBS, Overwolf, Epic overlays can hang RetroArch)
set VK_LOADER_LAYERS_DISABLE=~implicit~
rem parallel HD texture decoders: CPU threads - 4, from 2 to 10
set /a XENO_IO_THREADS=%NUMBER_OF_PROCESSORS%-4
if %XENO_IO_THREADS% LSS 2 set XENO_IO_THREADS=2
if %XENO_IO_THREADS% GTR 10 set XENO_IO_THREADS=10
start "" /D "%ROOT%RetroArch" "%ROOT%RetroArch\retroarch.exe" -c "%ROOT%RetroArch\retroarch.cfg" -L "%ROOT%RetroArch\cores\mednafen_psx_hw_libretro.dll" "%ROOT%Xenogears (RUS)\Xenogears (RUS).m3u"
'''

README = '''Xenogears (русская версия) + HD-пак — переносная сборка

1. Распаковать архив целиком в любую папку, лучше без русских букв в пути (например D:\\Games).
   Файлов ~{n} тысяч: 7-Zip или WinRAR распакуют за минуты, проводник Windows — очень долго.
   Ещё вариант без программ: в папке с архивом  tar -xf Xenogears_HD_RUS.zip
2. Запустить "Xenogears HD.cmd".

Нужно: Windows 10/11 x64, видеокарта с Vulkan (любая современная AMD/NVIDIA/Intel со свежим драйвером).
Внутри: RetroArch, ядро Beetle PSX HW (своя сборка), BIOS scph5501, HD-пак, образ RUS (2 диска), сохранения.

Управление: геймпад XInput подхватывается сам; F1 — меню RetroArch, F2/F4 — быстрое сохранение/загрузка.
После быстрой загрузки (F4) HD-спрайты появляются после смены локации — это особенность сохранений.
Смена диска: F1 -> Управление дисками -> извлечь лоток, выбрать диск 2, вставить.

Если тормозит или вылетает на слабом ПК (меньше 16 ГБ ОЗУ или видеокарта < 4 ГБ):
F1 -> Параметры ядра -> HD Texture RAM Cache Budget 8192 -> 2048, HD Texture VRAM Cache Budget 3072 -> 1536
(сохраняется для этой игры).
'''


UNPACK = r"""@echo off
rem Unpacks every Xenogears_HD_RUS_partNN.zip next to this file into ONE folder "Xenogears HD RUS"
rem (the parts are independent zips of different files; Windows 10/11 built-in tar).
setlocal
cd /d "%~dp0"
set N=0
for %%f in (Xenogears_HD_RUS_part*.zip) do (
  echo Unpacking %%f ...
  tar -xf "%%f"
  if errorlevel 1 (echo ERROR in %%f - the part is damaged or missing space & pause & exit /b 1)
  set /a N+=1
)
echo.
echo Done: %N% parts. Now run "Xenogears HD RUS\Xenogears HD.cmd"
pause
"""


def entries():
    """(source path or bytes, name in the archive), in archive order: launcher, RetroArch, disc, pack."""
    T = TOP + '/'
    out = []
    # RetroArch: program files + the folders the menu/gamepads need; the config with the one absolute path cleared
    for f in sorted(os.listdir(RA)):
        p = os.path.join(RA, f)
        if (os.path.isfile(p) and not f.endswith(RA_SKIP_EXT) and f not in RA_SKIP and '.bak' not in f
                and f != 'retroarch.cfg'):
            out.append((p, T + 'RetroArch/' + f))
    cfg = open(os.path.join(RA, 'retroarch.cfg'), encoding='utf-8').read().splitlines()
    cfg = ['cache_directory = ""' if l.startswith('cache_directory ') else l for l in cfg]
    out.append((('\n'.join(cfg) + '\n').encode('utf-8'), T + 'RetroArch/retroarch.cfg'))
    for d in RA_DIRS:
        out += tree(os.path.join(RA, d), T + 'RetroArch/' + d)
    out.append((os.path.join(RA, 'cores', 'mednafen_psx_hw_libretro.dll'), T + 'RetroArch/cores/mednafen_psx_hw_libretro.dll'))
    out.append((os.path.join(RA, 'config', 'Beetle PSX HW', NAME + '.opt'), T + f'RetroArch/config/Beetle PSX HW/{NAME}.opt'))
    out.append((os.path.join(RA, 'system', 'scph5501.bin'), T + 'RetroArch/system/scph5501.bin'))
    for sub, names in (('saves', [NAME + '.srm', NAME + '.1.mcr', NAME + '.ldci']), ('states', [NAME + '.state'])):
        for n in names:
            p = os.path.join(RA, sub, 'Beetle PSX HW', n)
            if os.path.exists(p):
                out.append((p, T + f'RetroArch/{sub}/Beetle PSX HW/{n}'))
    for f in sorted(os.listdir(DISC)):
        if f.lower().endswith(('.bin', '.cue')) or f == NAME + '.m3u':
            out.append((os.path.join(DISC, f), T + f'{NAME}/{f}'))
    # the HD pack, as a real folder named after the Russian m3u (here it is a junction)
    out += tree(PACK, T + f'RetroArch/system/{NAME}-texture-replacements')
    out += tree(PAGES, T + f'RetroArch/system/{NAME}-texture-replacements-pages')
    readme = README.replace('{n}', str(round((len(out) + 2) / 1000)))
    return [(LAUNCHER.replace('\n', '\r\n').encode('ascii'), T + 'Xenogears HD.cmd'),
            (('﻿' + readme.replace('\n', '\r\n')).encode('utf-8'), T + 'README_RU.txt')] + out


def tree(src, arc):
    out = []
    for root, _, files in os.walk(src):
        for f in sorted(files):
            p = os.path.join(root, f)
            out.append((p, os.path.join(arc, os.path.relpath(p, src)).replace('\\', '/')))
    return out


class Volumes:
    """Writes entries into one zip, or into independent zips of at most `limit` bytes (parts of different files that
    unpack into the same folder). The size of a part is checked on disk before each file goes in."""

    def __init__(self, out, limit):
        self.out, self.limit, self.k, self.z, self.paths = out, limit, 0, None, []

    def _open(self):
        if self.z:
            self.z.close()
        self.k += 1
        p = self.out if not self.limit else self.out.replace('.zip', f'_part{self.k:02d}.zip')
        self.paths.append(p)
        self.z = zipfile.ZipFile(p + '.tmp', 'w', zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6)
        self.used = 0

    def add(self, src, arc):
        size = len(src) if isinstance(src, bytes) else os.path.getsize(src)
        cost = size + 2 * (len(arc.encode('utf-8')) + 100)          # data + local header + central directory entry
        if self.z is None or (self.limit and self.used and self.used + cost > self.limit):
            self._open()
        if isinstance(src, bytes):
            self.z.writestr(arc, src)
        else:
            ext = os.path.splitext(src)[1].lower()
            self.z.write(src, arc, compress_type=zipfile.ZIP_STORED if ext in ('.png', '.bin', '.bc7') else zipfile.ZIP_DEFLATED)
        self.used += cost

    def close(self):
        self.z.close()
        for p in self.paths:
            os.replace(p + '.tmp', p)
        return self.paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'<DATA_DRIVE>\XenogearsHD_portable\Xenogears_HD_RUS.zip')
    ap.add_argument('--split-gb', type=float, default=0, help='independent zips of at most this many GB (10^9 bytes) + Raspakovat.cmd')
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    t0 = time.time()
    ents = entries()
    vol = Volumes(a.out, int(a.split_gb * 1e9))
    for k, (src, arc) in enumerate(ents, 1):
        vol.add(src, arc)
        if k % 10000 == 0:
            print(f'  {k}/{len(ents)} files, part {vol.k}, {time.time() - t0:.0f} s', flush=True)
    paths = vol.close()
    if a.split_gb:
        d = os.path.dirname(a.out)
        # parts of an older, longer build would unpack old files over the new ones
        prefix = os.path.basename(a.out).replace('.zip', '_part')
        keep = {os.path.normcase(os.path.abspath(p)) for p in paths}
        for f in os.listdir(d):
            if (f.startswith(prefix) and f.endswith('.zip')
                    and os.path.normcase(os.path.abspath(os.path.join(d, f))) not in keep):
                os.remove(os.path.join(d, f))
                print('removed stale part', f)
        open(os.path.join(d, 'Raspakovat.cmd'), 'w', newline='\r\n', encoding='ascii').write(UNPACK)
        open(os.path.join(d, 'README_RU.txt'), 'w', newline='\r\n', encoding='utf-8-sig').write(
            'Все части Xenogears_HD_RUS_partNN.zip положить в одну папку и запустить Raspakovat.cmd\n'
            '(или в 7-Zip/WinRAR выделить ВСЕ части -> "Извлечь сюда"). Получится папка "Xenogears HD RUS",\n'
            'в ней запустить "Xenogears HD.cmd". Подробности - README_RU.txt внутри папки.\n')
    for p in paths:
        print(f'{p}  {os.path.getsize(p) / 1e9:.3f} GB')
    print(f'done: {len(ents)} files in {len(paths)} archive(s), {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
