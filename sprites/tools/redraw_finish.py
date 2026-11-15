"""Finish a re-render install in the BC7 pack (01.11.2026).

fix_apply.py installs the rebuilt groups as PNG, and its merge_shared.py step rewrites every twin-shared file (~1600)
as PNG too. The core reads PNG before BC7, so they work at once, but at 4x the VRAM and without the seam fill.

  python redraw_finish.py [--workers 12] [--dry]      (RetroArch closed; --dry only reads, works with it open)
1. every PNG in the pack -> BC7 (bc7pack.py rules; a texture that cannot keep them stays PNG). The PNG and the .bc7
   it replaces are backed up to <DATA_DRIVE>\\xeno_redraw_backup\\<stamp> first.
2. seam fill for every hero and NPC set (seam_fill_all.py / seam_fill_npc.py): files with nothing to fill are not
   touched, so only the re-installed ones change. ~8 min.
Log: pod/report/redraw_finish.log.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from fix_apply import retroarch_running  # noqa: E402
from install_parts import PACK  # noqa: E402

BACKUP = r'<DATA_DRIVE>\xeno_redraw_backup'
LOG = os.path.join(ROOT, 'pod', 'report', 'redraw_finish.log')
HEROES = 'fei,elly,citan,bart,billy,rico,emeralda,chuchu,maria'


def log(s):
    s = time.strftime('%d.%m %H:%M ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def convert_pngs(pack, backup, dry, workers=12):
    """PNG files of the pack -> .bc7 next to them, PNG deleted. Returns (converted, kept as PNG, errors)."""
    pngs = sorted(e.path for e in os.scandir(pack) if e.name.endswith('.png'))
    if dry or not pngs:
        return len(pngs), 0, 0
    os.makedirs(backup, exist_ok=True)
    for p in pngs:
        shutil.copy2(p, backup)
        if os.path.exists(p[:-4] + '.bc7'):
            shutil.copy2(p[:-4] + '.bc7', backup)
    ok = kept = err = 0
    with Pool(workers) as pool:
        for src, res, info, _ in pool.imap_unordered(bc7pack.convert_one, [(p, p[:-4] + '.bc7') for p in pngs],
                                                    chunksize=8):
            if res == 'ok':
                os.remove(src)
                ok += 1
            elif res == 'kept_png':
                kept += 1
            else:
                err += 1
                print('error:', os.path.basename(src), info)
    return ok, kept, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    if not a.dry and retroarch_running():
        sys.exit('RetroArch is running - close it first')
    t0 = time.time()
    bk = os.path.join(BACKUP, time.strftime('%Y%m%d_%H%M%S'))
    ok, kept, err = convert_pngs(PACK, bk, a.dry, a.workers)
    log(f'pack PNG -> BC7: {ok} converted, {kept} kept as PNG, {err} errors' + (f', backup {bk}' if ok and not a.dry
                                                                               else '') + (' (dry)' if a.dry else ''))
    opt = ['--workers', str(a.workers)] + (['--dry'] if a.dry else [])
    for cmd in (['seam_fill_all.py', '--heroes', HEROES], ['seam_fill_npc.py']):
        r = subprocess.run([sys.executable, os.path.join(HERE, cmd[0])] + cmd[1:] + opt, cwd=HERE)
        if r.returncode:
            sys.exit(f'{cmd[0]} failed')
    log(f'redraw finish done, {time.time() - t0:.0f} s' + (' (dry)' if a.dry else ''))


if __name__ == '__main__':
    main()
