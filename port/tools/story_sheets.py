"""Contact sheets of the story walk's shots: 4 x 4 thumbnails 480 px wide, each with its state's name under it.

Usage: python tools/story_sheets.py [shots folder=out/shots/task7/story] [out prefix=out/shots/task7/story_sheet]
Writes <prefix>_01.png, _02.png ... (16 shots a sheet, in name order = story order).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLUMNS, ROWS, WIDTH, LABEL = 4, 4, 480, 22


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'out', 'shots', 'task7', 'story')
    prefix = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'out', 'shots', 'task7', 'story_sheet')
    names = sorted(n for n in os.listdir(folder) if n.endswith('.png') and not n.startswith('_'))
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    per = COLUMNS * ROWS
    for sheet in range(0, len(names), per):
        chunk = names[sheet:sheet + per]
        first = Image.open(os.path.join(folder, chunk[0]))
        height = round(first.size[1] * WIDTH / first.size[0])
        out = Image.new('RGB', (COLUMNS * WIDTH, ROWS * (height + LABEL)), (24, 24, 24))
        draw = ImageDraw.Draw(out)
        for index, name in enumerate(chunk):
            x, y = (index % COLUMNS) * WIDTH, (index // COLUMNS) * (height + LABEL)
            image = Image.open(os.path.join(folder, name)).convert('RGB').resize((WIDTH, height), Image.LANCZOS)
            out.paste(image, (x, y))
            draw.text((x + 4, y + height + 3), name[:-4], fill=(235, 235, 235), font=font)
        path = f'{prefix}_{sheet // per + 1:02d}.png'
        out.save(path)
        print('sheet', path, len(chunk))


if __name__ == '__main__':
    main()
