"""Install of 03.11: Maison without the mustache, the eyepatch of Bart and Sigurd. RetroArch must be closed.

  python install_0311.py [--step prepare,npc,finish,rects,bart]        log: pod/report/install_0311.log
prepare  head renders + head-only map -> ai/redraw/install_0311 (current renders kept in before/ with undo_map.json)
npc      tools/fix_apply.py: the story groups are rebuilt from res_prod with the new heads, merge_shared
finish   tools/redraw_finish.py: PNG -> BC7, seam fill (old BC7 go to <DATA_DRIVE>\\xeno_redraw_backup\\<stamp>)
rects    draw-rect files of these sets are deleted (only names npc_rects itself wrote) and written again from the new blocks
bart     h_bart: only the staged parts (ai/prod_work/h_bart_patch/stage), backup in <DATA_DRIVE>\\xeno_redraw_backup\\bart_patch_<stamp>
Bart goes last and not through fix_apply: a rebuild of h_bart would undo the back-view fixes of 01.11.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from alias_dump_parts import PACK  # noqa: E402
from gear_redraw import write_bc7  # noqa: E402
from npc_rects import NPC, WRITTEN, part_rect, sheet_words  # noqa: E402

OUT = os.path.join(ROOT, 'ai', 'redraw', 'install_0311')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
LOG = os.path.join(ROOT, 'pod', 'report', 'install_0311.log')
EYE = os.path.join(ROOT, 'ai', 'redraw', 'eyepatch')
FINAL = os.path.join(ROOT, 'ai', 'redraw', 'eyepatch3', 'final', 'v4')
M1 = os.path.join(ROOT, 'ai', 'redraw', 'maison')
M2 = os.path.join(ROOT, 'ai', 'redraw', 'maison2')
BART = os.path.join(ROOT, 'ai', 'prod_work', 'h_bart_patch')
META = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'meta.json')))


def log(s):
    s = time.strftime('%d.%m %H:%M:%S ') + s
    print(s, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def running():
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq retroarch.exe'], capture_output=True, text=True)
    return 'retroarch.exe' in r.stdout.lower()


def run(cmd):
    log('run: ' + ' '.join(cmd[1:]))
    r = subprocess.run(cmd, cwd=TOOLS, capture_output=True, text=True, encoding='utf-8', errors='replace')
    for ln in (r.stdout.strip().splitlines() or [])[-25:]:
        log('   ' + ln)
    if r.returncode:
        log('FAILED: ' + r.stderr[-1500:])
        sys.exit(1)
    return r.stdout


def prepare():
    v4, before = os.path.join(OUT, 'v4'), os.path.join(OUT, 'before')
    os.makedirs(v4, exist_ok=True)
    os.makedirs(before, exist_ok=True)
    fmap = {}
    eye = json.load(open(os.path.join(EYE, 'map.json')))
    for rep, names in eye.items():
        if rep.endswith('__head') and not rep.startswith('h_bart'):
            shutil.copyfile(os.path.join(FINAL, rep + '.png'), os.path.join(v4, rep + '.png'))
            fmap[rep] = names
    mm = json.load(open(os.path.join(M1, 'map.json')))
    done = {f[:-4] for f in os.listdir(os.path.join(M2, 'm_7_60', 'v4'))}
    tips = {f[:-4] for f in os.listdir(os.path.join(M2, 'm2_7_60', 'v4'))}
    for rep in sorted(done):
        src = os.path.join(M2, 'm2_7_60' if rep in tips else 'm_7_60', 'v4', rep + '.png')
        shutil.copyfile(src, os.path.join(v4, rep + '.png'))
        fmap[rep] = mm[rep]
    every = sorted({n for v in fmap.values() for n in v})
    for n in every:
        shutil.copy2(os.path.join(RES, n + '.png'), os.path.join(before, n + '.png'))
    json.dump(fmap, open(os.path.join(OUT, 'map.json'), 'w'), indent=1)
    json.dump({n: [n] for n in every}, open(os.path.join(OUT, 'undo_map.json'), 'w'), indent=1)
    groups = sorted({META[n[:-6]]['group'] for n in every})
    json.dump(groups, open(os.path.join(OUT, 'groups.json'), 'w'), indent=1)
    log(f'prepared {len(fmap)} head renders for {len(every)} names, {len(groups)} groups: {groups}')


def rect_names(sid):
    d = os.path.join(NPC, sid)
    sheet = np.load(os.path.join(d, 'page.npy')).astype(np.uint16)
    lay = json.load(open(os.path.join(d, 'layout.json')))['npc']
    u = json.load(open(os.path.join(d, 'uses.json')))
    words = sheet_words(sheet)
    H = sheet.shape[0]
    out = set()
    for f in lay['frames']:
        for p in f:
            sx, sy, w, h = part_rect(p['block'])
            x0, ww, hh = sx >> 2, ((sx + w + 1) >> 2) - (sx >> 2), h - 1
            if ww > 0 and hh > 0 and sy + hh <= H and x0 + ww <= 64:
                crc = zlib.crc32(np.ascontiguousarray(words[sy:sy + hh, x0:x0 + ww]).astype('<u2').tobytes())
                out |= {f'{crc:x}-{pal}' for pal in u['palettes']}
    return out


def rects():
    groups = json.load(open(os.path.join(OUT, 'groups.json')))
    sets = sorted({os.path.basename(m['hero_dir']) for m in META.values() if m['group'] in groups})
    ours = {ln.strip() for ln in open(WRITTEN, encoding='utf-8')}
    bk = os.path.join(r'<DATA_DRIVE>\xeno_redraw_backup', 'rects_' + time.strftime('%Y-%m-%d_%H%M'))
    os.makedirs(bk, exist_ok=True)
    gone = 0
    for sid in sets:
        for nm in rect_names(sid) & ours:
            p = os.path.join(PACK, nm + '.bc7')
            if os.path.exists(p):
                shutil.move(p, os.path.join(bk, nm + '.bc7'))
                gone += 1
    log(f'rects: {gone} old files of {len(sets)} sets moved to {bk}')
    run([sys.executable, 'npc_rects.py', '--only', ','.join(sets)])


def bart():
    sel = json.load(open(os.path.join(BART, 'selected.json')))['parts']
    bk = os.path.join(r'<DATA_DRIVE>\xeno_redraw_backup', 'bart_patch_' + time.strftime('%Y-%m-%d_%H%M'))
    os.makedirs(bk, exist_ok=True)
    ok = 0
    for nm in sel:
        p = os.path.join(PACK, nm + '.bc7')
        if os.path.exists(p):
            shutil.copy2(p, bk)
        png = os.path.join(PACK, nm + '.png')
        if os.path.exists(png):      # PNG wins over BC7 in the core
            shutil.move(png, os.path.join(bk, nm + '.png'))
        rgba = np.asarray(Image.open(os.path.join(BART, 'stage', nm + '.png')).convert('RGBA'))
        ok += bool(write_bc7(p, rgba))
    log(f'bart: installed {ok}/{len(sel)} parts, backup {bk}')
    if ok != len(sel):
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--step', default='prepare,npc,finish,rects,bart')
    a = ap.parse_args()
    if running():
        sys.exit('RetroArch is running - close it first')
    t0 = time.time()
    for st in a.step.split(','):
        log('=== ' + st)
        if st == 'prepare':
            prepare()
        elif st == 'npc':
            out = run([sys.executable, 'fix_apply.py', os.path.join(OUT, 'v4'), '--map', os.path.join(OUT, 'map.json'), '--no-record'])
            if 'NOT installed' in out or ' not rendered: [\'' in out:
                log('FAILED: fix_apply did not install everything')
                sys.exit(1)
        elif st == 'finish':
            run([sys.executable, 'redraw_finish.py'])
        elif st == 'rects':
            rects()
        elif st == 'bart':
            bart()
    log(f'done in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
