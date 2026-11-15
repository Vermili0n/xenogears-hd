"""Before/after shots of the same moment with one build: XENO_WITHOUT_T7=1 draws as before task 7's fixes.

Usage: python tools/before_after.py <out folder> <name>="<game args>" ...
Writes <name>_before.png, <name>_after.png, <name>_cmp.png (side by side, 960 px each) and prints how many pixels differ.
"""
import os
import subprocess
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')


def shoot(args, path, without):
    env = dict(os.environ)
    if without:
        env['XENO_WITHOUT_T7'] = '1'
    else:
        env.pop('XENO_WITHOUT_T7', None)
    run = subprocess.run([GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + [f'shot={path}'], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=900, cwd=ROOT, env=env)
    bad = [line for line in (run.stdout + run.stderr).splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]
    return bad


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    for spec in sys.argv[2:]:
        name, args = spec.split('=', 1)
        before, after = os.path.join(out, name + '_before.png'), os.path.join(out, name + '_after.png')
        bad = shoot(args, before, True) + shoot(args, after, False)
        a, b = Image.open(before).convert('RGB'), Image.open(after).convert('RGB')
        diff = ImageChops.difference(a, b)
        changed = sum(1 for p in diff.get_flattened_data() if p != (0, 0, 0)) if hasattr(diff, 'get_flattened_data') else sum(1 for p in diff.getdata() if p != (0, 0, 0))
        w = 960
        h = round(a.size[1] * w / a.size[0])
        sheet = Image.new('RGB', (2 * w, h))
        sheet.paste(a.resize((w, h)), (0, 0))
        sheet.paste(b.resize((w, h)), (w, 0))
        sheet.save(os.path.join(out, name + '_cmp.png'))
        print(f'{name}: {changed} pixels differ{"; ERRORS " + str(bad) if bad else ""}')


if __name__ == '__main__':
    main()
