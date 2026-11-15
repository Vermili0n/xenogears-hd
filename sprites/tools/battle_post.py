"""Post-processing of battle sets drawn without a board: as prod_post.py, but colours are anchored to the sprite
(compose_set.py --color-mode anchor): without a board the model's colours drift from frame to frame.

  python battle_post.py --prod ai/redraw/battle_rest --res ai/redraw/battle_rest/res [--only g1,g2] [--workers 12]
                        [--all] [--work ai/prod_work_self]
Groups: those whose jobs use boards/_blank.png (--only narrows the list); --all = every group of the folder (a second
render with self boards, battle_boards.py). --work: another work root, so that the first run's parts stay untouched. Parts of an earlier run are kept as
ai/prod_work/<group>/parts_v1 (and parts_v1_magenta); then fix_magenta.py and battle_sheet.py as usual.
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from prod_post import WORK, run  # noqa: E402


def one(args):
    g, hero_dir, prod, res, root = args
    gd = os.path.join(root, g)
    work = os.path.join(gd, 'work')
    os.makedirs(work, exist_ok=True)
    log = os.path.join(gd, 'post.log')
    for d in ('parts', 'parts_magenta'):
        old, keep = os.path.join(gd, d), os.path.join(gd, d.replace('parts', 'parts_v1'))
        if os.path.isdir(old) and not os.path.exists(keep):
            os.rename(old, keep)
    if os.path.exists(os.path.join(gd, 'DONE')):
        os.remove(os.path.join(gd, 'DONE'))
    if run([sys.executable, 'compose_set.py', '--render', prod, '--res', os.path.join(res, 'v4'), '--work', work,
            '--name', g, '--out-scale', '8', '--color-mode', 'anchor', '--no-color', '--no-head'], log):
        return g, 'compose failed'
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    if not reds:
        return g, 'no renders'
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    tag = os.path.relpath(gd, os.path.join(ROOT, 'ai')).replace('\\', '/')
    if run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', tag, '--hero-dir', os.path.join(ROOT, hero_dir), '--scale', '8',
            '--exact-mask', '--ring', '0', '--uv-compensate', '--only', only], log):
        return g, 'slice failed'
    parts = os.path.join(gd, 'parts')
    open(os.path.join(gd, 'DONE'), 'w').write(parts)
    return g, f'ok {len(reds)} frames -> {len(os.listdir(parts))} files'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prod', required=True)
    ap.add_argument('--res', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--work', default=WORK)
    a = ap.parse_args()
    a.work = os.path.abspath(a.work)
    a.prod, a.res = os.path.abspath(a.prod), os.path.abspath(a.res)  # workers run from tools/
    meta = json.load(open(os.path.join(a.prod, 'meta.json')))
    blank = {j['name'] for j in json.load(open(os.path.join(a.prod, 'jobs.json'))) if j['ref'].endswith('_blank.png')}
    groups = {m['group']: m['hero_dir'] for n, m in meta.items() if a.all or n in blank}
    todo = sorted(g for g in groups if not a.only or g in set(a.only.split(',')))
    print('groups', len(todo), flush=True)
    with Pool(a.workers) as pool:
        for k, (g, st) in enumerate(pool.imap_unordered(one, [(g, groups[g], a.prod, a.res, a.work) for g in todo])):
            print(f'[{k + 1}/{len(todo)}] {g}: {st}', flush=True)


if __name__ == '__main__':
    main()
