"""Install the redrawn parts of Elly's walk copy (maps 934/936, see elly_copy_set.py) - 30.10.

  python elly_copy_install.py --res <dir with v4/*.png renders> [--dry]
compose_set (8x, 16x head pass, colour offsets of 'elly') -> batch_redraw slice (exact masks, UV compensation)
into ai/prod_work/h_elly934/parts, then only the 32 changed parts (copy hashes) go into the pack as BC7 (the other
parts of these frames are shared with the rest of Elly's walk and keep their HD). RetroArch must be closed.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402

PACK = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (USA)-texture-replacements'
HD = os.path.join(ROOT, 'extracted', 'disc1_full', 'elly934')
PROD = os.path.join(ROOT, 'ai', 'prod_elly934')
GD = os.path.join(ROOT, 'ai', 'prod_work', 'h_elly934')


def run(cmd):
    print('$', ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode:
        raise SystemExit(f'failed: {cmd[1]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--res', required=True)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    work = os.path.join(GD, 'work')
    os.makedirs(work, exist_ok=True)
    run([sys.executable, 'compose_set.py', '--render', PROD, '--res', os.path.join(os.path.abspath(a.res), 'v4'),
         '--work', work, '--name', 'h_elly934', '--out-scale', '8', '--offset-key', 'elly'])
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', 'prod_work/h_elly934', '--hero-dir', HD, '--scale', '8',
         '--exact-mask', '--ring', '0', '--uv-compensate', '--only', only])
    copy = json.load(open(os.path.join(HD, 'copy_map.json')))
    parts = os.path.join(GD, 'parts')
    n = 0
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png') or f.split('-')[0] not in copy:
            continue
        rgba = np.asarray(Image.open(os.path.join(parts, f)).convert('RGBA'))
        lv, flags = bc7pack.levels_of(rgba)
        enc, failed, _ = bc7pack.encode_levels(lv)
        if failed:
            print('BC7 rules failed, kept as PNG:', f)
            data, dst = None, f
        else:
            data, dst = bc7pack.pack_file(enc, rgba.shape[1], rgba.shape[0], flags), f[:-4] + '.bc7'
        print(('(dry) ' if a.dry else '') + 'install', dst)
        if not a.dry:
            if data is None:
                Image.fromarray(rgba, 'RGBA').save(os.path.join(PACK, dst))
            else:
                with open(os.path.join(PACK, dst + '.tmp'), 'wb') as fo:
                    fo.write(data)
                os.replace(os.path.join(PACK, dst + '.tmp'), os.path.join(PACK, dst))
        n += 1
    print(f'copy parts installed: {n} of {len(copy)} changed parts' + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
