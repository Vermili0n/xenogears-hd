"""Merge laptop klein redraws into the massovka NPCs: QA, replace accepted ebsynth fills, re-slice, project.

  python klein_merge_npc.py --klein ai/klein_npc [--min-iou 0.85 --max-p95 6 --min-redraw 10.5] [--dry]
For every NPC in jobs.json:
  prod_fit on ai/klein_npc/<nid> -> ai/npc_<nid>_klein/work (accepted frames only)
  accepted frames overwrite ai/npc_<nid>_prod/work/npc_<fi>_red.png (old ebsynth fill kept as *_ebs.png) and leave fills.json
  slice (--ring 1, remaining ebsynth fills low priority) -> project into ai/npc_pack
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(args):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-500:], r.stderr[-1500:])
        raise SystemExit('failed: ' + ' '.join(args[:2]))
    return r.stdout.strip().splitlines()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--klein', default='ai/klein_npc')
    ap.add_argument('--min-iou', default='0.85')
    ap.add_argument('--max-p95', default='6')
    ap.add_argument('--min-redraw', default='10.5')
    ap.add_argument('--pack-out', default='ai/npc_pack')
    ap.add_argument('--dry', action='store_true', help='QA only, do not touch ai/npc_*_prod')
    ap.add_argument('--nids', default='', help='comma list of NPC ids (default: all in jobs.json)')
    ap.add_argument('--src', default='out', help='out | out_hm (colour-matched by color_match.py --mode hist)')
    a = ap.parse_args()
    jobs = json.load(open(os.path.join(ROOT, a.klein, 'jobs.json')))
    nids = sorted({j['nid'] for j in jobs})
    if a.nids:
        nids = [n for n in nids if n in a.nids.split(',')]
    total = acc = 0
    for nid in nids:
        hd = f'extracted/npc/{nid}'
        run([os.path.join(HERE, 'prod_fit.py'), '--job', f'{a.klein}/{nid}', '--hero', f'npc_{nid}', '--hero-dir', hd,
             '--out-tag', '_klein', '--src', a.src, '--min-iou', a.min_iou, '--max-p95', a.max_p95, '--min-redraw', a.min_redraw])
        qa = json.load(open(os.path.join(ROOT, a.klein, nid, 'qa.json')))
        ok = [r['frame'] for r in qa if r['ok']]
        total += len(qa)
        acc += len(ok)
        print(f'{nid}: klein accepted {len(ok)}/{len(qa)}', flush=True)
        if a.dry:
            continue
        prod = os.path.join(ROOT, 'ai', f'npc_{nid}_prod', 'work')
        kw = os.path.join(ROOT, 'ai', f'npc_{nid}_klein', 'work')
        fp = os.path.join(prod, 'fills.json')
        fills = json.load(open(fp)) if os.path.exists(fp) else {}  # {frame: [keys]} of ebsynth fills
        for fi in ok:
            dst = os.path.join(prod, f'npc_{fi:03d}_red.png')
            if os.path.exists(dst) and not os.path.exists(dst[:-8] + '_ebs.png'):
                shutil.copy2(dst, dst[:-8] + '_ebs.png')
            shutil.copy2(os.path.join(kw, f'npc_{fi:03d}_red.png'), dst)
        fills = {k: v for k, v in fills.items() if int(k) not in set(ok)}
        json.dump(fills, open(fp, 'w'))
        frames = sorted(int(f.split('_')[1]) for f in os.listdir(prod) if f.endswith('_red.png'))
        only = ','.join(f'npc:{fi}' for fi in frames)
        low = ','.join(f'npc:{f}' for f in fills)
        shutil.rmtree(os.path.join(ROOT, 'ai', f'npc_{nid}_prod', 'parts'), ignore_errors=True)
        args = [os.path.join(HERE, 'batch_redraw.py'), 'slice', '--heroes', f'npc_{nid}', '--hero-dir', hd,
                '--out-tag', '_prod', '--ring', '1', '--only', only]
        if low:
            args += ['--low-priority', low]
        klein_all = sorted(set(ok) | {int(f[4:7]) for f in os.listdir(prod) if f.endswith('_ebs.png')})
        if klein_all:  # klein frames lose shared parts to keyframes, beat ebsynth fills
            args += ['--mid-priority', ','.join(f'npc:{fi}' for fi in klein_all)]
        print('  ', run(args)[-1])
        print('  ', run([os.path.join(HERE, 'npc_maps.py'), 'project', '--npc-dir', hd,
                         '--parts', f'ai/npc_{nid}_prod/parts', '--out', a.pack_out])[-1], flush=True)
    print(f'TOTAL klein accepted {acc}/{total}')


if __name__ == '__main__':
    main()
