"""Assemble frames at 4x from replacement parts (falls back to nearest-scaled originals), like the game would."""
import argparse
import json
import os

from PIL import Image

S = 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero-dir', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--frames', required=True)
    ap.add_argument('--parts', required=True, help='dir with 4x replacement parts')
    ap.add_argument('--out', required=True)
    ap.add_argument('--bg', default='90,90,90')
    args = ap.parse_args()
    lay = json.load(open(os.path.join(args.hero_dir, 'layout.json')))[args.set]
    frames = []
    for tok in args.frames.split(','):
        a, _, b = tok.partition('-')
        frames += list(range(int(a), int(b or a) + 1))
    cells = []
    for fi in frames:
        pl = []
        for p in lay['frames'][fi]:
            pal = lay['palettes'][min(p['clut'], len(lay['palettes']) - 1)]
            name = f"{p['block']}-{pal}.png"
            rp = os.path.join(args.parts, name)
            orig = Image.open(os.path.join(args.hero_dir, 'parts', name)).convert('RGBA')
            o4 = orig.resize((orig.width * S, orig.height * S), Image.NEAREST)
            r4 = Image.open(rp).convert('RGBA') if os.path.exists(rp) else o4
            a = r4.getchannel('A').point(lambda v: 255 if v else 0)
            r4.putalpha(a)
            pl.append((p, o4, r4))
        x0 = min(p['dx'] + p['mx'] for p, _, _ in pl)
        y0 = min(p['dy'] + p['my'] for p, _, _ in pl)
        x1 = max(p['dx'] + p['mx'] + o.width // S for p, o, _ in pl)
        y1 = max(p['dy'] + p['my'] + o.height // S for p, o, _ in pl)
        pair = []
        for k in (1, 2):
            img = Image.new('RGBA', ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
            for p, o, r in pl:
                im = (o, r)[k - 1]
                if p['flipx']:
                    im = im.transpose(Image.FLIP_LEFT_RIGHT)
                if p['flipy']:
                    im = im.transpose(Image.FLIP_TOP_BOTTOM)
                img.alpha_composite(im, ((p['dx'] + p['mx'] - x0) * S, (p['dy'] + p['my'] - y0) * S))
            pair.append(img)
        cells.append(pair)
    bg = tuple(int(v) for v in args.bg.split(',')) + (255,)
    cw = max(c[0].width for c in cells) + 8
    ch = max(c[0].height for c in cells) + 8
    sheet = Image.new('RGBA', (cw * len(cells), ch * 2), bg)
    for i, (o, r) in enumerate(cells):
        sheet.alpha_composite(o, (i * cw + (cw - o.width) // 2, ch - 4 - o.height))
        sheet.alpha_composite(r, (i * cw + (cw - r.width) // 2, 2 * ch - 4 - r.height))
    sheet.save(args.out)
    print(sheet.size)


if __name__ == '__main__':
    main()
