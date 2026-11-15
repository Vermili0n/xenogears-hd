"""30.10: palette-swapped NPCs stayed pixel in game (Chief Lee's sheet drawn purple for a Lahan merchant, ...): only the
palettes our redrawn frames used had HD files. npc_maps.py project now derives every other palette by recolouring
(derive_palette_pages). This re-projects every built NPC group that has such palettes, installs and merges.

  python pod/palette_swaps_2026-10-30.py      (RetroArch closed; log pod/report/palette_swaps_2026-10-30.log)
"""
import json
import os
import subprocess
import sys
import time
from multiprocessing.pool import ThreadPool

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import prod_sync  # noqa: E402
from install_parts import excluded_groups  # noqa: E402

LOG = os.path.join(ROOT, 'pod', 'report', 'palette_swaps_2026-10-30.log')
WORK = os.path.join(ROOT, 'ai', 'prod_work')


def log(*a):
    line = time.strftime('%H:%M ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def todo_groups():
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    g2d = {m['group']: m['hero_dir'] for m in meta.values()}
    skip = excluded_groups()
    out = []
    for g, hd in sorted(g2d.items()):
        hd = os.path.join(ROOT, hd)
        dp = os.path.join(WORK, g, 'DONE')
        if (g in skip or not os.path.exists(dp) or not os.path.exists(os.path.join(hd, 'pal.json'))
                or not os.path.exists(os.path.join(hd, 'uses.json'))):   # battle sets b_* have no map uses
            continue
        phs = json.load(open(os.path.join(hd, 'uses.json')))['palettes']
        st = open(dp).read().strip()
        have = {f[:-4].rsplit('-', 1)[1] for f in os.listdir(st) if f.endswith('.png')}
        if any(p not in have for p in phs):
            out.append((g, hd, st))
    return out


def project(item):
    g, hd, st = item
    r = subprocess.run([sys.executable, 'npc_maps.py', 'project', '--npc-dir', hd, '--parts', os.path.join(WORK, g, 'parts'),
                        '--out', st, '--scale', '8'], cwd=TOOLS, capture_output=True, text=True)
    return g, r.returncode, (r.stdout.strip().splitlines() or [''])[-1], r.stderr[-300:]


def main():
    items = todo_groups()
    log(f'=== start: {len(items)} NPC groups with palettes lacking HD')
    bad = []
    with ThreadPool(8) as pool:
        for k, (g, rc, out, err) in enumerate(pool.imap_unordered(project, items), 1):
            if rc:
                bad.append(g)
                log(f'[{k}/{len(items)}] {g} FAILED {err}')
            elif k % 20 == 0 or k == len(items):
                log(f'[{k}/{len(items)}] {g}: {out}')
    while prod_sync.retroarch_running():
        log('RetroArch is running - waiting to install')
        time.sleep(300)
    n = 0
    for g, hd, st in items:
        if g in bad:
            continue
        r = subprocess.run([sys.executable, 'install_parts.py', '--parts', st], cwd=TOOLS, capture_output=True, text=True)
        n += 1
        if r.returncode:
            log(g, 'install failed', r.stderr[-200:])
    log(f'installed {n} groups')
    r = subprocess.run([sys.executable, 'merge_shared.py'], cwd=TOOLS, capture_output=True, text=True)
    log('merge_shared:', (r.stdout.strip().splitlines() or [''])[-1])
    log(f'=== end; failed: {bad}; still lacking: {len(todo_groups())}')


if __name__ == '__main__':
    main()
