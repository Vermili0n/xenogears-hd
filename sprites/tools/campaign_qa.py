"""QA every finished campaign grid with prod_fit (silhouette IoU + contour p95 + 'redrawn' score) -> per-job verdict.

  python campaign_qa.py [--fetch] [--workers 8] [--only m_]   -> ai/campaign/_qa.json {job: {ok, total, bad_grids}}
--fetch first copies new outputs from <JUMP_HOST>. A grid is 'bad' if fewer than 12 of its 16 cells pass (then the grid is redone).
prod_fit runs in parallel worker processes (one job each); results are merged into _qa.json at the end.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
C = os.path.join(ROOT, 'ai', 'campaign')


def run_fit(job, v):
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENCV_FOR_THREADS_NUM='1')
    return subprocess.run([sys.executable, os.path.join(HERE, 'prod_fit.py'), '--job', os.path.join(C, job), '--hero', job,
                           '--hero-dir', os.path.join(ROOT, v['hero_dir']), '--out-tag', '_keys', '--min-iou', '0.88', '--max-p95', '6']
                          + (['--min-redraw', '6'] if job.startswith('m_') else []),  # flat townsfolk / animals differ little from the sprite
                          capture_output=True, text=True, env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch', action='store_true')
    ap.add_argument('--min-cells', type=int, default=12)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--only', default='', help='job name prefix')
    a = ap.parse_args()
    if a.fetch:
        lst = subprocess.run(['ssh', '-o', 'ConnectTimeout=15', '<JUMP_HOST>', 'ls /root/xeno_jobs/campaign/*/out/g*.png /root/xeno_jobs/campaign/*/out/e*.png /root/xeno_jobs/campaign/*/out/b*.png 2>/dev/null'],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.split()
        for p in lst:
            job, f = p.split('/')[-3], p.split('/')[-1]
            dst = os.path.join(C, job, 'out', f)
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                subprocess.run(['scp', '-q', f'<JUMP_HOST>:{p}', dst], stdin=subprocess.DEVNULL)
    jobs = json.load(open(os.path.join(C, 'jobs.json')))
    qa_all = json.load(open(os.path.join(C, '_qa.json'))) if os.path.exists(os.path.join(C, '_qa.json')) else {}
    todo = []
    for job, v in sorted(jobs.items()):
        if a.only and not job.startswith(a.only):
            continue
        outd = os.path.join(C, job, 'out')
        meta_p = os.path.join(C, job, 'in', 'grids.json')
        if not os.path.isdir(outd) or not os.path.exists(meta_p):
            continue
        meta = json.load(open(meta_p))
        if not all(os.path.exists(os.path.join(outd, f'{g}.png')) for g in meta):
            continue
        if job in qa_all and qa_all[job].get('grids_seen') == len(meta):
            continue
        todo.append((job, v, len(meta)))
    print('jobs to check', len(todo), flush=True)
    with ThreadPoolExecutor(max(1, a.workers)) as ex:
        results = list(ex.map(lambda t: (t, run_fit(t[0], t[1])), todo))
    for (job, v, ngrids), r in results:
        qp = os.path.join(C, job, 'qa.json')
        if not os.path.exists(qp):
            qa_all[job] = {'error': r.stderr[-300:]}
            continue
        q = json.load(open(qp))
        per = defaultdict(lambda: [0, 0])
        for rec in q:
            per[rec['grid']][1] += 1
            per[rec['grid']][0] += bool(rec['ok'])
        bad = [g for g, (ok, n) in per.items() if ok < min(a.min_cells, n)]
        qa_all[job] = {'ok': sum(x[0] for x in per.values()), 'total': sum(x[1] for x in per.values()), 'bad_grids': bad,
                       'per_grid': {g: f'{ok}/{n}' for g, (ok, n) in per.items()}, 'grids_seen': ngrids}
        print(job, qa_all[job]['ok'], '/', qa_all[job]['total'], 'bad grids:', bad, flush=True)
    json.dump(qa_all, open(os.path.join(C, '_qa.json'), 'w'), indent=1)
    nb = sum(len(v.get('bad_grids', [])) for v in qa_all.values())
    print('jobs checked', len(qa_all), 'bad grids', nb)


if __name__ == '__main__':
    main()
