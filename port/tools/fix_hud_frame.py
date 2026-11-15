"""Before/after shots of the fixes of 13.11 (caption rows, window frames, pictures short of a piece) with one build:
XENO_WITHOUT_T8=1 draws as before them. Each case is shot in Russian and English, the pack on and off; each pair gives a
1:1 crop of the place of the defect, before on the left, after on the right, and the count of pixels that differ.

Usage: python tools/fix_hud_frame.py <out folder> [case ...]     (cases: see CASES; default all)
"""
import os
import subprocess
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
SCRATCH_STATE = os.environ.get('XENO_USER_STATE', '')

# name: (game args, crop box in the 1280 x 720 shot)
CASES = {
    # The first battle of test.state (walk right), Cross every other frame: Fei's attack lands, "total damage" shows.
    'caption': ('state=out/states/test.state script=20:none,40:right,' + ','.join(['1:cross,1:none'] * 170), (560, 110, 740, 220)),
    # Fei's room: the window with his portrait ("Whew!").
    'window': ('map=4 ff=6134 script=640:none', (180, 380, 1100, 700)),
    # A world map battle from the user's own state (a copy): the green long-legged enemy.
    'monster': ('state=' + SCRATCH_STATE + ' script=333:none,320:up', (380, 300, 600, 580)),
    # The battle's name window over the world map's first encounter (usa.srm slot 1).
    'namewindow': ('card=out/saves/usa.srm slot=1 script=150:none,60:up,60:right,60:down,60:left,150:none', (120, 100, 560, 220)),
    # The field menu (test.state, Square): its windows' frames.
    'menu': ('state=out/states/test.state script=40:none,2:square,100:none', (0, 0, 1280, 720)),
}


def shoot(args, path, without):
    env = dict(os.environ)
    if without:
        env['XENO_WITHOUT_T8'] = '1'
    else:
        env.pop('XENO_WITHOUT_T8', None)
    run = subprocess.run([GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + [f'shot={path}'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=900, cwd=ROOT, env=env)
    return [line for line in (run.stdout + run.stderr).splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    names = sys.argv[2:] or list(CASES)
    for name in names:
        args, box = CASES[name]
        for lang in ('ru', 'en'):
            for hd in ('1', '0'):
                tag = f'{name}_{lang}_hd{hd}'
                full = f'{args} lang={lang} hd={hd}'
                before, after = os.path.join(out, tag + '_before.png'), os.path.join(out, tag + '_after.png')
                bad = shoot(full, before, True) + shoot(full, after, False)
                a, b = Image.open(before).convert('RGB'), Image.open(after).convert('RGB')
                diff = ImageChops.difference(a, b)
                data = diff.get_flattened_data() if hasattr(diff, 'get_flattened_data') else diff.getdata()
                changed = sum(1 for p in data if p != (0, 0, 0))
                ca, cb = a.crop(box), b.crop(box)
                sheet = Image.new('RGB', (ca.width * 2 + 8, ca.height), (255, 0, 255))
                sheet.paste(ca, (0, 0))
                sheet.paste(cb, (ca.width + 8, 0))
                sheet.save(os.path.join(out, tag + '_crop.png'))
                print(f'{tag}: {changed} pixels differ{"; ERRORS " + str(bad) if bad else ""}', flush=True)


if __name__ == '__main__':
    main()
