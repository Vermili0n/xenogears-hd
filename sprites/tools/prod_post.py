"""Production post-processing: renders -> compose (8x, head pass for heroes) -> slice (8x, exact masks, game UV
compensation) -> map NPC sheets (npc_maps project) -> staging dir per group. Groups run in parallel, each in its
own work dir, so nothing is shared between workers.

  python prod_post.py --prod ai/prod --res pod/report/prod/res_prod [--only g1,g2] [--workers 12] [--install]
--res holds v4/ and v2/ (infer_pod output tags). Done groups are skipped (ai/prod_work/<group>/DONE).
--install copies every finished group's staging files into the HD pack (install_parts.py rules: originals backed up).
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, 'ai', 'prod_work')
HEROES = {'fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria'}


def run(cmd, log):
    with open(log, 'a') as f:
        f.write('$ ' + ' '.join(cmd) + '\n')
        f.flush()
        r = subprocess.run(cmd, cwd=HERE, stdout=f, stderr=subprocess.STDOUT,
                           env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
    return r.returncode


def one(args):
    g, info, prod, res = args
    gd = os.path.join(WORK, g)
    if os.path.exists(os.path.join(gd, 'DONE')):
        return g, 'skip'
    work = os.path.join(gd, 'work')
    os.makedirs(work, exist_ok=True)
    log = os.path.join(gd, 'post.log')
    hd = os.path.join(ROOT, info['hero_dir'])
    sub = 'v2' if info['kind'] == 'gear' else 'v4'
    # teacher colour offset key (color_local.teacher_offsets): heroes by slug, campaign story jobs by job name;
    # story sets found among map NPCs (c_<hero>_<id6>) use their hero's offset; anything unknown -> global
    off = g
    if g.startswith('h_'):
        off = g[2:].split('_')[0]
    elif g.startswith('c_') and g[2:-7] in HEROES:
        off = g[2:-7]
    cmd = [sys.executable, 'compose_set.py', '--render', prod, '--res', os.path.join(res, sub), '--work', work,
           '--name', g, '--out-scale', '8', '--offset-key', off]
    if info['kind'] != 'hero':
        cmd.append('--no-head')
    if run(cmd, log):
        return g, 'compose failed'
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    if not reds:
        return g, 'no renders'
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    # slice writes to ai/<heroes><out-tag>/parts; heroes = prod_work/<g> relative to ai/
    tag = os.path.relpath(gd, os.path.join(ROOT, 'ai')).replace('\\', '/')
    if run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', tag, '--hero-dir', hd, '--scale', '8', '--exact-mask',
            '--ring', '0', '--uv-compensate', '--only', only], log):
        return g, 'slice failed'
    parts = os.path.join(gd, 'parts')
    stage = os.path.join(gd, 'stage')
    if os.path.normpath(hd).split(os.sep)[-2] in ('npc_full', 'npc_all', 'npc_all_d2'):
        if run([sys.executable, 'npc_maps.py', 'project', '--npc-dir', hd, '--parts', parts, '--out', stage, '--scale', '8'], log):
            return g, 'project failed'
    else:
        stage = parts  # heroes / world-map gears: parts already carry the game's texture names
    open(os.path.join(gd, 'DONE'), 'w').write(stage)
    return g, f'ok {len(reds)} frames -> {len(os.listdir(stage))} files'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prod', default=os.path.join(ROOT, 'ai', 'prod'))
    ap.add_argument('--res', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--install', action='store_true')
    a = ap.parse_args()
    a.prod, a.res = os.path.abspath(a.prod), os.path.abspath(a.res)  # workers run from tools/
    meta = json.load(open(os.path.join(a.prod, 'meta.json')))
    groups = defaultdict(lambda: {'n': 0})
    for name, m in meta.items():
        g = groups[m['group']]
        g.update(hero_dir=m['hero_dir'], kind=m['kind'])
        g['n'] += 1
    todo = sorted(groups)
    if a.only:
        todo = [g for g in todo if g in set(a.only.split(','))]
    print('groups', len(todo), flush=True)
    with Pool(a.workers) as pool:
        for k, (g, st) in enumerate(pool.imap_unordered(one, [(g, groups[g], a.prod, a.res) for g in todo])):
            print(f'[{k + 1}/{len(todo)}] {g}: {st}', flush=True)
    if a.install:
        for g in todo:
            dp = os.path.join(WORK, g, 'DONE')
            if os.path.exists(dp):
                stage = open(dp).read().strip()
                r = subprocess.run([sys.executable, os.path.join(HERE, 'install_parts.py'), '--parts', stage],
                                   capture_output=True, text=True)
                print(g, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:], flush=True)


if __name__ == '__main__':
    main()
