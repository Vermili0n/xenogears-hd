"""The coverage of the party's field sprite sets by the pack, from bridge\\build\\Release\\sprite_coverage.exe's output:
totals per character and palette (frames wholly HD / partly / not, per animation), contact sheets (each frame as the
bridge draws it, pieces not from the pack tinted red) and the names the pack lacks.

  python tools/sprite_coverage.py [out\\sweep_sprites] [--chars 0-10] [--k 3] [--no-sheets]

Writes into the folder: totals.txt; sheet_<c>_<palette>.png; missing_names_<c>.txt (grouped by palette, animation and
frame, in the pack's naming "<upload>-<palette>"; for each name the user's extracted part of the same size and palette
closest to it, when one with a picture in the pack differs in at most 5 % of texels with no opaque colour changed - the
rule of xeno_sprites\\tools\\alias_dump_parts.py, which put such pictures in the pack under the names the game uploads).
The extracted parts are read from ..\\xeno_sprites\\extracted\\disc1_full (read only).
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game_model import read_bc7  # noqa: E402

PACK = os.environ.get('XENO_PACK', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pack'))  # the HD pack folder
# The sprite pipeline's extracted parts (sprites/, not published: game data): XENO_EXTRACTED=<extracted>\disc1_full.
EXTRACTED = os.environ.get('XENO_EXTRACTED', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'xeno_sprites', 'extracted', 'disc1_full'))
HERO_FOLDERS = {0: 'fei', 1: 'elly', 2: 'citan', 3: 'bart', 4: 'billy', 5: 'rico', 6: 'emeralda', 7: 'chuchu', 8: 'maria', 9: 'citan', 10: 'emeralda'}
HERO_NAMES = {0: 'Fei', 1: 'Elly', 2: 'Citan', 3: 'Bart', 4: 'Billy', 5: 'Rico', 6: 'Emeralda', 7: 'Chu-Chu', 8: 'Maria', 9: 'Citan (sword)', 10: 'Emeralda (adult)'}
VERDICT_COLOURS = {'hd': (60, 170, 80), 'partly': (230, 180, 40), 'not': (210, 60, 60)}
_pictures = {}


def picture(path):
    if path not in _pictures:
        if path.endswith('.bc7'):
            _pictures[path] = Image.fromarray(read_bc7(path))
        else:
            _pictures[path] = Image.open(path).convert('RGBA')
    return _pictures[path]


def draw_frame(record, k, tint=True):
    """The frame as the bridge draws it: each piece's stretches from its picture or its VRAM texels (tinted), last piece first."""
    pieces = record['pieces']
    if not pieces:
        return Image.new('RGBA', (k, k), (0, 0, 0, 0))
    xs = [v for p in pieces for v in (p['x0'], p['x1'])]
    ys = [v for p in pieces for v in (p['y0'], p['y1'])]
    left, top = min(xs), min(ys)
    out = Image.new('RGBA', (int(round((max(xs) - left) * k)), int(round((max(ys) - top) * k))), (0, 0, 0, 0))
    for p in reversed(pieces):  # the PS1 draws a sprite's first pieces over its later ones
        texels = np.frombuffer(bytes.fromhex(p['texels']), np.uint8).reshape(p['h'], p['w'], 4)
        for d in p['draws']:
            s0, t0, s1, t1 = d['cell']
            x0 = p['x0'] + s0 * (p['x1'] - p['x0'])
            x1 = p['x0'] + s1 * (p['x1'] - p['x0'])
            y0 = p['y0'] + t0 * (p['y1'] - p['y0'])
            y1 = p['y0'] + t1 * (p['y1'] - p['y0'])
            dx0, dx1 = sorted((x0, x1))
            dy0, dy1 = sorted((y0, y1))
            w = max(1, int(round((dx1 - dx0) * k)))
            h = max(1, int(round((dy1 - dy0) * k)))
            u0, v0, u1, v1 = d['src']
            if d['t']:
                im = picture(d['t'])
                W, H = im.size
                box = (min(u0, u1) * W, min(v0, v1) * H, max(u0, u1) * W, max(v0, v1) * H)
                crop = im.crop(tuple(int(round(b)) for b in box)) if box[2] - box[0] >= 1 and box[3] - box[1] >= 1 else im.crop((0, 0, 1, 1))
                part = crop.resize((w, h), Image.LANCZOS)
                alpha = np.array(crop.split()[3].resize((w, h), Image.NEAREST))
                part.putalpha(Image.fromarray(alpha))
            else:
                a, b = sorted((u0 - p['u'], u1 - p['u']))
                c, e = sorted((v0 - p['v'], v1 - p['v']))
                a, c = int(a), int(c)
                b, e = max(a + 1, int(round(b))), max(c + 1, int(round(e)))
                crop = texels[c:e, a:b].copy()
                tinted = crop.astype(np.int32)
                if tint:
                    tinted[..., 0] = np.minimum(255, tinted[..., 0] // 2 + 128)
                    tinted[..., 1] //= 2
                    tinted[..., 2] //= 2
                part = Image.fromarray(np.where(crop[..., 3:] > 0, tinted, 0).astype(np.uint8)).resize((w, h), Image.NEAREST)
            if (x1 < x0) != (u1 < u0):
                part = part.transpose(Image.FLIP_LEFT_RIGHT)
            if (y1 < y0) != (v1 < v0):
                part = part.transpose(Image.FLIP_TOP_BOTTOM)
            out.alpha_composite(part, (int(round((dx0 - left) * k)), int(round((dy0 - top) * k))))
    return out


def sheet(records, verdicts, k, title, path, columns=16):
    cell_w = max(max(1, int((max(v for p in r['pieces'] for v in (p['x0'], p['x1'])) - min(v for p in r['pieces'] for v in (p['x0'], p['x1']))) * k))
                 for r in records if r['pieces'])
    cell_h = max(max(1, int((max(v for p in r['pieces'] for v in (p['y0'], p['y1'])) - min(v for p in r['pieces'] for v in (p['y0'], p['y1']))) * k))
                 for r in records if r['pieces'])
    cell_w += 8
    cell_h += 22
    rows = (len(records) + columns - 1) // columns
    out = Image.new('RGBA', (columns * cell_w, rows * cell_h + 24), (34, 34, 38, 255))
    pen = ImageDraw.Draw(out)
    pen.text((6, 6), title, fill=(230, 230, 230, 255))
    for i, r in enumerate(records):
        x, y = (i % columns) * cell_w, 24 + (i // columns) * cell_h
        verdict = verdicts[r['frame']]
        pen.rectangle((x + 1, y + 1, x + cell_w - 2, y + cell_h - 2), outline=VERDICT_COLOURS[verdict] + (255,), width=2)
        im = draw_frame(r, k)
        out.alpha_composite(im, (x + (cell_w - im.width) // 2, y + 4 + (cell_h - 22 - im.height)))
        pen.text((x + 5, y + cell_h - 17), f"f{r['frame']} a{r['animations'].replace(' ', ',')}"[:22], fill=(220, 220, 220, 255))
    out.save(path)


def extracted_parts(character):
    """The user's extracted parts of the hero's set: name -> (w, h, RGBA), with whether the pack has its picture."""
    folder = os.path.join(EXTRACTED, HERO_FOLDERS[character])
    parts = {}
    with open(os.path.join(folder, 'index.csv')) as f:
        for row in csv.DictReader(f):
            if row['file'] != str(427 + character):
                continue
            parts[row['name']] = (int(row['w']), int(row['h']))
    return folder, parts


def closest_part(texels, palette, folder, parts, pack_names):
    """The extracted part of the same size and palette whose picture the pack has, with the fewest differing texels."""
    h, w = texels.shape[:2]
    best = None
    for name, (pw, ph) in parts.items():
        if (pw, ph) != (w, h) or not name.endswith('-' + palette) or name not in pack_names:
            continue
        other = np.array(Image.open(os.path.join(folder, 'parts', name + '.png')).convert('RGBA'))
        both = (texels[..., 3] > 0) & (other[..., 3] > 0)
        if (texels[both, :3] != other[both, :3]).any():
            continue  # an opaque colour changed: another picture
        differ = int(((texels[..., 3] > 0) != (other[..., 3] > 0)).sum())
        if best is None or differ < best[1]:
            best = (name, differ)
    if best is not None and best[1] > 0.05 * w * h:
        best = None
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', nargs='?', default=os.path.join('out', 'sweep_sprites'))
    ap.add_argument('--chars', default='0-10')
    ap.add_argument('--k', type=int, default=3)
    ap.add_argument('--no-sheets', action='store_true')
    a = ap.parse_args()
    first, last = (int(v) for v in a.chars.split('-')) if '-' in a.chars else (int(a.chars), int(a.chars))
    pack_names = {n.rsplit('.', 1)[0] for n in os.listdir(PACK)}
    totals = []
    grand = defaultdict(Counter)
    for c in range(first, last + 1):
        frames = list(csv.DictReader(open(os.path.join(a.folder, f'frames_{c}.csv'))))
        pieces = list(csv.DictReader(open(os.path.join(a.folder, f'pieces_{c}.csv'))))
        animations = {int(r['animation']): [int(v) for v in r['frames'].split()] for r in csv.DictReader(open(os.path.join(a.folder, f'animations_{c}.csv')))
                      if r['frames'] != '-'}
        variants = sorted({r['palette_variant'] for r in frames}, key=lambda v: (v != 'own', v))
        totals.append(f"== {c} {HERO_NAMES[c]} (set {427 + c}_0): {len({r['frame'] for r in frames})} frames, {len(animations)} animations")
        for variant in variants:
            rows = {int(r['frame']): r for r in frames if r['palette_variant'] == variant}
            verdicts = {f: r['verdict'] for f, r in rows.items()}
            count = Counter(verdicts.values())
            grand[variant if variant == 'own' else 'other'].update(count)
            palettes = sorted({p for r in rows.values() for p in r['palettes'].split()})
            totals.append(f"  palette {variant} ({' '.join(palettes)}): wholly HD {count['hd']}, partly {count['partly']}, not {count['not']}; "
                          f"texels from VRAM {sum(float(r['texels_vram']) for r in rows.values()):.0f} of {sum(int(r['texels']) for r in rows.values())}")
            for animation, shown in sorted(animations.items()):
                n = Counter(verdicts[f] for f in shown if f in verdicts)
                if n['partly'] or n['not']:
                    bad = [f for f in shown if verdicts.get(f) != 'hd']
                    totals.append(f"    animation {animation}: {len(shown)} frames, HD {n['hd']}, partly {n['partly']}, not {n['not']} (frames {' '.join(map(str, bad))})")
            unreached = [f for f, r in rows.items() if r['animations'] == '-']
            if unreached:
                n = Counter(verdicts[f] for f in unreached)
                totals.append(f"    frames no animation reached: {len(unreached)}, HD {n['hd']}, partly {n['partly']}, not {n['not']}")
            if not a.no_sheets:
                records = [json.loads(line) for line in open(os.path.join(a.folder, f'draws_{c}.jsonl'))]
                records = [r for r in records if r['variant'] == variant]
                sheet(records, verdicts, a.k, f"{c} {HERO_NAMES[c]} set {427 + c}_0, palette {variant}: green HD, yellow partly, red not; red-tinted = VRAM",
                      os.path.join(a.folder, f'sheet_{c}_{variant}.png'))
        # The names the pack lacks, by palette, animation and frame.
        folder, parts = extracted_parts(c)
        records = {(json.loads(line)['variant'], json.loads(line)['frame']): json.loads(line) for line in open(os.path.join(a.folder, f'draws_{c}.jsonl'))}
        lines = [f"# {HERO_NAMES[c]} (set {427 + c}_0): pack names (<upload>-<palette>) the bridge looked up for sprite pieces not wholly from the pack.",
                 "# Each: palette variant, frame, the animations showing it, piece, class (a: no picture of the upload under any palette; b: only under",
                 "# other palettes; c: every upload has its picture; d: no upload), texels; then 'alias <- <name> (n texels differ)' when an extracted",
                 "# part of the same size and palette with a picture in the pack differs from the upload only in a few transparent texels."]
        names = Counter()
        for r in pieces:
            if r['kind'] == '0':
                continue
            record = records[(r['palette_variant'], int(r['frame']))]
            piece = record['pieces'][int(r['piece'])]
            texels = np.frombuffer(bytes.fromhex(piece['texels']), np.uint8).reshape(piece['h'], piece['w'], 4)
            for name in r['names'].split() or ['-']:
                names[name] += 1
                alias = ''
                if name != '-' and name not in pack_names:
                    best = closest_part(texels, name.split('-')[1], folder, parts, pack_names)
                    alias = f"  alias <- {best[0]} ({best[1]} texels differ)" if best else '  no close extracted part'
                lines.append(f"{r['palette_variant']}\tframe {r['frame']}\tanimations {r['animations']}\tpiece {r['piece']}\tclass {r['miss']}\t{name}\t{r['w']}x{r['h']}{alias}")
        lines.insert(4, f"# {len(names)} names, {sum(names.values())} piece-frames")
        with open(os.path.join(a.folder, f'missing_names_{c}.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        totals.append(f"  missing names: {len(names)} ({os.path.join(a.folder, f'missing_names_{c}.txt')})")
    totals.append('== all: ' + '; '.join(f"palette {v}: HD {n['hd']}, partly {n['partly']}, not {n['not']}" for v, n in grand.items()))
    text = '\n'.join(totals) + '\n'
    print(text)
    with open(os.path.join(a.folder, 'totals.txt'), 'w') as f:
        f.write(text)


if __name__ == '__main__':
    main()
