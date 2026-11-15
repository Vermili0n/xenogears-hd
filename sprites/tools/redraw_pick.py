"""Pick frames for a manual re-render (01.11.2026): a job folder for the pod + maps for fix_apply.py.

  python redraw_pick.py <pattern>[,<pattern>...] [--hint "<text>"] [--seed 7] [--out ai/redraw/<name>]
<pattern>: a frame job name of ai/prod/jobs_v4.json or an fnmatch pattern over them: h_elly__428_0_045,
h_elly__428_0_04?, h_elly (a bare group = every frame of it). The head close-up (<name>__head) goes along when it exists.
Frames whose control image is byte-identical (same board) are rendered once and copied to all of them (as fix_jobs.py).
--hint is appended to the prompt of every job. The seed must differ from the production seed 42: with the same
prompt and seed the pod draws the very same picture again.
The folder gets jobs.json, control/ + boards/ (only what the jobs use), map.json (rendered -> all names), before/ (the
current renders of all names) + undo_map.json, and README.txt with the pod / install commands for this folder.
Gears (LoRA v2 jobs) are not handled here.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')
RES = os.path.join(ROOT, 'pod', 'report', 'prod', 'res_prod', 'v4')
SEC_PER_JOB = 15  # L40S, 28 steps (Elly copy run 01.11)

README = r"""Re-render {name}: {n_frames} frames ({n_names} with twins) + head close-ups -> {n_jobs} jobs, about {eta} min on one L40S.
Seed {seed}{hint_line}

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY> or ~/.ssh/<SSH_KEY>).
Run from the xeno_sprites folder in PowerShell.

1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (repeat until SETUP_OK, ~10 min)

2. Upload and render:
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r {rel} root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup sh -c 'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{name}/jobs.json --out redraw/{name}/res --crop --cfg 4 --seed {seed} --lora lora/xeno_klein_v4.safetensors; echo RENDER_DONE' > redraw/{name}/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/{name}/infer.log; ls /workspace/redraw/{name}/res/v4 | wc -l"
   (done: RENDER_DONE and {n_jobs} files)

3. Download, then stop the pod in RunPod:
   scp -P PORT -r root@HOST:/workspace/redraw/{name}/res {rel}\

4. Look at the renders by eye: {rel}\res\v4\*.png (compare with {rel}\before\)

5. Install (RetroArch closed):
   python tools\fix_apply.py {rel}\res\v4 --map {rel}\map.json --no-record
   python tools\redraw_finish.py
   Check in game. Previews of the sliced frames: ai\prod_work\<group>\frames\

Undo (RetroArch closed):
   python tools\fix_apply.py {rel}\before --map {rel}\undo_map.json --no-record
   python tools\redraw_finish.py
"""


def md5(path):
    return hashlib.md5(open(path, 'rb').read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('patterns')
    ap.add_argument('--hint', default='')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    if a.seed == 42 and not a.hint:
        ap.error('seed 42 without a hint repeats the production render exactly - pick another --seed')
    jobs = {j['name']: j for j in json.load(open(os.path.join(PROD, 'jobs_v4.json')))}
    gears = {j['name'] for j in json.load(open(os.path.join(PROD, 'jobs_v2.json')))}
    frames = [n for n in jobs if not n.endswith('__head')]
    picked = set()
    for pat in a.patterns.split(','):
        pat = pat.strip()
        if '__' not in pat and not any(c in pat for c in '*?['):
            pat += '__*'
        hit = fnmatch.filter(frames, pat)
        if not hit:
            g = fnmatch.filter(gears, pat)
            sys.exit(f'{pat}: ' + ('gear (LoRA v2) frames are not handled by this script' if g else 'no such frame'))
        picked |= set(hit)
    # twins: same control bytes + same board; only files of a picked size are hashed
    size = {n: os.path.getsize(os.path.join(PROD, jobs[n]['control'])) for n in frames}
    want = {size[n] for n in picked}
    key = {n: (md5(os.path.join(PROD, jobs[n]['control'])), jobs[n]['ref']) for n in frames if size[n] in want}
    cases = defaultdict(list)
    for n in sorted(key):
        cases[key[n]].append(n)
    hint = '' if not a.hint else (a.hint if a.hint.startswith(',') else ', ' + a.hint)
    out_jobs, fmap = [], {}
    for k in sorted({key[n] for n in picked}):
        names = cases[k]
        rep = min(n for n in names if n in picked)
        for suffix in ('', '__head'):
            if rep + suffix not in jobs:
                continue
            out_jobs.append(dict(jobs[rep + suffix], prompt=jobs[rep + suffix]['prompt'] + hint))
            fmap[rep + suffix] = [n + suffix for n in names if n + suffix in jobs]
    name = os.path.basename(os.path.normpath(a.out)) if a.out else time.strftime('%Y%m%d_%H%M')
    out = a.out or os.path.join(ROOT, 'ai', 'redraw', name)
    if os.path.exists(os.path.join(out, 'jobs.json')):
        sys.exit(f'{out} already has jobs.json - pick another --out')
    for d in ('control', 'boards', 'before'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    for j in out_jobs:
        for f in (j['control'], j['ref']):
            dst = os.path.join(out, f)
            if not os.path.exists(dst):
                shutil.copyfile(os.path.join(PROD, f), dst)
    every = sorted(n for names in fmap.values() for n in names)
    for n in every:
        src = os.path.join(RES, n + '.png')
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(out, 'before', n + '.png'))
    json.dump(out_jobs, open(os.path.join(out, 'jobs.json'), 'w'), indent=1)
    json.dump(fmap, open(os.path.join(out, 'map.json'), 'w'), indent=1)
    json.dump({n: [n] for n in every if os.path.exists(os.path.join(out, 'before', n + '.png'))},
              open(os.path.join(out, 'undo_map.json'), 'w'), indent=1)
    try:
        rel = os.path.relpath(out, ROOT)
    except ValueError:  # another drive
        rel = out
    n_frames = sum(1 for n in fmap if not n.endswith('__head'))
    n_names = sum(1 for n in every if not n.endswith('__head'))
    text = README.format(name=name, rel=rel, n_frames=n_frames, n_names=n_names, n_jobs=len(out_jobs),
                         eta=max(1, len(out_jobs) * SEC_PER_JOB // 60), seed=a.seed,
                         hint_line=f', hint: "{hint[2:]}"' if hint else ', no hint')
    open(os.path.join(out, 'README.txt'), 'w', encoding='utf-8').write(text)
    print(f'{len(picked)} frames picked, {n_frames} to render (+heads) = {len(out_jobs)} jobs '
          f'(~{max(1, len(out_jobs) * SEC_PER_JOB // 60)} min on one L40S), {n_names} frames get the result')
    print(f'folder: {out}\ncommands: {os.path.join(out, "README.txt")}')


if __name__ == '__main__':
    main()
