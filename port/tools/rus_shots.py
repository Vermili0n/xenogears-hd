"""The same dialogue in Russian and in English, shot with the Godot shell, side by side at 1:1, with what the core holds.

python tools/rus_shots.py <name> "<ru args>" "<en args>" [more shared args]
  e.g. python tools/rus_shots.py lahan_m2_52 "map=4 ff=3629 script=120:none" "map=4 ff=3697 script=120:none"
Writes out/shots/task5/<name>_ru.png, _en.png, _sheet.png (the two whole frames side by side, unscaled) and
<name>.txt: each run's open message windows (map, number, codes as the core holds them) and its 2D tallies.
The Russian run's windows are checked against the Russian disc read by tools/rus_text.py (independent of the core).
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

import rus_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
OUT = os.path.join(ROOT, 'out', 'shots', 'task5')
RUSSIAN = os.path.join(ROOT, 'games_ru', 'xenogears_rus_xz.BIN')
USA = os.path.join(ROOT, 'weltall', 'Games', 'Xenogears (USA) (Disc 1).bin')


def shoot(path, args):
    run = subprocess.run([GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + [f'shot={path}'],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
    lines = [line for line in run.stdout.splitlines() if line.startswith('xeno: ') and 'Vulkan' not in line]
    errors = [line for line in (run.stdout + run.stderr).splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]
    return lines, errors


def tallies(line):
    out = {}
    for key in ('map', 'screen_textured', 'screen_hd', 'sprite_pieces', 'sprite_hd', 'leader_position'):
        at = line.find(f'"{key}": ')
        if at >= 0:
            out[key] = line[at + len(key) + 4:].split(', "')[0]
    return out


def main():
    name, ru_args, en_args = sys.argv[1], sys.argv[2], sys.argv[3]
    shared = sys.argv[4] if len(sys.argv) > 4 else ''
    os.makedirs(OUT, exist_ok=True)
    report = []
    images = []
    for lang, args, disc in (('ru', ru_args, RUSSIAN), ('en', en_args, USA)):
        path = os.path.join(OUT, f'{name}_{lang}.png')
        lines, errors = shoot(path, f'lang={lang} {args} {shared}')
        report.append(f'== {lang}: {args} {shared}')
        report += [f'error: {e}' for e in errors]
        img, index = rus_text.open_disc(disc)
        for line in lines:
            if line.startswith('xeno: shot '):
                report.append(f'tallies {tallies(line)}')
            if line.startswith('xeno: message '):
                words = line.split()
                m, i, codes = int(words[3]), int(words[5]), words[7]
                if i >= 0:
                    mine = rus_text.messages(rus_text.message_table(img, index, m))[i]
                    same = 'EQUAL to the disc read independently' if mine.hex() == codes else 'DIFFERENT from the disc'
                else:
                    same = 'not one of the table messages'
                report.append(f'window map {m} #{i}: {same}')
                report.append(f'  codes {codes}')
                report.append('  reading: ' + rus_text.reading(bytes.fromhex(codes), lang == 'ru').replace('\n', ' | '))
        if os.path.exists(path):
            images.append((f'{lang}: {args}', Image.open(path).convert('RGB')))
    if images:
        w = sum(im.size[0] for _, im in images)
        h = max(im.size[1] for _, im in images)
        sheet = Image.new('RGB', (w, h + 30), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
        x = 0
        for label, im in images:
            draw.text((x + 8, 5), label, fill=(240, 240, 240), font=font)
            sheet.paste(im, (x, 30))
            x += im.size[0]
        sheet.save(os.path.join(OUT, f'{name}_sheet.png'))
    text = '\n'.join(report)
    open(os.path.join(OUT, f'{name}.txt'), 'w', encoding='utf-8').write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
