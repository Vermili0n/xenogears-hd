"""Build the model bake-off inputs: 2x2 grids (1024x1024, cells 512) of xBR-smoothed sprite frames at 8x on magenta,
plus the reference images. Writes ai/or_test/in/{grid_*.png, ref_*.png, grids.json} (cell placement for scoring)."""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import xbr4  # noqa: E402

# name: (set, frames[, cols]) - cols x rows of CELLxCELL cells (default 2x2)
GRIDS = {
    'walk_front': ('427_0', [57, 58, 59, 60]),
    'walk_front2': ('427_0', [61, 62, 63, 64]),
    'walk_side': ('427_0', [41, 42, 43, 44]),
    'walk_back': ('427_0', [25, 26, 27, 28]),
    'kick': ('3005_0', [21, 22, 23, 24]),
    'g16_walk': ('427_0', list(range(25, 41)), 4),          # 2K test: walk back + back-3/4
    'g64_walk': ('427_0', list(range(25, 89)), 8),          # 4K test: all walk/run directions
    'g25_walk': ('427_0', list(range(41, 66)), 5),          # 4K test: 5x5, side + front-3/4 + front walk
}
MAG = (255, 0, 255)
CELL, FEET = 512, 500


def main():
    out = os.path.join(ROOT, 'ai', 'or_test', 'in')
    os.makedirs(out, exist_ok=True)
    meta = {}
    for name, spec in GRIDS.items():
        s, ids = spec[0], spec[1]
        cols = spec[2] if len(spec) > 2 else 2
        rows = -(-len(ids) // cols)
        grid = Image.new('RGB', (cols * CELL, rows * CELL), MAG)
        cells = []
        for j, fi in enumerate(ids):
            o = Image.open(os.path.join(ROOT, 'extracted', 'disc1', 'fei', 'frames', f'{s}_{fi:03d}.png')).convert('RGBA')
            c4, m4 = xbr4(o)
            im = Image.fromarray(np.dstack([c4, (m4 * 255).astype(np.uint8)]), 'RGBA')
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
            a = np.asarray(im).copy()
            a[..., 3] = np.where(a[..., 3] > 127, 255, 0)
            im = Image.fromarray(a, 'RGBA')
            cx, cy = (j % cols) * CELL, (j // cols) * CELL
            x = cx + (CELL - im.width) // 2
            y = cy + FEET - im.height
            grid.paste(im, (x, y), im)
            cells.append({'set': s, 'frame': fi, 'x': x, 'y': y, 'w': im.width, 'h': im.height, 'scale': 8,
                          'cx': cx, 'cy': cy, 'cols': cols, 'rows': rows})
        grid.save(os.path.join(out, f'grid_{name}.png'))
        meta[name] = cells
    fc = os.path.join(ROOT, 'for_chatgpt', 'fei')
    Image.open(os.path.join(fc, 'chatgpt_sheet.png')).convert('RGB').save(os.path.join(out, 'ref_sheet.png'))
    Image.open(os.path.join(fc, 'chatgpt_face.png')).convert('RGB').save(os.path.join(out, 'ref_face.png'))
    # style sample: two figures from the approved ChatGPT walk test (frames 57 and 61), sprite proportions
    t = Image.open(os.path.join(fc, 'test.png')).convert('RGB')
    style = Image.new('RGB', (768, 512), MAG)
    style.paste(t.crop((0, 0, 384, 512)), (0, 0))
    style.paste(t.crop((0, 512, 384, 1024)), (384, 0))
    style.save(os.path.join(out, 'ref_style.png'))
    json.dump(meta, open(os.path.join(out, 'grids.json'), 'w'), indent=1)
    print('ok', list(meta))


if __name__ == '__main__':
    main()
