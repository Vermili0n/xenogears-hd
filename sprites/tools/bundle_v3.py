"""Pod bundle + evaluation sets for LoRA v3.

  python bundle_v3.py [--pairs ai/pairs_v3] [--test ai/pairs_v3_test] [--out ai/pod_v3]
Writes:
  <out>/pod_bundle_v3.zip : pairs_v3/{control,target(+txt),mask}, boards/<md5>.png + ref_map.json (refs deduplicated),
                            eval/<name>_{c,r}.png + eval/samples.json (training-time samples, caption per type)
  <out>/test3/            : jobs.json + control/ ref/ target/ for infer_pod.py (held-out subset, teacher targets kept)
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from render_build import CAP_NOREF  # noqa: E402


def kind(n):
    if n.startswith('g_'):
        return 'gear'
    if n.endswith('__head'):
        return 'head'
    if n.endswith('__noref'):
        return 'noref'
    return 'npc' if n.startswith('n_') else 'full'


def owner(n):
    job = n.split('__')[0]
    return job


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pairs', default=os.path.join(ROOT, 'ai', 'pairs_v3'))
    ap.add_argument('--test', default=os.path.join(ROOT, 'ai', 'pairs_v3_test'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'pod_v3'))
    ap.add_argument('--test-full', type=int, default=8, help='full frames per held-out job in test3')
    ap.add_argument('--test-head', type=int, default=4, help='head crops per held-out job in test3')
    ap.add_argument('--tag', default='v3', help='bundle / folder name inside the zip: pod_bundle_<tag>.zip, pairs_<tag>/')
    ap.add_argument('--reuse-test', default='', help='existing test3 folder (jobs.json) to take the samples from')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    names = sorted(f[:-4] for f in os.listdir(os.path.join(a.pairs, 'target')) if f.endswith('.png'))
    if a.reuse_test:
        write_bundle(a, names, a.reuse_test, json.load(open(os.path.join(a.reuse_test, 'jobs.json'))))
        return
    tnames = sorted(f[:-4] for f in os.listdir(os.path.join(a.test, 'target')) if f.endswith('.png'))
    caps = {n: open(os.path.join(a.test, 'target', n + '.txt')).read() for n in tnames}

    # held-out subset per job and type
    by = {}
    for n in tnames:
        by.setdefault((owner(n), kind(n)), []).append(n)
    test = []
    for (job, k), ns in sorted(by.items()):
        per = a.test_head if k == 'head' else a.test_full
        test += ns[::max(1, len(ns) // per)][:per]
    # massovka check: held-out NPC full frames again with the blank board and the no-reference caption
    noref = [n for n in test if kind(n) == 'npc'][:6]
    t3 = os.path.join(a.out, 'test3')
    for d in ('control', 'ref', 'target'):
        os.makedirs(os.path.join(t3, d), exist_ok=True)
    jobs = []
    blank = None
    for n in test:
        for d in ('control', 'ref', 'target'):
            shutil.copyfile(os.path.join(a.test, d, n + '.png'), os.path.join(t3, d, n + '.png'))
        jobs.append({'name': n, 'control': f'control/{n}.png', 'ref': f'ref/{n}.png', 'target': f'target/{n}.png', 'prompt': caps[n]})
    for n in noref:
        if blank is None:
            blank = os.path.join(t3, 'ref', '_blank.png')
            shutil.copyfile(os.path.join(a.pairs, 'boards', '_blank.png'), blank)
        jobs.append({'name': n + '__noref', 'control': f'control/{n}.png', 'ref': 'ref/_blank.png', 'target': f'target/{n}.png',
                     'prompt': CAP_NOREF})
    json.dump(jobs, open(os.path.join(t3, 'jobs.json'), 'w'), indent=0)
    write_bundle(a, names, t3, jobs)


def write_bundle(a, names, t3, jobs):
    # training-time samples: a few of each type
    want = {'full': 6, 'head': 4, 'npc': 2, 'gear': 1}
    samples = []
    for k, cnt in want.items():
        pool = [j for j in jobs if kind(j['name']) == k]
        samples += pool[::max(1, len(pool) // cnt)][:cnt]
    samples += [j for j in jobs if j['name'].endswith('__noref')][:1]

    zp = os.path.join(a.out, f'pod_bundle_{a.tag}.zip')
    refmap, seen = {}, set()
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_STORED) as z:
        for n in names:
            for d in ('control', 'target', 'mask'):
                z.write(os.path.join(a.pairs, d, n + '.png'), f'pairs_{a.tag}/{d}/{n}.png')
            z.write(os.path.join(a.pairs, 'target', n + '.txt'), f'pairs_{a.tag}/target/{n}.txt')
            rp = os.path.join(a.pairs, 'ref', n + '.png')
            h = hashlib.md5(open(rp, 'rb').read()).hexdigest()
            if h not in seen:
                z.write(rp, f'boards/{h}.png')
                seen.add(h)
            refmap[n + '.png'] = h
        z.writestr('ref_map.json', json.dumps(refmap))
        for s in samples:
            z.write(os.path.join(t3, s['control']), f"eval/{s['name']}_c.png")
            z.write(os.path.join(t3, s['ref']), f"eval/{s['name']}_r.png")
        z.writestr('eval/samples.json', json.dumps([{'name': s['name'], 'prompt': s['prompt']} for s in samples]))
    print('train', len(names), 'boards', len(seen), 'test3 jobs', len(jobs), 'samples', len(samples),
          f'{os.path.getsize(zp) / 2**20:.0f} MB')


if __name__ == '__main__':
    main()
