"""Before/after shots of the sprite fixes of 13.11 (afternoon) with one build, 1:1 crops around what changed:
- 'load_*': the pack's pictures loaded on the frame that first draws them (main.gd hdsync=1) against VRAM's texels until
  a worker has loaded them (hdsync=0); shot_now=1 (the frame as it stands, no waiting for pictures), mid-run;
- 'edge_*': a piece reaching past its picture drawn from the picture with its edge texels replicated, as the user's core
  does, against those texels from VRAM (XENO_BEYOND_VRAM=1, 15b99a7's rule).

Usage: python tools/fix_run_sprite.py <out folder> [case ...]
Writes <case>_before.png, <case>_after.png, <case>_crop.png (before left, after right, 1:1, around the pixels that
differ, at least 240 x 240) and prints how many pixels differ.
"""
import os
import subprocess
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
USER_STATE = os.environ.get('XENO_USER_STATE', '')
NIGHT = 'state=out/sweep_sprites/hd/s108.state'
LAHAN = 'state=out/sweep_sprites/hd/s010.state'

# name: (game args, before's extra args, after's extra args, before's environment)
CASES = {
    # The night (story 16, map 15): Fei runs up, Citan follows; the 10th and 22nd frames of the run.
    'load_night_a': (NIGHT + ' script=20:none,10:up+circle shot_now=1', 'hdsync=0', 'hdsync=1', {}),
    'load_night_b': (NIGHT + ' script=20:none,22:up+circle shot_now=1', 'hdsync=0', 'hdsync=1', {}),
    # Lahan by day (story 7, map 1): Fei runs left among the villagers.
    'load_lahan': (LAHAN + ' script=20:none,3:left+circle shot_now=1', 'hdsync=0', 'hdsync=1', {}),
    # The bar (map 9): the boy at the counter, the barman (pictures of a drawn rectangle a column short of the piece).
    'edge_bar': ('map=9 script=90:none', '', '', {'XENO_BEYOND_VRAM': '1'}),
    # Lahan (map 1, a new game): its villagers.
    'edge_lahan': ('map=1 script=120:none', '', '', {'XENO_BEYOND_VRAM': '1'}),
    # A world map battle from the user's own state (a copy, XENO_USER_STATE): the green long-legged enemy.
    'edge_monster': ('state=' + USER_STATE + ' script=333:none,320:up', '', '', {'XENO_BEYOND_VRAM': '1'}),
}


def shoot(args, path, env_extra):
    env = dict(os.environ)
    env.pop('XENO_BEYOND_VRAM', None)
    env.update(env_extra)
    run = subprocess.run([GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + [f'shot={path}'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=900, cwd=ROOT, env=env)
    return [line for line in (run.stdout + run.stderr).splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    for name in sys.argv[2:] or list(CASES):
        args, before_args, after_args, before_env = CASES[name]
        if 'monster' in name and not USER_STATE:
            print(f'{name}: skipped (XENO_USER_STATE not given)')
            continue
        before, after = os.path.join(out, name + '_before.png'), os.path.join(out, name + '_after.png')
        bad = shoot(f'{args} {before_args}', before, before_env) + shoot(f'{args} {after_args}', after, {})
        a, b = Image.open(before).convert('RGB'), Image.open(after).convert('RGB')
        diff = ImageChops.difference(a, b)
        box = diff.getbbox()
        data = diff.get_flattened_data() if hasattr(diff, 'get_flattened_data') else diff.getdata()
        changed = sum(1 for p in data if p != (0, 0, 0))
        if box is None:
            box = (0, 0, a.width, a.height)
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        w, h = max(240, box[2] - box[0] + 40), max(240, box[3] - box[1] + 40)
        crop = (max(0, cx - w // 2), max(0, cy - h // 2), min(a.width, cx + w // 2), min(a.height, cy + h // 2))
        ca, cb = a.crop(crop), b.crop(crop)
        sheet = Image.new('RGB', (ca.width * 2 + 8, ca.height), (255, 0, 255))
        sheet.paste(ca, (0, 0))
        sheet.paste(cb, (ca.width + 8, 0))
        sheet.save(os.path.join(out, name + '_crop.png'))
        print(f'{name}: {changed} pixels differ, box {box}{"; ERRORS " + str(bad) if bad else ""}', flush=True)


if __name__ == '__main__':
    main()
