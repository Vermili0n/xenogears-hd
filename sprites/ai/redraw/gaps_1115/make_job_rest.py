r"""Pod jobs for the remaining gaps of 15.11 that need new drawings (nothing in the pack or ai/prod is touched).

  python ai\redraw\gaps_1115\make_job_rest.py   -> pod_rest\ (jobs_v4.json, jobs_v2.json, control\, boards\, meta.json, run.sh, README.txt)
LoRA v4 (characters, boards):
  roni46  Roni Fatima, set 44f27d4ef0 frame 46 with its head piece (record 07,5a size 0, drawn by the game 13x13 at uv
          7,90 - F6 2026-11-15T15-11-11-094); frame + head close-up, seeds 7/11/23 (pick by eye, as zero_block).
  f2427   streamed file 2427 (26 frames, palette 9b380d72; frames 0-2 = NPC b1812ab6b8:0-2), board npc_b1812ab6b8, seed 42.
  f3837   streamed file 3837 (9 frames, Tolone's battle palettes; like Id's chi file 3833 but no frame equals her battle
          set's), board tolone (ai/redraw/battle_story/boards), seed 42.
LoRA v2 (gears, mecha caption, no board):
  gear456 Billy's gear on the field, frames 21-30 (layout block '0' left out; plan item 6), seed 42.
  f2410   streamed file 2410 (25 frames, palette 9b2347a5 = gear447 / world map 3943; no frame equal), seed 42.
"""
import json
import os
import shutil

import numpy as np
from PIL import Image

from gcommon import HERE, NPC, ROOT, npc_set
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v3 import CAP_HEAD, head_window  # noqa: E402
from render_build import CAP_REF  # noqa: E402
from render_set import head_control  # noqa: E402
from npc_maps import rgba_from_idx  # noqa: E402

NAME = 'pod_rest'
OUT = os.path.join(HERE, NAME)
CAP_MECHA = 'redraw this pre-rendered mecha sprite as a clean detailed illustration, same pose and silhouette, flat magenta background'


class HeroZ(Hero):
    """Hero with the empty block '0' left out of a frame (zero_block/make_job.py)."""

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


def roni_folder():
    """Roni's set with frame 46's head piece put back: parts of the npc_full set + r0x07y5aw0dh0d (13x13 at 7,90)."""
    nid = '44f27d4ef0'
    src = os.path.join(NPC, nid)
    dst = os.path.join(HERE, 'fixed', 'roni46')
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    lay, u, idx, raw = npc_set(nid)
    block = 'r0x07y5aw0dh0d'
    Image.fromarray(rgba_from_idx(idx[90:103, 7:20], raw[0]), 'RGBA').save(os.path.join(dst, 'parts', f'{block}-{u["palettes"][0]}.png'))
    full = json.load(open(os.path.join(dst, 'layout.json')))
    # the disc's order: the head is the first part listed (drawn last); record dx -8, dy -46
    full['npc']['frames'][46].insert(0, {'block': block, 'dx': -8, 'dy': -46, 'flipx': False, 'flipy': False, 'clut': 0,
                                         'mx': 0, 'my': 0, 'rot': 0})
    json.dump(full, open(os.path.join(dst, 'layout.json'), 'w'))
    return dst


def main():
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, 'ai', 'prod', 'boards', '_blank.png'), os.path.join(OUT, 'boards', '_blank.png'))
    for b, src in (('roni_fatima.png', 'ai/prod/boards'), ('npc_b1812ab6b8.png', 'ai/prod/boards'),
                   ('tolone.png', 'ai/redraw/battle_story/boards')):
        shutil.copyfile(os.path.join(ROOT, src, b), os.path.join(OUT, 'boards', b))
    # (tag, hero folder, Hero class, set key, frames, board, lora, seeds, head close-ups)
    groups = [
        ('roni46', roni_folder(), Hero, 'npc', [46], 'boards/roni_fatima.png', 'v4', [7, 11, 23], True),
        ('f2427', os.path.join(HERE, 'streamed', 'f2427'), Hero, '2427_0', None, 'boards/npc_b1812ab6b8.png', 'v4', [42], False),
        ('f3837', os.path.join(HERE, 'streamed', 'f3837'), Hero, '3837_0', None, 'boards/tolone.png', 'v4', [42], False),
        ('gear456', os.path.join(ROOT, 'extracted', 'disc1_full', 'gear456'), HeroZ, '456_0', list(range(21, 31)),
         'boards/_blank.png', 'v2', [42], False),
        ('f2410', os.path.join(HERE, 'streamed', 'f2410'), Hero, '2410_0', None, 'boards/_blank.png', 'v2', [42], False),
    ]
    jobs = {'v4': [], 'v2': []}
    seeds = {'v4': set(), 'v2': set()}
    meta, counts = {}, []
    for tag, hd, cls, sk, frames, board, lora, sd, heads in groups:
        h = cls(hd)
        if sk not in h.layout:
            sk = next(iter(h.layout))
        frames = frames if frames is not None else [k for k, f in enumerate(h.layout[sk]['frames']) if f]
        n = 0
        for fi in frames:
            try:
                o8 = frame_rgba(h, sk, fi)
            except Exception as ex:  # noqa: BLE001
                print(tag, fi, 'skipped:', ex)
                continue
            name = f'{tag}__{sk}_{fi:03d}'
            place(o8, 512, 500).save(os.path.join(OUT, 'control', name + '.png'))
            prompt = CAP_MECHA if lora == 'v2' else CAP_REF
            for s in sd:
                jobs[lora].append({'name': name if len(sd) == 1 else f'{name}__s{s}', 'control': f'control/{name}.png',
                                   'ref': board, 'prompt': prompt, 'seed': s})
            x0, y0 = head_window(h, sk, fi)
            meta[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': sk, 'frame': fi, 'head': [x0, y0],
                          'group': tag, 'lora': lora}
            n += len(sd)
            if heads:
                hc, cov = head_control(o8, x0, y0)
                if cov >= 0.15:
                    hc.save(os.path.join(OUT, 'control', name + '__head.png'))
                    for s in sd:
                        jobs[lora].append({'name': f'{name}__head' if len(sd) == 1 else f'{name}__head__s{s}',
                                           'control': f'control/{name}__head.png', 'ref': board,
                                           'prompt': CAP_HEAD, 'seed': s})
                    meta[name]['head_job'] = name + '__head'
                    n += len(sd)
            seeds[lora] |= set(sd)
        counts.append(f'{tag}: {n} pictures (LoRA {lora})')
        print(counts[-1], flush=True)
    run = ['#!/usr/bin/env bash', '# Resumable: finished files are skipped. Each job carries its seed (split per seed below).', 'cd /workspace']
    for lora, lst in jobs.items():
        for s in sorted(seeds[lora]):
            part = [j for j in lst if j['seed'] == s]
            if not part:
                continue
            fn = f'jobs_{lora}_s{s}.json'
            json.dump(part, open(os.path.join(OUT, fn), 'w'), indent=1)
            run.append(f'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{NAME}/{fn} --out redraw/{NAME}/res_{lora}_{s} '
                       f'--crop --cfg 4 --seed {s} --lora lora/xeno_klein_{lora}.safetensors')
    run += ['echo RENDER_DONE', '']
    open(os.path.join(OUT, 'run.sh'), 'w', encoding='utf-8', newline='\n').write('\n'.join(run))
    json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), indent=1)
    total = sum(len(v) for v in jobs.values())
    readme = f"""Remaining 15.11 gaps that need drawings: {total} pictures, about {max(1, total * 65 // 600)} min of an RTX PRO 6000 / L40S
(5.7-6.6 s a picture, 12.11) + ~10 min setup; both LoRAs on one pod (v4 = characters, v2 = gears).
{chr(10).join(counts)}

Pod: as ai\\redraw\\gaps_1115\\pod_multitex\\README.txt step 1 (setup_infer.sh, infer_pod.py), plus BOTH LoRAs:
   scp -J <JUMP_HOST> -P PORT lora\\klein_v4\\xeno_klein_v4.safetensors lora\\klein_v2\\xeno_klein_v2.safetensors root@HOST:/workspace/lora/
Upload the folder (tar through <JUMP_HOST>) to /workspace/redraw/{NAME}, then
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/{NAME}/run.sh > redraw/{NAME}/infer.log 2>&1 &)"
Download res_* (tar through <JUMP_HOST>), stop the pod, tell Claude.

Install (separate work, after the user's look at the sheets):
  roni46: pick a seed by eye; slice ONLY the head piece r0x07y5aw0dh0d into the HD sheet 86ef69b7-98d6171a (and the other
    uploads/rects of set 44f27d4ef0 that hold texels 7..19 x 90..102) - an OVERWRITE of existing files: user's word first.
  gear456: like zero_block/install.py (HeroZ, compose + slice, h-1 aliases as gear_redraw install), only the 65 missing names.
  f2410 / f2427 / f3837: compose + slice by their own layouts (streamed\\f*), as id_chi/retarget stage_parts; new names only.
"""
    open(os.path.join(OUT, 'README.txt'), 'w', encoding='utf-8').write(readme)
    print(total, 'pictures ->', OUT)


if __name__ == '__main__':
    main()
