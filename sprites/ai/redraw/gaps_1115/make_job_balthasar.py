r"""Pod jobs for Balthasar's field set (portrait 562, c691ca06-d588213e): set 48c502a64f, group m_48c502a64f (16.11.2026).

  python ai\redraw\gaps_1115\make_job_balthasar.py   -> pod_balthasar\ (jobs.json, control\, boards\, meta.json, run.sh, README.txt)
User 16.11: "on the model a moustache, on the portrait none". The set was drawn as crowd (m_, Nano Banana board made
from its own frames): that board (ai/prod/boards/npc_48c502a64f.png) gives a younger man with stubble/moustache lines,
and the HD copied it. The sprite and the portrait (562: long grey hair, deep wrinkles, no moustache, no beard) agree.
Two new boards, both from the game's own pictures, no paid generation:
  A  boards\balth_a.png: the old board's bodies (outfit and colours as the sprite) + portrait 562's HD face twice
     in the lower row in place of the stubbled heads (back view kept).
  B  boards\balth_b.png: official art (for_chatgpt\isaac_balthasar\1_portrait.png, full body) + portrait 562 HD.
Every frame of the set (76; shared parts: a set is drawn whole, one board) + a head close-up where the face shows
(skin in the head window of the original) - for both boards, seed 42. The user picks a board by the sheets, then the
install is an OVERWRITE of the set's pack files (only with the user's word).
"""
import json
import os

import numpy as np
from PIL import Image

from gcommon import HERE, ROOT, hd, show
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v3 import head_window  # noqa: E402
from render_set import head_control  # noqa: E402

NAME = 'pod_balthasar'
OUT = os.path.join(HERE, NAME)
SET = '48c502a64f'
GROUP = 'm_48c502a64f'
SEED = 42
PROMPT = ('redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the second image, '
          'same pose and silhouette, flat magenta background')
PROMPT_HEAD = 'close-up of the head: ' + PROMPT
MAG = (255, 0, 255)


def portrait():
    """Portrait 562's HD on the board grey (transparent -> grey)."""
    h = hd('c691ca06-d588213e')
    rgb = show(h)
    grey = np.array([206, 206, 206], np.uint8)
    rgb[(rgb == MAG).all(-1)] = grey
    return Image.fromarray(rgb)


def boards():
    old = Image.open(os.path.join(ROOT, 'ai', 'prod', 'boards', f'npc_{SET}.png')).convert('RGB')
    face = portrait()
    a = old.copy()
    # lower row of the old board: front head 0..170, 3/4 head 170..340, back 340..512 (y 340..512)
    a.paste(face.resize((172, 172), Image.LANCZOS), (0, 340))
    a.paste(face.resize((172, 172), Image.LANCZOS), (170, 340))
    a.save(os.path.join(OUT, 'boards', 'balth_a.png'))
    art = Image.open(os.path.join(ROOT, 'for_chatgpt', 'isaac_balthasar', '1_portrait.png')).convert('RGBA')
    bg = Image.new('RGBA', art.size, (206, 206, 206, 255))
    art = Image.alpha_composite(bg, art).convert('RGB')
    b = Image.new('RGB', (512, 512), (206, 206, 206))
    k = min(300 / art.width, 512 / art.height)
    art = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)
    b.paste(art, ((300 - art.width) // 2, (512 - art.height) // 2))
    b.paste(face.resize((208, 208), Image.LANCZOS), (304, 152))
    b.save(os.path.join(OUT, 'boards', 'balth_b.png'))


def face_shows(o8, x0, y0):
    """Skin in the head window of the original frame: a face (front, side) and not the back of the head."""
    o = np.asarray(o8)
    s = 8  # frame_rgba is x8 of the native frame
    win = o[max(0, y0 * s):(y0 + 24) * s, max(0, x0 * s):(x0 + 24) * s]
    r, g, b, al = (win[..., k].astype(int) for k in range(4))
    skin = (al > 128) & (r > 180) & (g > 120) & (b < 170) & (r > g + 20) & (g > b)
    return skin.sum() / max(1, (al > 128).sum()) > 0.04


def main():
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    boards()
    h = Hero(os.path.join(ROOT, 'extracted', 'npc_full', SET))
    jobs, meta, n_heads = [], {}, 0
    for fi in range(len(h.layout['npc']['frames'])):
        if not h.layout['npc']['frames'][fi]:
            continue
        name = f'{GROUP}__npc_{fi:03d}'
        o8 = frame_rgba(h, 'npc', fi)
        x0, y0 = head_window(h, 'npc', fi)
        place(o8, 512, 500).save(os.path.join(OUT, 'control', name + '.png'))
        meta[name] = {'hero_dir': f'extracted/npc_full/{SET}', 'set': 'npc', 'frame': fi, 'head': [x0, y0], 'group': GROUP,
                      'kind': 'npc'}
        heads = False
        hc, cov = head_control(o8, x0, y0)
        if cov >= 0.15 and face_shows(o8, x0, y0):
            hc.save(os.path.join(OUT, 'control', name + '__head.png'))
            meta[name]['head_job'] = name + '__head'
            heads = True
            n_heads += 1
        for tag in ('a', 'b'):
            ref = f'boards/balth_{tag}.png'
            jobs.append({'name': f'{tag}__{name}', 'control': f'control/{name}.png', 'ref': ref, 'prompt': PROMPT})
            if heads:
                jobs.append({'name': f'{tag}__{name}__head', 'control': f'control/{name}__head.png', 'ref': ref,
                             'prompt': PROMPT_HEAD})
    json.dump(jobs, open(os.path.join(OUT, 'jobs.json'), 'w'), indent=1)
    json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), indent=1)
    run = ['#!/usr/bin/env bash', '# Resumable: finished files are skipped.', 'cd /workspace',
           f'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{NAME}/jobs.json --out redraw/{NAME}/res_{SEED} --crop --cfg 4'
           f' --seed {SEED} --lora lora/xeno_klein_v4.safetensors', 'echo RENDER_DONE', '']
    open(os.path.join(OUT, 'run.sh'), 'w', encoding='utf-8', newline='\n').write('\n'.join(run))
    n_frames = len(meta)
    open(os.path.join(OUT, 'README.txt'), 'w', encoding='utf-8').write(
        f"Balthasar (portrait 562) field set {SET} again, without the moustache: {n_frames} frames + {n_heads} heads, "
        f"x2 boards (A: old board + portrait face, B: official art + portrait) = {len(jobs)} pictures, seed {SEED}, LoRA v4.\n"
        f"Pod: as pod_multitex\\README.txt step 1; upload this folder to /workspace/redraw/{NAME}, then\n"
        f"   ssh -J <JUMP_HOST> -p PORT root@HOST \"cd /workspace && (setsid nohup bash redraw/{NAME}/run.sh > redraw/{NAME}/infer.log 2>&1 &)\"\n"
        f"(done: RENDER_DONE and {len(jobs)} files in res_{SEED}/v4). Download res_{SEED}.\n"
        "Install: the user picks board A or B on the sheets; compose (heads 16x) + slice + project like the production\n"
        "(prod_post for this group with the picked results) - an overwrite of the set's files: the user's word first.\n")
    print(f'{n_frames} frames + {n_heads} heads, x2 boards = {len(jobs)} pictures -> {OUT}')


if __name__ == '__main__':
    main()
