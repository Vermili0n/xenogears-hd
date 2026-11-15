r"""Pod jobs for the hero frames the production render lost (14.11.2026): frames whose layout names block '0'.

  python ai\redraw\zero_block\make_job.py
A frame of a set may name a block the set does not hold (layout.json: "block": "0", an empty piece: the game draws
nothing there, or a head it takes from another set). ai_redraw.Hero raises on it (no parts/0-<pal>.png), render_prod.py
takes that for an empty frame and skips it, and the parts only such frames bring were never drawn: Citan runs in
original pixels on three frames of his run (F6 report 14.11, xeno_port/out/frame_reports/2026-11-14T23-26-47-638).
Here the same controls as render_prod.build_group makes, with block '0' left out, for the frames that still need a
render (FRAMES); what needs none is in README.txt. Writes jobs.json, control/, boards/, meta.json, run.sh, README.txt
beside this file. Nothing in ai/prod or in the pack is touched.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v3 import CAP_HEAD, head_window  # noqa: E402
from render_build import CAP_REF  # noqa: E402
from render_set import head_control  # noqa: E402

NAME = os.path.basename(HERE)
SEEDS = [7, 11, 23]
EYEPATCH = ', he wears a black eyepatch over one eye exactly where the sprite shows the dark patch'
# (group, hero folder, board, set, frame, hint, head close-up, the pack names this render is for)
FRAMES = [
    # Citan's run towards the camera, third step. The field set's frame 429_0:99 has no head of its own (block '0');
    # the world map set's 3924_0:39 is the same figure texel for texel with its head: that one is rendered.
    ('h_citan', 'citan', 'citan', '3924_0', 39, '', True, ['69375a47-9694422f', 'f5c68a74-9694422f']),
    # Citan in battle, one frame: crouched under a cloud of dust (an effect on top, so no head close-up; the model may
    # draw the cloud as something else: judge by eye).
    ('h_citan', 'citan', 'citan', '2991_0', 116, '', False,
     ['52d944e6-177a4dc6', '98658317-177a4dc6', '5d4aab65-177a4dc6', 'd8d0f8aa-177a4dc6']),
    # Bart standing, the head turning.
    ('h_bart', 'bart', 'bart', '430_0', 70, EYEPATCH, True, ['c2be06fd-84f5630b', 'ef212788-84f5630b', '9e3e77d0-84f5630b']),
]

README = r"""Frames the production render lost (a layout block '0'): {n_frames} frames + their head close-ups = {n_jobs} jobs,
seeds {seeds} -> {n_pictures} pictures, about {eta} min on one L40S.

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY> or ~/.ssh/<SSH_KEY>).
Run from the xeno_sprites folder in PowerShell.

1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (repeat until SETUP_OK, ~10 min)

2. Upload and render (the seeds one after the other, run.sh):
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r ai\redraw\{name} root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/{name}/run.sh > redraw/{name}/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/{name}/infer.log; ls /workspace/redraw/{name}/res_*/v4 | grep -c png"
   (done: RENDER_DONE and {n_pictures} files, {n_jobs} per seed)

3. Download, then stop the pod in RunPod:
   scp -P PORT -r root@HOST:/workspace/redraw/{name}/res_* ai\redraw\{name}\

4. Tell Claude. Do NOT run fix_apply.py on this folder: these frames are not in ai/prod (jobs_v4.json, meta.json), and
   fix_apply rebuilds the whole h_bart group, which would undo the fixes of 01.11 and 03.11.

What the install has to do (meta.json here has each frame's set, frame, head window and names):
{wanted}
  ai_redraw.Hero must leave block '0' out for these frames (HeroZ in make_job.py), or compose / slice raise.
  Only the names listed are written; every other part of these frames is in the pack already.

Needs no pod: three more names of Citan's run are cut from composites that exist (the field frames are the world map
set's frames without the head, texel for texel; the field set cuts the body into other blocks):
  4c19563e-9694422f (24x13)                      field 429_0:93 = world map 3924_0:33 -> ai/prod_work/h_citan/work/3924_0_033_red.png
  93b3328f-9694422f (20x21), 938162c3-9694422f (16x10)   field 429_0:97 = world map 3924_0:37 -> ai/prod_work/h_citan/work/3924_0_037_red.png
  (429_0:99 also shows 4c19563e, one texel lower than in 429_0:93.)

Not here: Billy's gear on the field (extracted/disc1_full/gear456, frames 21-30, 65 names) has the same cause; gears are
LoRA v2 (tools/gear_redraw.py).
"""


class HeroZ(Hero):
    """Hero with the empty block '0' left out of a frame."""

    def placements(self, setkey, fi):
        s = self.layout[setkey]
        out = []
        for p in s['frames'][fi]:
            if p['block'] == '0':
                continue
            pal = s['palettes'][min(p['clut'], len(s['palettes']) - 1)]
            img = self.part(p['block'], pal)
            out.append({**p, 'pal': pal, 'w': img.width, 'h': img.height, 'x': p['dx'] + p['mx'], 'y': p['dy'] + p['my']})
        return out


def main():
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    jobs, meta, wanted = [], {}, []
    for group, hero, board, sk, fi, hint, head, names in FRAMES:
        hd = os.path.join(ROOT, 'extracted', 'disc1_full', hero)
        h = HeroZ(hd)
        name = f'{group}__{sk}_{fi:03d}'
        o8 = frame_rgba(h, sk, fi)
        x0, y0 = head_window(h, sk, fi)
        meta[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': sk, 'frame': fi, 'head': [x0, y0],
                      'dups': [], 'group': group, 'kind': 'hero', 'names': names}
        place(o8, 512, 500).save(os.path.join(HERE, 'control', name + '.png'))
        ref = f'boards/{board}.png'
        if not os.path.exists(os.path.join(HERE, ref)):
            shutil.copyfile(os.path.join(ROOT, 'ai', 'prod', ref), os.path.join(HERE, ref))
        jobs.append({'name': name, 'control': f'control/{name}.png', 'ref': ref, 'prompt': CAP_REF + hint})
        wanted.append(f'  {name}: ' + ', '.join(names))
        hc, cov = head_control(o8, x0, y0)
        if not head or cov < 0.15:
            continue
        meta[name]['head_job'] = name + '__head'
        hc.save(os.path.join(HERE, 'control', name + '__head.png'))
        jobs.append({'name': name + '__head', 'control': f'control/{name}__head.png', 'ref': ref, 'prompt': CAP_HEAD + hint})
    json.dump(jobs, open(os.path.join(HERE, 'jobs.json'), 'w'), indent=1)
    json.dump(meta, open(os.path.join(HERE, 'meta.json'), 'w'), indent=1)
    run = ['#!/usr/bin/env bash', '# The seeds one after the other. Resumable: finished files are skipped.', 'cd /workspace',
           'for s in ' + ' '.join(str(s) for s in SEEDS) + '; do',
           f'  HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{NAME}/jobs.json --out redraw/{NAME}/res_$s --crop --cfg 4'
           ' --seed $s --lora lora/xeno_klein_v4.safetensors',
           'done', 'echo RENDER_DONE', '']
    open(os.path.join(HERE, 'run.sh'), 'w', encoding='utf-8', newline='\n').write('\n'.join(run))
    n_pictures = len(jobs) * len(SEEDS)
    text = README.format(name=NAME, n_frames=len(FRAMES), n_jobs=len(jobs), seeds=', '.join(str(s) for s in SEEDS),
                         n_pictures=n_pictures, eta=max(1, n_pictures * 15 // 60), wanted='\n'.join(wanted))
    open(os.path.join(HERE, 'README.txt'), 'w', encoding='utf-8').write(text)
    print(f'{len(FRAMES)} frames, {len(jobs)} jobs x {len(SEEDS)} seeds = {n_pictures} pictures; commands: {os.path.join(HERE, "README.txt")}')


if __name__ == '__main__':
    main()
