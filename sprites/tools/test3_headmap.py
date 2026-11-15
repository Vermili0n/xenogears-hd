"""Head comparison support for test3: for every head crop in test3, make sure the full frame of the same sprite frame is
rendered too (v3 jobs.json and v2 jobs_v2.json), and record where the head window sits on the 512 full canvas.

  python test3_headmap.py [--test ai/pod_v3/test3] [--src ai/pairs_v3_test] [--boards ai/pairs_v3/boards]
headmap.json: {head_name: {"full": full_name, "box": [x0, y0, x1, y1]}} (box on the full-frame canvas, = 32 native px).
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_pairs_v2 import slug_of  # noqa: E402
from make_pairs_v3 import HEAD_N, head_window, load_index  # noqa: E402
from render_build import CAP_NOREF  # noqa: E402


def canvas_box(h, setkey, fi, size=512, feet=500):
    places = h.placements(setkey, fi)
    img, _ = h.assemble(places)
    w8, h8 = img.width * 8, img.height * 8
    k = min(feet / h8, size / w8, 1.0)
    ox, oy = (size - int(w8 * k)) // 2, feet - int(h8 * k)
    x0, y0 = head_window(h, setkey, fi)
    s = 8 * k
    return [round(ox + x0 * s), round(oy + y0 * s), round(ox + (x0 + HEAD_N) * s), round(oy + (y0 + HEAD_N) * s)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', default=os.path.join(ROOT, 'ai', 'pod_v3', 'test3'))
    ap.add_argument('--src', default=os.path.join(ROOT, 'ai', 'pairs_v3_test'))
    ap.add_argument('--boards', default=os.path.join(ROOT, 'ai', 'pairs_v3', 'boards'))
    a = ap.parse_args()
    idx = load_index()
    heroes = {}
    jobs = json.load(open(os.path.join(a.test, 'jobs.json')))
    jobs2 = json.load(open(os.path.join(a.test, 'jobs_v2.json')))
    have, have2 = {j['name'] for j in jobs}, {j['name'] for j in jobs2}
    hmap = {}
    for j in [j for j in jobs if j['name'].endswith('__head')]:
        full = j['name'][:-6]
        job, rest = full.split('__')
        setkey, fi = rest.rsplit('_', 1)
        hd = idx[job]['hero_dir']
        heroes.setdefault(hd, Hero(os.path.join(ROOT, hd)))
        hmap[j['name']] = {'full': full, 'box': canvas_box(heroes[hd], setkey, int(fi))}
        if full not in have:
            for d in ('control', 'ref', 'target'):
                shutil.copyfile(os.path.join(a.src, d, full + '.png'), os.path.join(a.test, d, full + '.png'))
            jobs.append({'name': full, 'control': f'control/{full}.png', 'ref': f'ref/{full}.png', 'target': f'target/{full}.png',
                         'prompt': open(os.path.join(a.src, 'target', full + '.txt')).read()})
            have.add(full)
        if full not in have2:
            k = {'name': full, 'control': f'control/{full}.png', 'target': f'target/{full}.png'}
            if job.startswith('n_'):
                k.update(ref='ref/_blank.png', prompt=CAP_NOREF)
            else:
                b = slug_of(job) + '@v2.png'
                if not os.path.exists(os.path.join(a.test, 'ref', b)):
                    shutil.copyfile(os.path.join(a.boards, b), os.path.join(a.test, 'ref', b))
                k.update(ref='ref/' + b, prompt=open(os.path.join(a.src, 'target', full + '.txt')).read())
            jobs2.append(k)
            have2.add(full)
    json.dump(jobs, open(os.path.join(a.test, 'jobs.json'), 'w'), indent=0)
    json.dump(jobs2, open(os.path.join(a.test, 'jobs_v2.json'), 'w'), indent=0)
    json.dump(hmap, open(os.path.join(a.test, 'headmap.json'), 'w'), indent=0)
    print('heads', len(hmap), 'v3 jobs', len(jobs), 'v2 jobs', len(jobs2))


if __name__ == '__main__':
    main()
