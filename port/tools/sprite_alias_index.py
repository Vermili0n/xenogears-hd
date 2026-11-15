"""The original texels behind the pack's pictures, for the bridge to find a picture by content when an upload's own name is
not in the pack (FSession::SetAliasIndex): every pack name whose original drawing is known - the user's extracted parts
(..\\xeno_sprites\\extracted\\*\\*\\parts\\<name>.png, the parts his pack's pictures were drawn over) and Beetle's dumps
(<pack name>.png in the -texture-dump folders: what Beetle saw under that very name). Read only; the index is derived
game data and lives in out\\alias\\ (outside git).

  python tools/sprite_alias_index.py [out\\alias\\sprite_alias_index.bin]

Format (little-endian): 'XALI', u32 version 1, u32 count; per entry u32 upload crc, u32 palette crc, u16 width, u16
height, then width x height u16 texels row by row: 0 transparent, else 0x8000 | r5 | g5 << 5 | b5 << 10 (8-bit >> 3).
"""
import glob
import os
import struct
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The sprite pipeline's extracted parts (game data, not published): XENO_EXTRACTED=<folder>.
SPRITES = os.environ.get('XENO_EXTRACTED', os.path.join(os.path.dirname(ROOT), 'xeno_sprites', 'extracted'))
PACK = os.environ.get('XENO_PACK', os.path.join(ROOT, 'pack'))  # the HD pack folder
# Beetle's texture dump folders (RetroArch's <system>/<game>-texture-dump), separated by ';': XENO_DUMPS=<folder>;<folder>.
DUMPS = [d for d in os.environ.get('XENO_DUMPS', '').split(';') if d]


def texels(path):
    a = np.asarray(Image.open(path).convert('RGBA')).astype(np.uint16)
    value = 0x8000 | (a[..., 0] >> 3) | (a[..., 1] >> 3) << 5 | (a[..., 2] >> 3) << 10
    return np.where(a[..., 3] > 0, value, 0).astype('<u2')


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'out', 'alias', 'sprite_alias_index.bin')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pack = {n.rsplit('.', 1)[0] for n in os.listdir(PACK) if n.endswith(('.bc7', '.png'))}
    sources = {}
    for d in DUMPS:
        if os.path.isdir(d):
            for n in os.listdir(d):
                stem = n[:-4]
                if n.endswith('.png') and stem in pack and '-' in stem:
                    sources[stem] = os.path.join(d, n)
    dumped = len(sources)
    # The extracted parts are the pictures' own originals: they win over a dump of the same name.
    for path in glob.glob(os.path.join(SPRITES, '*', '*', 'parts', '*.png')):
        stem = os.path.basename(path)[:-4]
        if stem in pack:
            sources[stem] = path
    entries = []
    for stem, path in sorted(sources.items()):
        upload, palette = (int(v, 16) for v in stem.split('-'))
        t = texels(path)
        entries.append((t.shape[1], t.shape[0], upload, palette, t))
    entries.sort(key=lambda e: (e[0], e[1], e[2], e[3]))
    with open(out, 'wb') as f:
        f.write(b'XALI' + struct.pack('<II', 1, len(entries)))
        for w, h, upload, palette, t in entries:
            f.write(struct.pack('<IIHH', upload, palette, w, h))
            f.write(t.tobytes())
    print(f'{out}: {len(entries)} pictures with known originals ({dumped} named in the dumps; extracted parts for the rest or in their place), '
          f'{os.path.getsize(out) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
