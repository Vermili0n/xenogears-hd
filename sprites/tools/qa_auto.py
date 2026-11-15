"""Auto QA of the "back view drawn with a face" bug for production groups whose renders are all downloaded.

  python qa_auto.py [--groups g1,g2]      default: every newly complete group (prod_sync.complete_groups), gears/battle skipped

Per run: fill_dups -> compose (same arguments as prod_post, writes only ai/prod_work/<g>/work, no DONE, nothing installed;
groups that already have DONE are not recomposed) -> qa_backview sieve -> qa_zoom sheets for eye review:
  * frames the sieve flags, plus every frame whose ORIGINAL head has no skin (back views - the only frames where the bug can be);
  * groups where the sieve cannot calibrate (no skin colour / too few face pixels): every frame.
State (groups already sieved): pod/report/qa/auto/state.json; sheets: pod/report/qa/z_<g>_auto_<n>.png.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from multiprocessing import Pool

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import prod_sync  # noqa: E402
from prod_post import HEROES  # noqa: E402

PROD = os.path.join(ROOT, 'ai', 'prod')
WORK = os.path.join(ROOT, 'ai', 'prod_work')
QA = os.path.join(ROOT, 'pod', 'report', 'qa')
OUT = os.path.join(QA, 'auto')
ZOOM = os.path.join(TOOLS, 'qa_zoom.py')
STATE = os.path.join(OUT, 'state.json')
ENV = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')


def offset_key(g):  # same rule as prod_post.one
    if g.startswith('h_'):
        return g[2:].split('_')[0]
    if g.startswith('c_') and g[2:-7] in HEROES:
        return g[2:-7]
    return g


def compose(args):
    g, kind = args
    work = os.path.join(WORK, g, 'work')
    os.makedirs(work, exist_ok=True)
    cmd = [sys.executable, 'compose_set.py', '--render', PROD, '--res', os.path.join(prod_sync.RES, 'v4'), '--work', work,
           '--name', g, '--out-scale', '8', '--offset-key', offset_key(g)]
    if kind != 'hero':
        cmd.append('--no-head')
    with open(os.path.join(WORK, g, 'qa_compose.log'), 'a') as f:
        r = subprocess.run(cmd, cwd=TOOLS, stdout=f, stderr=subprocess.STDOUT, env=ENV)
    return g, r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--groups', default='')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    meta = json.load(open(os.path.join(PROD, 'meta.json')))
    kind = {m['group']: m['kind'] for m in meta.values()}
    prod_sync.fill_dups()
    if a.groups:
        groups = a.groups.split(',')
    else:
        ready, _, _ = prod_sync.complete_groups()
        groups = [g for g in ready if g not in state and not g.startswith(('g_', 'b_'))]
    if not groups:
        print('QA: no new complete groups')
        return
    todo = [(g, kind[g]) for g in groups if not os.path.exists(os.path.join(WORK, g, 'DONE'))]
    with Pool(5) as pool:   # ~1.5-2 GB commit each; 8 ran the PC out of commit with Firefox open (29.10)
        bad = [g for g, rc in pool.imap_unordered(compose, todo) if rc]
    groups = [g for g in groups if g not in bad]

    stamp = time.strftime('%m%d_%H%M')
    csv = os.path.join(OUT, f'bv_{stamp}.csv')
    r = subprocess.run([sys.executable, 'qa_backview.py'] + groups + ['--csv', csv], cwd=TOOLS, capture_output=True,
                       text=True, env=ENV)
    notes = {ln.split(':')[0]: ln for ln in r.stdout.splitlines() if ':' in ln}
    rows = {}
    for ln in open(csv) if os.path.exists(csv) else []:
        g, s, f, ss, rr, fl = ln.strip().split(',')
        rows.setdefault(g, []).append((s, int(f), float(ss), float(rr), fl == '1'))

    sel_csv = os.path.join(OUT, f'sel_{stamp}.csv')
    sel = open(sel_csv, 'w')
    summary = []
    for g in groups:
        work = os.path.join(WORK, g, 'work')
        gr = rows.get(g, [])
        flagged = [(s, f) for s, f, ss, rr, fl in gr if fl]
        # every rendered frame goes on the sheets (the sieve's "no skin in the original head" misses real back views:
        # neck/ears/hair count as skin - h_bart field/scene sets had none); sieve candidates are listed in state.json
        pick = sorted({(m['set'], m['frame']) for m in meta.values() if m['group'] == g and
                       os.path.exists(os.path.join(work, f"{m['set']}_{m['frame']:03d}_red.png"))})
        mode = 'all' if gr else 'all, sieve not calibrated'
        for s, f in pick:  # qa_zoom csv: takes lines ending in ,1
            sel.write(f'{g},{s},{f},0,0,1\n')
        state[g] = dict(mode=mode, frames=len(gr), flagged=[f'{s}:{f}' for s, f in flagged], shown=len(pick),
                        note=notes.get(g, 'no sieve output'), sheets=[], reviewed=False)
    sel.close()
    for g in groups:
        if not state[g]['shown']:
            continue
        for old in glob.glob(os.path.join(QA, f'z_{g}_head_*.png')):
            os.remove(old)
        z = subprocess.run([sys.executable, ZOOM, g, 'csv:' + sel_csv, '--crop-top', '0.35', '--h', '100', '--tag', '_head'], cwd=TOOLS,
                           capture_output=True, text=True, env=ENV)
        state[g]['sheets'] = [ln.split()[0] for ln in z.stdout.splitlines() if '.png' in ln]
        if z.returncode:
            state[g]['note'] += ' | zoom failed: ' + z.stderr[-200:]
    json.dump(state, open(STATE, 'w'), ensure_ascii=False, indent=1)
    for g in groups:
        st = state[g]
        summary.append(f"{g}: {st['mode']}, shown {st['shown']}, flagged {len(st['flagged'])}, sheets {len(st['sheets'])}")
    sheets = sum(len(state[g]['sheets']) for g in groups)
    print(f'QA: {len(groups)} groups, {sheets} sheets to review' + (f', compose failed: {bad}' if bad else ''))
    print('\n'.join(summary))


if __name__ == '__main__':
    main()
