"""Unattended production of redraws for a list of frames (runs locally, talks to <JUMP_HOST> over ssh).

  python produce.py --hero fei --job fei_scene --frames-file list.txt [--out-tag _prod]

Rounds (each frame stops at the first round where it passes prod_fit QA):
  1. 4x4 grids, Gemini 3 Pro 4K, Batch API (full references)
  2. 2x2 grids, Gemini 3 Pro 2K, Batch API, no face reference
  3. 2x2 grids, Seedream 5 Pro 2K (OpenRouter) and Nano Banana 2.1 2K (direct) - synchronous
  4. best round-3 candidate accepted with relaxed QA (IoU >= 0.85, contour p95 <= 6)
Passing frames land in ai/<hero><out-tag>/work. Report: ai/<job>/report.json.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=60', '<JUMP_HOST>']
REMOTE = '/root/xeno_jobs'
PY = sys.executable


def sh(cmd, key=None, check=True):
    """Run a local command; key (file path) is piped to stdin."""
    inp = open(key).read().strip() + '\n' if key else None
    r = subprocess.run(cmd, input=inp, text=True, capture_output=True)
    if check and r.returncode:
        raise RuntimeError(f'{cmd[:3]}... failed: {r.stderr[-800:]}')
    return r.stdout


def make(hero, job, frames, per, prefix):
    d = os.path.join(ROOT, 'ai', job)
    shutil.rmtree(d, ignore_errors=True)
    sh([PY, os.path.join(HERE, 'make_grids.py'), '--hero', hero, '--out', d, '--frames', ','.join(frames),
        '--per', str(per), '--prefix', prefix])
    for r in ('sheet', 'face', 'style'):
        shutil.copy(os.path.join(ROOT, 'ai', 'or_test', 'in', f'ref_{r}.png'), os.path.join(d, 'in'))
    sh(SSH + [f'rm -rf {REMOTE}/{job}; mkdir -p {REMOTE}/{job}/in'])
    sh(['scp', '-q', '-o', 'BatchMode=yes'] + glob.glob(os.path.join(d, 'in', '*')) + [f'<JUMP_HOST>:{REMOTE}/{job}/in/'])
    return d


def fetch(job, pattern='*.png'):
    d = os.path.join(ROOT, 'ai', job, 'out')
    os.makedirs(d, exist_ok=True)
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', f'<JUMP_HOST>:{REMOTE}/{job}/out/{pattern}', d + '/'],
                   capture_output=True)
    return d


def qa(hero, job, tag, relaxed=False):
    args = [PY, os.path.join(HERE, 'prod_fit.py'), '--job', os.path.join(ROOT, 'ai', job), '--hero', hero, '--out-tag', tag]
    if relaxed:
        args += ['--min-iou', '0.85', '--max-p95', '6']
    print(sh(args).strip().splitlines()[-1], flush=True)
    return json.load(open(os.path.join(ROOT, 'ai', job, 'qa.json')))


def batch_round(hero, job, frames, per, size, noface, tag, gkey):
    make(hero, job, frames, per, job[-2:])
    sub = ['cd /root/xeno_or && python3 gem_batch.py submit --dir', f'{REMOTE}/{job}', '--refs', f'{REMOTE}/{job}/in',
           '--model gemini-3-pro-image --size', size, '--name', job] + (['--noface'] if noface else [])
    print(sh(SSH + [' '.join(sub)], key=gkey).strip(), flush=True)
    print(sh(SSH + [f'cd /root/xeno_or && python3 gem_batch.py poll --dir {REMOTE}/{job} --wait'], key=gkey).strip()
          .splitlines()[-1], flush=True)
    fetch(job)
    return qa(hero, job, tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', required=True)
    ap.add_argument('--job', required=True)
    ap.add_argument('--frames-file', required=True, help='set:frame per line or comma separated')
    ap.add_argument('--out-tag', default='_prod')
    ap.add_argument('--gkey', default=os.path.join(ROOT, 'gemini_key.txt'))
    ap.add_argument('--okey', default=os.path.join(ROOT, 'key.txt'))
    ap.add_argument('--start-round', type=int, default=1)
    a = ap.parse_args()
    todo = [t.strip() for t in open(a.frames_file).read().replace('\n', ',').split(',') if t.strip()]
    todo = list(dict.fromkeys(todo))
    work = os.path.join(ROOT, 'ai', a.hero + a.out_tag, 'work')
    report = {'total': len(todo), 'rounds': []}

    def done(t):
        s, fi = t.split(':')
        return os.path.exists(os.path.join(work, f'{s}_{int(fi):03d}_red.png'))

    def left():
        return [t for t in todo if not done(t)]

    if a.start_round <= 1 and left():
        batch_round(a.hero, f'{a.job}_r1', left(), 16, '4K', False, a.out_tag, a.gkey)
        report['rounds'].append({'round': 1, 'left': len(left())})
    if a.start_round <= 2 and left():
        batch_round(a.hero, f'{a.job}_r2', left(), 4, '2K', True, a.out_tag, a.gkey)
        report['rounds'].append({'round': 2, 'left': len(left())})
    if a.start_round <= 3 and left():
        job = f'{a.job}_r3'
        rest = left()
        make(a.hero, job, rest, 4, 'm')
        R = f'{REMOTE}/{job}'
        grids = ','.join(sorted(json.load(open(os.path.join(ROOT, 'ai', job, 'in', 'grids.json')))))
        sh(SSH + [f'cd /root/xeno_or && python3 or_bakeoff.py --dir {R} --models bytedance-seed/seedream-5-0-pro '
                  f'--grids {grids} --res 2K --workers 4'], key=a.okey, check=False)
        sh(SSH + [f'cd /root/xeno_or && python3 gem_direct.py --dir {R} --model gemini-nano-banana-2.1 --grids {grids} '
                  f'--size 2K --tag nb'], key=a.gkey, check=False)
        src = fetch(job)
        cands = {}
        for m, pre, suf in (('sd', 'bytedance-seed_seedream-5-0-pro__', ''), ('nb', 'gemini-nano-banana-2.1__', '_nb')):
            jm = f'{job}_{m}'
            dm = os.path.join(ROOT, 'ai', jm)
            shutil.rmtree(dm, ignore_errors=True)
            shutil.copytree(os.path.join(ROOT, 'ai', job, 'in'), os.path.join(dm, 'in'))
            os.makedirs(os.path.join(dm, 'out'))
            for g in grids.split(','):
                p = os.path.join(src, f'{pre}{g}{suf}.png')
                if os.path.exists(p):
                    shutil.copy(p, os.path.join(dm, 'out', f'{g}.png'))
            for r in qa(a.hero, jm, a.out_tag):          # strict pass goes straight into work
                cands.setdefault(f"{r['set']}:{r['frame']}", []).append((m, r))
        report['rounds'].append({'round': 3, 'left': len(left())})
        # round 4: relaxed acceptance of the best remaining candidate (higher IoU wins)
        for t in left():
            best = max((c for c in cands.get(t, []) if c[1].get('iou')), key=lambda c: c[1]['iou'], default=None)
            if best and best[1]['iou'] >= 0.85 and best[1]['p95'] <= 6:
                jm = f'{job}_{best[0]}'
                qa(a.hero, jm, a.out_tag + 'x', relaxed=True)
                s, fi = t.split(':')
                p = os.path.join(ROOT, 'ai', a.hero + a.out_tag + 'x', 'work', f'{s}_{int(fi):03d}_red.png')
                if os.path.exists(p):
                    shutil.copy(p, work)
        report['rounds'].append({'round': 4, 'left': len(left())})
    report['missing'] = left()
    json.dump(report, open(os.path.join(ROOT, 'ai', f'{a.job}_report.json'), 'w'), indent=1)
    print('DONE', a.job, f"{report['total'] - len(report['missing'])}/{report['total']}", 'missing:', report['missing'], flush=True)


if __name__ == '__main__':
    main()
