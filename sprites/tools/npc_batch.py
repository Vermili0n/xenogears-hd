"""Massovka NPC keyframes: pick evenly spaced keyframes per NPC, pack one 4x4 grid per NPC, submit all grids as one
Gemini batch (NPC prompt, style reference only), then split results back and run QA per NPC.

  python npc_batch.py prep  --ids a,b,c --job npc_lahan [--keys 16]
  python npc_batch.py split --job npc_lahan
Per NPC: ai/npcj/<id>/in (grids.json, grid_k00.png), after split ai/npcj/<id>/out/k00.png and QA into
ai/npc_<id>_prod/work. Combined job: ai/<job>/in/grid_<id>.png + grids.json (+ ref_style.png).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


NPC_ROOT = os.path.join(ROOT, 'extracted', 'npc')


def cover_frames(nid):
    """All frames that bring new parts (greedy cover), in frame order."""
    fr = json.load(open(os.path.join(NPC_ROOT, nid, 'layout.json')))['npc']['frames']
    parts = [{(p['block'], p['clut']) for p in f} for f in fr]
    allp = set().union(*parts) if parts else set()
    seen, cover = set(), []
    while seen != allp:
        b = max(range(len(fr)), key=lambda i: len(parts[i] - seen))
        if not parts[b] - seen:
            break
        cover.append(b)
        seen |= parts[b]
    return sorted(cover)


def keyframes(cover, k):
    if len(cover) <= k:
        return cover
    return [cover[round(i * (len(cover) - 1) / (k - 1))] for i in range(k)]


def cmd_prep(a):
    job = os.path.join(ROOT, 'ai', a.job)
    shutil.rmtree(job, ignore_errors=True)
    os.makedirs(os.path.join(job, 'in'))
    meta = {}
    plan = {}
    for nid in a.ids.split(','):
        cov = cover_frames(nid)
        if not cov:
            continue
        keys = keyframes(cov, a.keys)
        d = os.path.join(ROOT, 'ai', 'npcj', nid)
        shutil.rmtree(d, ignore_errors=True)
        subprocess.run([PY, os.path.join(HERE, 'make_grids.py'), '--hero', f'npc_{nid}',
                        '--hero-dir', os.path.join(NPC_ROOT, nid), '--out', d,
                        '--frames', ','.join(f'npc:{f}' for f in keys), '--prefix', 'k'], check=True, capture_output=True)
        m = json.load(open(os.path.join(d, 'in', 'grids.json')))
        shutil.copy(os.path.join(d, 'in', 'grid_k00.png'), os.path.join(job, 'in', f'grid_{nid}.png'))
        meta[nid] = m['k00']
        plan[nid] = {'cover': cov, 'keys': keys}
        print(nid, 'cover', len(cov), 'keys', len(keys), flush=True)
    json.dump(meta, open(os.path.join(job, 'in', 'grids.json'), 'w'))
    json.dump(plan, open(os.path.join(job, 'plan.json'), 'w'))
    shutil.copy(os.path.join(ROOT, 'ai', 'or_test', 'in', 'ref_style.png'), os.path.join(job, 'in'))


def cmd_split(a):
    job = os.path.join(ROOT, 'ai', a.job)
    plan = json.load(open(os.path.join(job, 'plan.json')))
    tot = ok = 0
    for nid in plan:
        src = os.path.join(job, 'out', f'{nid}.png')
        d = os.path.join(ROOT, 'ai', 'npcj', nid)
        if not os.path.exists(src):
            print(nid, 'no output')
            continue
        os.makedirs(os.path.join(d, 'out'), exist_ok=True)
        shutil.copy(src, os.path.join(d, 'out', 'k00.png'))
        r = subprocess.run([PY, os.path.join(HERE, 'prod_fit.py'), '--job', d, '--hero', f'npc_{nid}',
                            '--hero-dir', os.path.join(NPC_ROOT, nid), '--out-tag', '_prod',
                            '--min-iou', str(a.min_iou), '--max-p95', '6'], capture_output=True, text=True)
        if not os.path.exists(os.path.join(d, 'qa.json')):
            print(nid, 'QA failed:', r.stderr[-300:])
            continue
        q = json.load(open(os.path.join(d, 'qa.json')))
        n_ok = len({r_['frame'] for r_ in q if r_['ok']})
        tot += len(plan[nid]['keys'])
        ok += n_ok
        print(nid, f'{n_ok}/{len(plan[nid]["keys"])} keyframes ok', flush=True)
    print('total', ok, '/', tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prep', 'split'])
    ap.add_argument('--ids', default='')
    ap.add_argument('--job', required=True)
    ap.add_argument('--keys', type=int, default=16)
    ap.add_argument('--npc-root', default='', help='folder with NPC pseudo-hero dirs (default extracted/npc; catalogue: extracted/npc_all)')
    ap.add_argument('--min-iou', type=float, default=0.85, help='massovka: silhouette comes from the original anyway')
    a = ap.parse_args()
    global NPC_ROOT
    if a.npc_root:
        NPC_ROOT = os.path.join(ROOT, a.npc_root)
    (cmd_prep if a.cmd == 'prep' else cmd_split)(a)


if __name__ == '__main__':
    main()
