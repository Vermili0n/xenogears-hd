"""30.10: palette-swap recolour v2 (npc_maps.derive_palette_pages: texels where the redraw shows something else than
the sprite - a face over the sprite's sleeve - take the delta of the colour actually drawn, preferring colours that
are equal in both palettes). v1 turned such faces/hands green on the Lahan boy f6ad8ce563.

  python pod/recolor_v2_2026-10-30.py            project every NPC group with derived palettes into <group>/stage_v2,
                                                  log how many derived-palette pixels changed (pod/report/recolor_v2.json)
  python pod/recolor_v2_2026-10-30.py --install  (RetroArch closed) stage -> stage_v1, stage_v2 -> stage, install the
                                                  derived-palette names, merge_shared
Log pod/report/palette_swaps_2026-10-30.log.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from multiprocessing.pool import ThreadPool

import numpy as np
from PIL import Image

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import prod_sync  # noqa: E402
from install_parts import excluded_groups  # noqa: E402

LOG = os.path.join(ROOT, 'pod', 'report', 'palette_swaps_2026-10-30.log')
REP = os.path.join(ROOT, 'pod', 'report', 'recolor_v2.json')
WORK = os.path.join(ROOT, 'ai', 'prod_work')


def log(*a):
    line = time.strftime('%H:%M ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def groups():
    """NPC groups whose stage has palettes recoloured (no redrawn parts in that palette)."""
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    g2d = {m['group']: m['hero_dir'] for m in meta.values()}
    skip = excluded_groups()
    out = []
    for g, hd in sorted(g2d.items()):
        hd = os.path.join(ROOT, hd)
        gd = os.path.join(WORK, g)
        if (g in skip or not os.path.exists(os.path.join(gd, 'DONE')) or not os.path.exists(os.path.join(hd, 'uses.json'))
                or not os.path.exists(os.path.join(hd, 'pal.json')) or not os.path.isdir(os.path.join(gd, 'parts'))):
            continue
        phs = json.load(open(os.path.join(hd, 'uses.json')))['palettes']
        drawn = {f[:-4].rsplit('-', 1)[1] for f in os.listdir(os.path.join(gd, 'parts')) if f.endswith('.png')}
        derived = [p for p in phs if p not in drawn]
        if derived and drawn & set(phs):
            out.append((g, hd, derived))
    return out


def project(item):
    g, hd, derived = item
    gd = os.path.join(WORK, g)
    new = os.path.join(gd, 'stage_v2')
    for d in (new, new + '_cov'):
        shutil.rmtree(d, ignore_errors=True)
    r = subprocess.run([sys.executable, 'npc_maps.py', 'project', '--npc-dir', hd, '--parts', os.path.join(gd, 'parts'),
                        '--out', new, '--scale', '8'], cwd=TOOLS, capture_output=True, text=True)
    if r.returncode:
        return g, None, r.stderr[-300:]
    old = os.path.join(gd, 'stage')
    tot = ch = 0
    for f in os.listdir(new):
        if not f.endswith('.png') or f[:-4].rsplit('-', 1)[1] not in derived or not os.path.exists(os.path.join(old, f)):
            continue
        a = np.asarray(Image.open(os.path.join(old, f)).convert('RGBA')).astype(np.int16)
        b = np.asarray(Image.open(os.path.join(new, f)).convert('RGBA')).astype(np.int16)
        if a.shape != b.shape:
            continue
        tot += int((a[..., 3] > 0).sum())
        ch += int((np.abs(a - b).max(-1) > 24).sum())
    return g, (ch, tot), ''


def cmd_project():
    items = groups()
    log(f'=== recolour v2: projecting {len(items)} groups into stage_v2')
    rep, bad = {}, []
    with ThreadPool(8) as pool:
        for k, (g, res, err) in enumerate(pool.imap_unordered(project, items), 1):
            if res is None:
                bad.append(g)
                log(f'[{k}/{len(items)}] {g} FAILED {err}')
                continue
            rep[g] = {'changed': res[0], 'opaque': res[1], 'pct': round(100 * res[0] / max(1, res[1]), 2)}
            if k % 20 == 0 or k == len(items):
                log(f'[{k}/{len(items)}] {g}: {rep[g]["pct"]}%')
    json.dump(dict(sorted(rep.items(), key=lambda kv: -kv[1]['pct'])), open(REP, 'w'), indent=1)
    log(f'recolour v2 projected; failed {bad}; report {REP}')


def cmd_install():
    while prod_sync.retroarch_running():
        log('RetroArch is running - waiting to install recolour v2')
        time.sleep(120)
    n = 0
    for g, hd, derived in groups():
        gd = os.path.join(WORK, g)
        new, old = os.path.join(gd, 'stage_v2'), os.path.join(gd, 'stage')
        if not os.path.isdir(new):
            continue
        names = [f for f in os.listdir(new) if f.endswith('.png') and f[:-4].rsplit('-', 1)[1] in derived]
        for d in ('stage_v1', 'stage_v1_cov'):
            shutil.rmtree(os.path.join(gd, d), ignore_errors=True)
        os.replace(old, os.path.join(gd, 'stage_v1'))
        if os.path.isdir(old + '_cov'):
            os.replace(old + '_cov', os.path.join(gd, 'stage_v1_cov'))
        os.replace(new, old)
        os.replace(new + '_cov', old + '_cov')
        lst = os.path.join(gd, 'recolor_v2_names.txt')
        open(lst, 'w').write('\n'.join(names) + '\n')
        r = subprocess.run([sys.executable, 'install_parts.py', '--parts', old, '--only', lst], cwd=TOOLS,
                           capture_output=True, text=True)
        if r.returncode:
            log(g, 'install failed', r.stderr[-200:])
        n += 1
    log(f'recolour v2 installed {n} groups (old stages kept as stage_v1)')
    r = subprocess.run([sys.executable, 'merge_shared.py'], cwd=TOOLS, capture_output=True, text=True)
    log('merge_shared:', (r.stdout.strip().splitlines() or [''])[-1])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    cmd_install() if ap.parse_args().install else cmd_project()
