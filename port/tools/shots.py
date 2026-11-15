"""Takes the same place in several looks with the Godot shell and puts them side by side.

Each look is one run of the game with its own options (a window shows for a few seconds per run).
Usage: python shots.py <name> "<game args shared>" "<label>=<extra args>" ... [--sheet]
  e.g. python shots.py room "map=4 ff=8000 script=10:none,40:down" "orig=hd=0 light=0" "hd=hd=1 light=0" "hd+light=hd=1 light=1"
Writes out/shots/<name>_<label>.png and out/shots/<name>_sheet.png.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
OUT = os.path.join(ROOT, 'out', 'shots')


def shoot(name, shared, label, extra):
    path = os.path.join(OUT, f'{name}_{label.replace("+", "_")}.png')
    args = [GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + shared.split() + extra.split() + [f'shot={path}']
    run = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    shot = [line for line in run.stdout.splitlines() if line.startswith('xeno: shot')]
    print(label, '->', shot[0][:160] if shot else run.stdout[-400:] + run.stderr[-400:])
    return path if os.path.exists(path) else None


def sheet(name, shots):
    """The looks side by side at 1:1 (scaling down would hide the very pixels being compared): the middle of each frame."""
    images = [(label, Image.open(path).convert('RGB')) for label, path in shots if path]
    if not images:
        return
    w, h = images[0][1].size
    cw, ch = min(w, 640), min(h, 480)
    box = ((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    out = Image.new('RGB', (cw * len(images), ch + 30), (20, 20, 20))
    draw = ImageDraw.Draw(out)
    for i, (label, image) in enumerate(images):
        draw.text((i * cw + 8, 5), label, fill=(240, 240, 240), font=font)
        out.paste(image.crop(box), (i * cw, 30))
    path = os.path.join(OUT, f'{name}_sheet.png')
    out.save(path)
    print('sheet', path)


def main():
    name, shared = sys.argv[1], sys.argv[2]
    looks = [a.split('=', 1) for a in sys.argv[3:] if a != '--sheet']
    os.makedirs(OUT, exist_ok=True)
    shots = [(label, shoot(name, shared, label, extra)) for label, extra in looks]
    sheet(name, shots)


if __name__ == '__main__':
    main()
