"""Install colour-corrected frames of an already built group: copy pod/report/qa/color/<src>_<group>/*_red.png over
ai/prod_work/<group>/work (originals once to work_before_color/), then the post-compose chain of prod_post.one
(slice -> npc_maps project for map NPCs -> install_parts). Run merge_shared.py afterwards.
The group's DONE marker stays; a later prod_post rebuild would recompose and LOSE the correction - re-run then.

  python apply_color.py <group> [--src hair]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')


def run(cmd, log):
    with open(log, 'a') as f:
        f.write('$ ' + ' '.join(cmd) + '\n')
        f.flush()
        return subprocess.run(cmd, cwd=TOOLS, stdout=f, stderr=subprocess.STDOUT).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('group')
    ap.add_argument('--src', default='hair')
    a = ap.parse_args()
    g = a.group
    gd = os.path.join(ROOT, 'ai', 'prod_work', g)
    work, bk = os.path.join(gd, 'work'), os.path.join(gd, 'work_before_color')
    src = os.path.join(ROOT, 'pod', 'report', 'qa', 'color', f'{a.src}_{g}')
    os.makedirs(bk, exist_ok=True)
    fixed = sorted(glob.glob(os.path.join(src, '*_red.png')))
    for p in fixed:
        dst = os.path.join(work, os.path.basename(p))
        if not os.path.exists(os.path.join(bk, os.path.basename(p))):
            shutil.copy2(dst, bk)
        shutil.copyfile(p, dst)
    meta = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))
    hd = os.path.join(ROOT, next(m['hero_dir'] for m in meta.values() if m['group'] == g))
    log = os.path.join(gd, 'color.log')
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    tag = os.path.relpath(gd, os.path.join(ROOT, 'ai')).replace('\\', '/')
    if run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', tag, '--hero-dir', hd, '--scale', '8', '--exact-mask',
            '--ring', '0', '--uv-compensate', '--only', only], log):
        sys.exit(f'{g}: slice failed, see {log}')
    stage = open(os.path.join(gd, 'DONE')).read().strip()
    if os.path.normpath(hd).split(os.sep)[-2] in ('npc_full', 'npc_all', 'npc_all_d2'):
        if run([sys.executable, 'npc_maps.py', 'project', '--npc-dir', hd, '--parts', os.path.join(gd, 'parts'), '--out',
                os.path.join(gd, 'stage'), '--scale', '8'], log):
            sys.exit(f'{g}: project failed, see {log}')
    r = subprocess.run([sys.executable, 'install_parts.py', '--parts', stage], cwd=TOOLS, capture_output=True, text=True)
    print(f'{g}: {len(fixed)} corrected frames, {r.stdout.strip() or r.stderr[-200:]}')


if __name__ == '__main__':
    main()
