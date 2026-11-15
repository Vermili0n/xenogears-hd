"""Post-training test set for LoRA v2: held-out frames (with boards) + random massovka frames (blank board, no-ref caption).

  python render_testset.py [--out ai/pod_v2/test2] [--per-job 8] [--mass 12]
"""
import argparse
import json
import os
import random
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v2 import ref_board, slug_of  # noqa: E402
from render_build import CAP_MECHA, CAP_NOREF, CAP_REF, groups  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'pod_v2', 'test2'))
    ap.add_argument('--per-job', type=int, default=8)
    ap.add_argument('--mass', type=int, default=12)
    a = ap.parse_args()
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    Image.new('RGB', (512, 512), (205, 205, 205)).save(os.path.join(a.out, 'boards', '_blank.png'))
    split = json.load(open(os.path.join(ROOT, 'ai', 'pairs_v2', 'split.json')))
    cj = json.load(open(os.path.join(ROOT, 'ai', 'campaign', 'jobs.json')))
    byjob = {}
    for n in split['test']:
        byjob.setdefault(n.split('__')[0], []).append(n)
    jobs = []
    for job, names in byjob.items():
        names = names[::max(1, len(names) // a.per_job)][:a.per_job]
        h = Hero(os.path.join(ROOT, cj[job]['hero_dir']))
        slug = slug_of(job)
        if slug and not os.path.exists(os.path.join(a.out, 'boards', slug + '.png')):
            ref_board(slug).save(os.path.join(a.out, 'boards', slug + '.png'))
        for n in names:
            setkey, fi = n.split('__')[1].rsplit('_', 1)
            place(frame_rgba(h, setkey, int(fi)), 512, 500).save(os.path.join(a.out, 'control', n + '.png'))
            jobs.append({'name': n, 'control': f'control/{n}.png', 'ref': f'boards/{slug or "_blank"}.png',
                         'prompt': CAP_REF if slug else CAP_MECHA})
    rnd = random.Random(7)
    mg = groups('massovka')
    for group, hd, _, _ in rnd.sample(mg, a.mass):
        h = Hero(hd)
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        fi = rnd.randrange(len(lay['npc']['frames']))
        n = f'{group}__npc_{fi:03d}'
        try:
            place(frame_rgba(h, 'npc', fi), 512, 500).save(os.path.join(a.out, 'control', n + '.png'))
        except Exception:  # noqa: BLE001
            continue
        jobs.append({'name': n, 'control': f'control/{n}.png', 'ref': 'boards/_blank.png', 'prompt': CAP_NOREF})
    for f in sorted(os.listdir(os.path.join(ROOT, 'ai', 'pod_v2', 'eval'))):  # the 6 massovka frames of the training samples
        if f.startswith('mass_') and f.endswith('_c.png'):
            n = f[:-6]
            Image.open(os.path.join(ROOT, 'ai', 'pod_v2', 'eval', f)).save(os.path.join(a.out, 'control', n + '.png'))
            jobs.append({'name': n, 'control': f'control/{n}.png', 'ref': 'boards/_blank.png', 'prompt': CAP_NOREF})
    json.dump(jobs, open(os.path.join(a.out, 'jobs.json'), 'w'), indent=0)
    print('test jobs', len(jobs))


if __name__ == '__main__':
    main()
