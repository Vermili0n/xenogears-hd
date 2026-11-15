"""Merge replacement files that several production groups write under the same name.

Two NPC sets can live in the same VRAM upload block with the same palette (twin sets of one character: same texture
data, different frame lists). Each group redraws only its own frames; the rest of its page is the xBR upscale of the
original. Installed one after the other, the last group would replace the other group's redrawn texels with xBR.
Here every shared name is rebuilt: the first group's file (sorted by name) plus, from each other group, the texels
only that group redrew (coverage masks <stage>_cov written by npc_maps.py project). Written straight into the pack.

  python merge_shared.py [--dry]
Groups whose coverage masks are missing (built before the masks existed) are re-projected first.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'ai', 'prod_work')
sys.path.insert(0, HERE)
from install_parts import PACK, excluded, excluded_groups  # noqa: E402


# pilot sets (28.10, before the production run) live outside prod_work; listed first so their redrawn texels win:
# the Lahan boy f6ad8ce563 shares its top 6 blocks with m_e04fe7b326, whose art there flickered with his (30.10)
PILOTS = {'p3h_npcf6ad': 'ai/p3h_npcf6ad/stage_pal', 'p3h_npc36e3': 'ai/p3h_npc36e3/stage_pal',
          'p3h_timothy': 'ai/p3h_timothy/stage_pal'}


def stages():
    out = {g: os.path.join(ROOT, d) for g, d in PILOTS.items() if os.path.isdir(os.path.join(ROOT, d))}
    skip_groups = excluded_groups()  # never installed, so never merged into shared pack files either
    for g in sorted(os.listdir(WORK)):
        if g in skip_groups:
            continue
        dp = os.path.join(WORK, g, 'DONE')
        if os.path.exists(dp):
            st = open(dp).read().strip()
            if os.path.isdir(st):
                out[g] = st
    return out


def reproject(g, meta_dirs):
    gd = os.path.join(WORK, g)
    r = subprocess.run([sys.executable, 'npc_maps.py', 'project', '--npc-dir', os.path.join(ROOT, meta_dirs[g]),
                        '--parts', os.path.join(gd, 'parts'), '--out', os.path.join(gd, 'stage'), '--scale', '8'],
                       cwd=HERE, capture_output=True, text=True)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    st = stages()
    by = defaultdict(list)
    for g, d in st.items():
        for f in os.listdir(d):
            if f.endswith('.png'):
                by[f].append(g)
    skip = excluded()   # never written to the pack (install_parts.py, ai/prod/exclude_parts.txt)
    shared = {f: gs for f, gs in by.items() if len(gs) > 1 and f not in skip}
    groups = sorted({g for gs in shared.values() for g in gs})
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    dirs = {m['group']: m['hero_dir'] for m in meta.values()}
    for g in groups:  # NPC stages need their coverage masks
        if os.path.basename(st[g]) == 'stage' and not os.path.isdir(st[g] + '_cov'):
            print(g, 'coverage masks rebuilt' if reproject(g, dirs) else 'REPROJECT FAILED', flush=True)
    merged = changed = 0
    for f, gs in sorted(shared.items()):
        ims, covs = [], []
        for g in gs:
            im = np.asarray(Image.open(os.path.join(st[g], f)).convert('RGBA')).copy()
            cp = os.path.join(st[g] + '_cov', f)
            if os.path.exists(cp):                           # NPC stages (prod 'stage', pilot 'stage_pal')
                cv = np.asarray(Image.open(cp)) > 127
            elif os.path.basename(st[g]) != 'stage':        # hero parts: the whole file is redrawn
                cv = im[..., 3] > 0
            else:
                cv = np.zeros(im.shape[:2], bool)
            ims.append(im)
            covs.append(cv)
        if len({i.shape for i in ims}) > 1:
            print('size mismatch, left as installed:', f, gs)
            continue
        out, have = ims[0].copy(), covs[0].copy()
        for im, cv in zip(ims[1:], covs[1:]):
            take = cv & ~have
            out[take] = im[take]
            have |= cv
        merged += 1
        dst = os.path.join(PACK, f)
        cur = np.asarray(Image.open(dst).convert('RGBA')) if os.path.exists(dst) else None
        if cur is None or cur.shape != out.shape or not np.array_equal(cur, out):
            changed += 1
            if not a.dry:
                Image.fromarray(out, 'RGBA').save(dst)
    print(f'shared names {len(shared)} (groups {len(groups)}), merged {merged}, pack files rewritten {changed}'
          + (' (dry run)' if a.dry else ''))


if __name__ == '__main__':
    main()
