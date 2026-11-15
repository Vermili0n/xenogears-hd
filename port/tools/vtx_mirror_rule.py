"""How the game's own GPU UVs of a sprite piece differ when it is drawn mirrored (the user's core's vertex journal).

The journal (XENO_VTX_* in the user's Beetle core) holds every textured primitive with its screen corners and the UVs the
game sent. A sprite's piece is a quad lying square on the screen. The same piece drawn straight and mirrored (a character
turned the other way) has the same CLUT, rows and width; this compares the texel columns its UVs span either way.

Usage: python vtx_mirror_rule.py <xeno_vtx.log> [...]
"""
import re
import sys
from collections import Counter, defaultdict

LINE = re.compile(r'^f(\d+) prim (\d+) n(\d+) mode (\d+) clut (\d+),(\d+) tex (\d+),(\d+) (\d+)x(\d+) hd(\d) \|(.*)$')
VTX = re.compile(r'\(([-\d.]+),([-\d.]+) uv(\d+),(\d+)\)')


def quads(paths):
    for path in paths:
        for line in open(path, encoding='ascii', errors='replace'):
            m = LINE.match(line.strip())
            if not m or m.group(3) != '4':
                continue
            v = [(float(a), float(b), int(c), int(d)) for a, b, c, d in VTX.findall(m.group(12))]
            if len(v) == 4:
                yield (int(m.group(5)), int(m.group(6))), int(m.group(4)), v


def square_on_screen(v):
    """Corners 0-1 along x and 0-2 along y, as the GPU's quad order puts a sprite's piece; None when not."""
    (x0, y0, *_), (x1, y1, *_), (x2, y2, *_), (x3, y3, *_) = v
    if abs(y0 - y1) > 0.01 or abs(y2 - y3) > 0.01 or abs(x0 - x2) > 0.01 or abs(x1 - x3) > 0.01:
        return None
    return x1 - x0, y2 - y0


def main(paths):
    pieces = defaultdict(Counter)   # (clut, mode, v range, |du|) -> Counter of (mirrored, u range)
    spans = Counter()
    for clut, mode, v in quads(paths):
        size = square_on_screen(v)
        if size is None:
            continue
        dx, dy = size
        du = v[1][2] - v[0][2]
        dv = v[2][3] - v[0][3]
        if du == 0 or dv == 0 or dy <= 0:
            continue
        mirrored = (dx > 0) != (du > 0)
        spans[(mirrored, round(abs(dx) / abs(du), 2))] += 1
        key = (clut, mode, min(v[0][3], v[2][3]), max(v[0][3], v[2][3]), abs(du))
        pieces[key][(mirrored, min(v[0][2], v[1][2]), max(v[0][2], v[1][2]))] += 1
    print('screen width / |du| by mirrored (top 12):')
    for (mirrored, ratio), n in spans.most_common(12):
        print(f'  mirrored={mirrored} ratio={ratio} x{n}')
    offsets = Counter()
    examples = []
    for key, seen in pieces.items():
        straight = {(lo, hi) for (m, lo, hi) in seen if not m}
        mirror = {(lo, hi) for (m, lo, hi) in seen if m}
        for lo, hi in straight:
            for mlo, mhi in mirror:
                if abs(mlo - lo) <= 2 and abs(mhi - hi) <= 2:
                    offsets[(mlo - lo, mhi - hi)] += 1
                    if len(examples) < 8:
                        examples.append((key, (lo, hi), (mlo, mhi)))
    print('mirrored u range minus straight u range, for the same piece (lo, hi):')
    for off, n in offsets.most_common():
        print(f'  {off}: x{n}')
    for key, s, m in examples:
        print('  e.g. clut', key[0], 'mode', key[1], 'rows', key[2], key[3], '|du|', key[4], 'straight', s, 'mirrored', m)


if __name__ == '__main__':
    main(sys.argv[1:])
