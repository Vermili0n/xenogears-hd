"""Before/after shots of the rule of 13.11 afternoon (a pack picture's rim over a transparent texel takes the kind of the
drawn texel nearest to it) with one build: XENO_WITHOUT_T9=1 draws as before it (the rim plain). Each case is shot in
Russian and English, the pack on and off; each pair gives a 1:1 crop of the place (before on the left, after on the
right) and the count of pixels that differ. For the battle's HUD also the count of trace pixels: dark in the shot (every
channel under 32) where the shot without the pack, same case and language, is not (some channel over 64), that is where
the PS1's own texels leave the background, inside the boxes of the command ring and its buttons, and of the gauge.

Usage: python tools/fix_hud_trace.py <out folder> [case ...]     (cases: see CASES; default all)
The world map battle comes from a copy of the user's state (XENO_USER_STATE=<path>), as tools/fix_hud_frame.py's.
"""
import os
import subprocess
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
SCRATCH_STATE = os.environ.get('XENO_USER_STATE', '')
# 1280 x 720: the 320 x 224 screen at 720 / 224 from x 125.7.
SCALE, LEFT = 720 / 224, (1280 - 320 * 720 / 224) / 2


def box(x0, y0, x1, y1):
    """A box of the game's screen (320 x 224 pixels) in the 1280 x 720 shot."""
    return (int(LEFT + x0 * SCALE), int(y0 * SCALE), int(LEFT + x1 * SCALE + 0.999), int(y1 * SCALE + 0.999))


# The battle's HUD: the command ring and the four buttons (0..176 x 38..100 without the gauge's top), the gauge at the
# left (6..26 x 88..212).
RING = [box(0, 38, 176, 86), box(28, 86, 176, 100)]
GAUGE = [box(6, 88, 26, 212)]
HUD = box(0, 30, 220, 212)


def battle(frames):
    """The world map battle of the user's state, Cross every 10 frames from frame 653 on, shot after that many frames."""
    steps = ['333:none', '320:up']
    left = frames - 653
    while left > 0:
        steps.append('1:cross')
        left -= 1
        if left > 0:
            steps.append(f'{min(9, left)}:none')
            left -= min(9, left)
    return 'state=' + SCRATCH_STATE + ' script=' + ','.join(steps)


# name: (game args, crop box in the 1280 x 720 shot, whether to count the HUD's traces). The battle's frames as
# session_smoke counts them: the ring shows from 1167, the HUD fades over 1176..1183 and stays at colour 0 till 1315.
CASES = {
    'ring_shown': (battle(1170), HUD, True),
    'ring_fading': (battle(1178), HUD, True),
    'ring_faded': (battle(1250), HUD, True),
    'ring_gone': (battle(1320), HUD, True),
    # Fei's room: the window with his portrait ("Whew!"), the frame of 15b99a7.
    'window': ('map=4 ff=6134 script=640:none', (180, 380, 1100, 700), False),
    # The field menu (test.state, Square): its windows and the cursor.
    'menu': ('state=out/states/test.state script=40:none,2:square,100:none', (0, 0, 1280, 720), False),
    # The battle's name window over the world map's first encounter (usa.srm slot 1).
    'namewindow': ('card=out/saves/usa.srm slot=1 script=150:none,60:up,60:right,60:down,60:left,150:none', (120, 100, 560, 220), False),
    # The world map at the save: the minimap.
    'minimap': ('card=out/saves/usa.srm slot=1 script=150:none,62:down,12:none', (880, 420, 1280, 720), False),
}


def shoot(args, path, without):
    env = dict(os.environ)
    if without:
        env['XENO_WITHOUT_T9'] = '1'
    else:
        env.pop('XENO_WITHOUT_T9', None)
    run = subprocess.run([GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + [f'shot={path}'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=1800, cwd=ROOT, env=env)
    return [line for line in (run.stdout + run.stderr).splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]


def pixels(image):
    return list(image.get_flattened_data()) if hasattr(image, 'get_flattened_data') else list(image.getdata())


def traces(shot, reference, areas):
    """Pixels dark in shot (all channels < 32) where reference is not (some channel > 64), inside the areas."""
    count = 0
    for area in areas:
        a = pixels(shot.crop(area))
        b = pixels(reference.crop(area))
        count += sum(1 for p, q in zip(a, b) if max(p) < 32 and max(q) > 64)
    return count


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    names = sys.argv[2:] or list(CASES)
    for name in names:
        args, crop, hud = CASES[name]
        for lang in ('ru', 'en'):
            shots = {}
            for hd in ('0', '1'):
                tag = f'{name}_{lang}_hd{hd}'
                full = f'{args} lang={lang} hd={hd}'
                before, after = os.path.join(out, tag + '_before.png'), os.path.join(out, tag + '_after.png')
                bad = shoot(full, before, True) + shoot(full, after, False)
                a, b = Image.open(before).convert('RGB'), Image.open(after).convert('RGB')
                shots[hd] = (a, b)
                changed = sum(1 for p in pixels(ImageChops.difference(a, b)) if p != (0, 0, 0))
                ca, cb = a.crop(crop), b.crop(crop)
                sheet = Image.new('RGB', (ca.width * 2 + 8, ca.height), (255, 0, 255))
                sheet.paste(ca, (0, 0))
                sheet.paste(cb, (ca.width + 8, 0))
                sheet.save(os.path.join(out, tag + '_crop.png'))
                line = f'{tag}: {changed} pixels differ'
                if hud and hd == '1':
                    reference = shots['0'][1]
                    line += (f'; trace pixels (dark where hd=0 is not) ring+buttons {traces(a, reference, RING)} -> {traces(b, reference, RING)}, '
                             f'gauge {traces(a, reference, GAUGE)} -> {traces(b, reference, GAUGE)}')
                print(line + (f'; ERRORS {bad}' if bad else ''), flush=True)


if __name__ == '__main__':
    main()
