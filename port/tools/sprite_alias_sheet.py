"""The pictures found by content (FSession::SetAliasIndex) for a person to check by eye, from the bridge's reports
(XENO_ALIAS_REPORT=<csv> on any headless tool: one line per upload or region compared, once).

  python tools/sprite_alias_sheet.py <out folder> <report.csv> [<report.csv> ...]

Writes into the folder:
- substitutions.csv: every accepted pair (what was looked up, the picture used, texels opaque in both with another
  colour, texels opaque in one only, size), and unresolved.csv: every miss with its best candidate of the same size and
  palette, rejected;
- sheet_<palette>.png per palette (a palette is one character's or one set's colours), the riskiest first (most texels
  opaque in one only): per pair the texels as the game holds them, the candidate's original (the index's: the user's
  extracted part or Beetle's dump), where they differ (red: the game draws a texel the original lacks; blue: the other
  way), the HD picture drawn there, and the measures;
- distances.txt: the distribution of the best candidates' measures over every miss.
"""
import csv
import os
import struct
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game_model import read_bc7  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.environ.get('XENO_PACK', os.path.join(ROOT, 'pack'))  # the HD pack folder
INDEX = os.path.join(ROOT, 'out', 'alias', 'sprite_alias_index.bin')
K = 6


def kind(r):
    first = r[0].split()[0]
    return first if first in ('region-rect', 'region-piece', 'port-rect', 'port-piece') else 'upload'


def read_index(names):
    out = {}
    with open(INDEX, 'rb') as f:
        magic, version, count = struct.unpack('<4sII', f.read(12))
        for _ in range(count):
            upload, palette, w, h = struct.unpack('<IIHH', f.read(12))
            data = f.read(w * h * 2)
            name = f'{upload:x}-{palette:x}'
            if name in names:
                out[name] = np.frombuffer(data, '<u2').reshape(h, w)
    return out


def rgba(units):
    u = units.astype(np.uint32)
    out = np.zeros(units.shape + (4,), np.uint8)
    out[..., 0] = (u & 31) * 255 // 31
    out[..., 1] = (u >> 5 & 31) * 255 // 31
    out[..., 2] = (u >> 10 & 31) * 255 // 31
    out[..., 3] = np.where(u != 0, 255, 0)
    return out


def tile(image, w, h):
    back = Image.new('RGBA', (w * K, h * K), (60, 60, 64, 255))
    back.alpha_composite(image.resize((w * K, h * K), Image.NEAREST if image.width == w else Image.LANCZOS))
    return back


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    rows = {}
    for path in sys.argv[2:]:
        for r in csv.reader(open(path)):
            if len(r) >= 9:
                rows[r[0]] = r
    accepted = [r for r in rows.values() if r[6] == '1']
    rejected = [r for r in rows.values() if r[6] != '1']
    with open(os.path.join(out, 'substitutions.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['looked_up', 'picture', 'conflicts', 'edges', 'width', 'height', 'palette'])
        for r in sorted(accepted, key=lambda r: (r[7], -int(r[5]))):
            w.writerow([r[0], r[3], r[4], r[5], r[1], r[2], r[7]])
    with open(os.path.join(out, 'unresolved.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['looked_up', 'best_candidate', 'conflicts', 'edges', 'width', 'height', 'palette'])
        for r in sorted(rejected, key=lambda r: (r[7], r[0])):
            w.writerow([r[0], r[3], r[4], r[5], r[1], r[2], r[7]])
    # The distribution of the best candidates' measures over every miss compared.
    lines = [f'compared {len(rows)}: accepted {len(accepted)}, rejected {len(rejected)}; '
             f'no candidate of the same size and palette {sum(1 for r in rejected if r[3] == "-")}',
             'by kind (accepted / compared): ' + ', '.join(f'{k} {sum(1 for r in accepted if kind(r) == k)}/{sum(1 for r in rows.values() if kind(r) == k)}'
                                                         for k in ('upload', 'region-rect', 'region-piece', 'port-rect', 'port-piece'))]
    cand = [r for r in rows.values() if r[3] != '-']
    lines.append('best candidate, texels opaque in both with another colour: ' + str(sorted(Counter(min(int(r[4]), 21) for r in cand).items())) + ' (21 = 21 or more)')
    zero = [r for r in cand if int(r[4]) == 0]
    share = Counter()
    for r in zero:
        s = int(r[5]) / (int(r[1]) * int(r[2]))
        share['0' if s == 0 else '<=2%' if s <= .02 else '<=5%' if s <= .05 else '<=10%' if s <= .10 else '<=25%' if s <= .25 else '>25%'] += 1
    lines.append('conflicts 0: texels opaque in one only, share of the texels: ' + str(dict(share)))
    lines.append('conflicts 0: texels opaque in one only, count: ' + str(sorted(Counter(min(int(r[5]), 41) for r in zero).items())))
    with open(os.path.join(out, 'distances.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    # Sheets per palette, riskiest first.
    originals = read_index({r[3] for r in accepted})
    by = defaultdict(list)
    for r in accepted:
        by[r[7]].append(r)
    for palette, pairs in by.items():
        pairs.sort(key=lambda r: (-int(r[5]), r[0]))
        cells = []
        for r in pairs:
            w, h = int(r[1]), int(r[2])
            if not r[8] or r[3] not in originals:
                continue
            game = np.frombuffer(bytes.fromhex(r[8]), '>u2').reshape(h, w)
            orig = originals[r[3]]
            diff = np.zeros((h, w, 4), np.uint8)
            diff[(game != 0) & (orig == 0)] = (230, 40, 40, 255)
            diff[(game == 0) & (orig != 0)] = (40, 90, 230, 255)
            path = os.path.join(PACK, r[3] + '.bc7')
            hd = Image.fromarray(read_bc7(path)) if os.path.exists(path) else Image.open(os.path.join(PACK, r[3] + '.png')).convert('RGBA')
            row = [tile(Image.fromarray(rgba(game)), w, h), tile(Image.fromarray(rgba(orig)), w, h), tile(Image.fromarray(diff), w, h), tile(hd, w, h)]
            cells.append((row, f'{r[0]}  <-  {r[3]}   colour {r[4]}, opaque in one only {r[5]} of {w * h}'))
        if not cells:
            continue
        width = sum(c.width for c in cells[0][0]) + 40
        widths = max(sum(c.width for c in row) + 30 for row, _ in cells)
        height = sum(row[0].height + 22 for row, _ in cells) + 24
        sheet = Image.new('RGBA', (max(widths, 600), height), (30, 30, 34, 255))
        pen = ImageDraw.Draw(sheet)
        pen.text((6, 4), f'palette {palette}: the game\'s texels | the original found | differ (red: game only, blue: original only) | HD drawn', fill=(230, 230, 230, 255))
        y = 24
        for row, text in cells:
            pen.text((6, y), text, fill=(230, 230, 120, 255))
            x = 6
            for image in row:
                sheet.alpha_composite(image, (x, y + 14))
                x += image.width + 8
            y += row[0].height + 22
        sheet.save(os.path.join(out, f'sheet_{palette}.png'))
    print(f'{len(accepted)} pairs in {len(by)} sheets: {out}')


if __name__ == '__main__':
    main()
