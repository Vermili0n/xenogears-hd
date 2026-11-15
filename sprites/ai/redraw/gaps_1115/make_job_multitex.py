r"""Pod jobs for the map NPC sets that were cut from the wrong texture (15.11.2026; class of Khan's flashback set).

  python ai\redraw\gaps_1115\make_job_multitex.py      -> pod_multitex\ (jobs.json, control\, boards\, meta.json, run.sh, README.txt)
The sets npc_fixed.py re-extracts (pieces on texture 1/2 now cut from their own image, fixed\<set>), rendered whole in
one style as the production did (render_prod: same caption and board per group, seed 42, head close-ups for the story
groups c_* only). Nothing in ai/prod or in the pack is touched; installing the result needs a texture-aware
projection (the second image of an item is its own upload: e.g. Khan's 1ebf4490-56b2aa1b) - see README.
"""
import json
import os
import shutil
import sys

from gcommon import HERE, ROOT
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v3 import CAP_HEAD, head_window  # noqa: E402
from render_set import head_control  # noqa: E402

NAME = 'pod_multitex'
OUT = os.path.join(HERE, NAME)
SEED = 42
# set -> production group (ai/prod/jobs_v4.json gives its board and caption)
SETS = {
    '1ecec3878b': 'm_1ecec3878b',      # Khan (Fei's father), flashback maps 662/664 - F6 reports 15.11
    '2a6c20d32b': 'm_2a6c20d32b',
    '507b56107a': 'm_507b56107a',
    '85dbb0f247': 'c_gaspar_uzuki_85dbb0',
    '9b2c042653': 'm_9b2c042653',
    'a00b6f391b': 'm_a00b6f391b',
    'b1289f4abd': 'm_b1289f4abd',
    'c2df43a7cd': 'c_kelvena_c2df43',
    'c3531d4e57': 'm_c3531d4e57',
}

README = r"""Map NPC sets cut from the wrong texture, rendered again from the fixed cut (npc_fixed.py):
{n_sets} sets, {n_frames} frames + {n_heads} head close-ups = {n_jobs} pictures (seed {seed}), about {eta} min on one RTX PRO 6000 / L40S
(5.7-6.6 s a picture measured 12.11) plus ~10 min pod setup.

Sets: {sets}

Board check BEFORE the pod: the campaign boards of these groups were drawn from the same garbled frames
(boards\npc_1ecec3878b.png: Khan with misplaced pieces). Colours and face are usable; if the user wants a clean board,
one Nano Banana grid of 16 fixed frames per set (Google batch ~$0.06-0.12 each) comes first.

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY>; all transfers through -J <JUMP_HOST>).
Run from the xeno_sprites folder in PowerShell.
1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -J <JUMP_HOST> -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -J <JUMP_HOST> -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -J <JUMP_HOST> -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -J <JUMP_HOST> -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (until SETUP_OK, ~10 min)
2. Upload and render:
   tar the folder ai\redraw\gaps_1115\{name}, copy it to /workspace/redraw/{name} (through <JUMP_HOST>), then
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/{name}/run.sh > redraw/{name}/infer.log 2>&1 &)"
   (done: RENDER_DONE and {n_jobs} files in res_{seed}/v4)
3. Download res_{seed} (tar through <JUMP_HOST>), stop the pod.
4. Install = new work: compose/slice per set from fixed\<set> (Hero folders, parts r<tid>x..), then a projection that
   writes texture k's HD into the upload of image k of the item (npc_maps.cmd_project knows only image 0), BC7, seam fill.
   The c_gaspar / c_kelvena / m_507b56107a / m_81c7c75ab9 groups are already in the pack (drawn from the garbled cut):
   replacing them is an overwrite - only with the user's word.
"""


def main():
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    prod = json.load(open(os.path.join(ROOT, 'ai', 'prod', 'jobs_v4.json')))
    by_group = {}
    for j in prod:
        g = j['name'].split('__')[0]
        kind = 'head' if j['name'].endswith('__head') else 'frame'
        by_group.setdefault(g, {}).setdefault(kind, j)
    jobs, meta, n_frames, n_heads = [], {}, 0, 0
    for nid, group in SETS.items():
        src = by_group[group]['frame']
        ref = src['ref']
        if not os.path.exists(os.path.join(OUT, ref)):
            shutil.copyfile(os.path.join(ROOT, 'ai', 'prod', ref), os.path.join(OUT, ref))
        hd = os.path.join(HERE, 'fixed', nid)
        h = Hero(hd)
        for fi in range(len(h.layout['npc']['frames'])):
            if not h.layout['npc']['frames'][fi]:
                continue
            name = f'{group}__npc_{fi:03d}'
            o8 = frame_rgba(h, 'npc', fi)
            x0, y0 = head_window(h, 'npc', fi)
            meta[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': 'npc', 'frame': fi,
                          'head': [x0, y0], 'group': group, 'kind': 'npc'}
            place(o8, 512, 500).save(os.path.join(OUT, 'control', name + '.png'))
            jobs.append({'name': name, 'control': f'control/{name}.png', 'ref': ref, 'prompt': src['prompt']})
            n_frames += 1
            if 'head' not in by_group[group]:
                continue
            hc, cov = head_control(o8, x0, y0)
            if cov < 0.15:
                continue
            meta[name]['head_job'] = name + '__head'
            hc.save(os.path.join(OUT, 'control', name + '__head.png'))
            jobs.append({'name': name + '__head', 'control': f'control/{name}__head.png', 'ref': ref,
                         'prompt': by_group[group]['head']['prompt']})
            n_heads += 1
        print(nid, group, len(h.layout['npc']['frames']), 'frames', flush=True)
    json.dump(jobs, open(os.path.join(OUT, 'jobs.json'), 'w'), indent=1)
    json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), indent=1)
    run = ['#!/usr/bin/env bash', '# Resumable: finished files are skipped.', 'cd /workspace',
           f'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{NAME}/jobs.json --out redraw/{NAME}/res_{SEED} --crop --cfg 4'
           f' --seed {SEED} --lora lora/xeno_klein_v4.safetensors', 'echo RENDER_DONE', '']
    open(os.path.join(OUT, 'run.sh'), 'w', encoding='utf-8', newline='\n').write('\n'.join(run))
    text = README.format(name=NAME, n_sets=len(SETS), n_frames=n_frames, n_heads=n_heads, n_jobs=len(jobs), seed=SEED,
                         eta=max(1, len(jobs) * 65 // 600), sets=', '.join(f'{k} ({v})' for k, v in SETS.items()))
    open(os.path.join(OUT, 'README.txt'), 'w', encoding='utf-8').write(text)
    print(f'{len(SETS)} sets, {n_frames} frames + {n_heads} heads = {len(jobs)} pictures -> {OUT}')


if __name__ == '__main__':
    main()
