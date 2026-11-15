r"""Shared helpers of the 15.11 pack-gap work (gaps_1115): pack names, decoding, sheets of extracted sets."""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
from alias_dump_parts import PACK, read_bc7_level0  # noqa: E402
from npc_maps import lut, rgba_from_idx  # noqa: E402

MOD_PACK = os.path.join(os.path.dirname(ROOT), 'xeno_port', 'dist', 'XenogearsHD', 'pack')
NPC = os.path.join(ROOT, 'extracted', 'npc_full')
NAMES = os.path.join(HERE, 'pack_names.txt')
S = 8


RUS_BIN = os.path.join(os.path.dirname(ROOT), 'xeno_port', 'games_ru', 'xenogears_rus_xz.BIN')
RUS_BIN2 = os.path.join(os.path.dirname(ROOT), 'xeno_port', 'games_ru', 'xenogears_rus_xz2.BIN')


class RawUser:
    """The 2048-byte user-data stream of a MODE2/2352 image, sliced like the cooked work/*_user.bin files
    (work/disc1rus_user.bin is not the disc the port runs: its files lie elsewhere). Read only."""

    def __init__(self, path):
        self.f = open(path, 'rb')
        self.size = os.path.getsize(path) // 2352 * 2048

    def __len__(self):
        return self.size

    def __getitem__(self, k):
        if not isinstance(k, slice):
            return self[k:k + 1][0]
        start, stop = k.start or 0, min(k.stop if k.stop is not None else self.size, self.size)
        out = bytearray()
        pos = start
        while pos < stop:
            lba, off = divmod(pos, 2048)
            n = min(2048 - off, stop - pos)
            self.f.seek(lba * 2352 + 24 + off)
            out += self.f.read(n)
            pos += n
        return bytes(out)


def exe_toc(user):
    """The game's own file index (XENOGEAR.EXE at 0x80010004, as Weltall's FGameFileIndex reads it) of a disc stream:
    the RUS disc's files lie at other sectors than sector 24's table says (file 1650: 202458, not 202437)."""
    import struct
    from xfs import read_toc
    pvd = user[16 * 2048:17 * 2048]
    lba, size = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
    d, p = user[lba * 2048:lba * 2048 + size], 0
    exe = None
    while p < len(d):
        n = d[p]
        if n == 0:
            p = (p // 2048 + 1) * 2048
            continue
        name = d[p + 33:p + 33 + d[p + 32]]
        if name.startswith(b'XENOGEAR.EXE'):
            el, es = struct.unpack_from('<I', d, p + 2)[0], struct.unpack_from('<I', d, p + 10)[0]
            exe = user[el * 2048:el * 2048 + es]
        p += n
    t_addr = struct.unpack_from('<I', exe, 0x18)[0]
    off = 0x800 + 0x80010004 - t_addr
    return read_toc(bytes(24 * 2048) + exe[off:off + 0x7ffc])


def rus_disc(n=1):
    u = RawUser(RUS_BIN if n == 1 else RUS_BIN2)
    return u, exe_toc(u)


def pack_names(refresh=False):
    """Base names (no extension) of the pack's files; cached in pack_names.txt (listing 380k files takes a minute)."""
    if refresh or not os.path.exists(NAMES):
        open(NAMES, 'w').write('\n'.join(os.listdir(PACK)))
    return {n.rsplit('.', 1)[0] for n in open(NAMES).read().split('\n') if n}


def hd(name):
    """RGBA of a pack file <name>.bc7 (PSX alpha convention) or None."""
    p = os.path.join(PACK, name + '.bc7')
    return read_bc7_level0(p) if os.path.exists(p) else None


def show(rgba):
    """PSX-convention RGBA -> viewable RGB on magenta (transparent = (0,0,0,0))."""
    out = np.zeros(rgba.shape[:2] + (3,), np.uint8)
    out[:] = (255, 0, 255)
    m = ~(rgba == 0).all(-1)
    out[m] = rgba[..., :3][m]
    return out


def npc_set(nid):
    d = os.path.join(NPC, nid)
    return (json.load(open(os.path.join(d, 'layout.json')))['npc'], json.load(open(os.path.join(d, 'uses.json'))),
            np.load(os.path.join(d, 'page.npy')), json.load(open(os.path.join(d, 'pal.json')))['palettes_raw'])


def sprite_rgb(idx, pal_raw, scale=S):
    a = rgba_from_idx(idx, pal_raw)
    out = np.zeros(a.shape[:2] + (3,), np.uint8)
    out[:] = (255, 0, 255)
    out[a[..., 3] > 0] = a[..., :3][a[..., 3] > 0]
    return np.repeat(np.repeat(out, scale, 0), scale, 1)


def side_by_side(cells, gap=8, bg=(40, 40, 40)):
    H = max(c.shape[0] for c in cells)
    W = sum(c.shape[1] + gap for c in cells)
    sheet = Image.new('RGB', (W, H), bg)
    x = 0
    for c in cells:
        sheet.paste(Image.fromarray(np.ascontiguousarray(c)), (x, 0))
        x += c.shape[1] + gap
    return sheet


def install_files(src_dir, names, log_path, ext='.bc7'):
    """Copy <name><ext> from src_dir into the pack and the mod's pack, only names neither has; append to log_path."""
    done = []
    for n in names:
        a, b = os.path.join(PACK, n + ext), os.path.join(MOD_PACK, n + ext)
        if os.path.exists(a) or os.path.exists(os.path.join(PACK, n + '.png')):
            continue
        data = open(os.path.join(src_dir, n + ext), 'rb').read()
        open(a, 'wb').write(data)
        if not os.path.exists(b):
            open(b, 'wb').write(data)
        done.append(n + ext)
    with open(log_path, 'a') as f:
        f.writelines(n + '\n' for n in done)
    return done
