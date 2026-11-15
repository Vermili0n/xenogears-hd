"""Check the UV rule of textured quads in the core's vertex log (XENO_VTX_* env, custom core).

  python tools/vtx_uv_check.py <RETROARCH_DRIVE>/RetroArch/logs/xeno_vtx.old.log <RETROARCH_DRIVE>/RetroArch/logs/xeno_vtx.log [--frames 50]

For every 4-vertex polygon the screen length of its two edges is compared with the UV change along them.
Field sprites showed the "size - 1" rule: a w-texel part is drawn w pixels wide while its UVs span only w - 1
texels, so the game stretches the texture by w / (w - 1) (handled by batch_redraw --uv-compensate).
Per quad: scale_exact = L / du, scale_m1 = L / (du + 1); the right hypothesis gives the same scale on both edges
(and, for sprites at scale 1, scale_m1 == 1). Reports votes per texture mode / CLUT group and per frame range.
"""
import argparse
import math
import re
from collections import Counter, defaultdict

LINE = re.compile(r'^f(\d+) prim (\d+) n(\d+) mode (\d+) clut (\d+),(\d+) tex (\d+),(\d+) (\d+)x(\d+) hd(\d) \|(.*)$')
TOL = 0.025
VTX = re.compile(r'\(([-\d.]+),([-\d.]+) uv(\d+),(\d+)\)')


def parse(paths):
    for p in paths:
        try:
            fh = open(p, encoding='ascii', errors='replace')
        except FileNotFoundError:
            continue
        with fh:
            for ln in fh:
                m = LINE.match(ln.strip())
                if not m:
                    continue
                f, prim, n, mode, cx, cy, tx, ty, tw, th, hd, rest = m.groups()
                v = [(float(a), float(b), int(c), int(d)) for a, b, c, d in VTX.findall(rest)]
                yield dict(f=int(f), prim=int(prim), n=int(n), mode=int(mode), clut=(int(cx), int(cy)),
                           tex=(int(tx), int(ty), int(tw), int(th)), hd=int(hd), v=v)


def edge(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    du, dv = abs(b[2] - a[2]), abs(b[3] - a[3])
    return L, du, dv


def classify(q):
    """Return ('m1'|'exact'|'?', info) for an axis-aligned-in-UV quad (v0-v1 = u edge, v0-v2 = v edge)."""
    v = q['v']
    if len(v) != 4:
        return '?', None
    Lu, du, dv1 = edge(v[0], v[1])
    Lv, du2, dv = edge(v[0], v[2])
    if dv1 or du2 or du < 2 or dv < 2 or Lu < 1 or Lv < 1:
        return '?', None  # not a plain textured rectangle, or too small to tell
    e = (Lu / du, Lv / dv)
    m = (Lu / (du + 1), Lv / (dv + 1))
    de, dm = abs(e[0] - e[1]) / max(e), abs(m[0] - m[1]) / max(m)
    if dm < TOL <= de:
        return 'm1', (e, m)
    if de < TOL <= dm:
        return 'exact', (e, m)
    return '?', (e, m)


def spread(xs):
    xs = sorted(xs)
    med = xs[len(xs) // 2]
    return sum(abs(x - med) for x in xs) / len(xs) / med


def group_test(rows):
    """Per (frame, clut): all parts of one character share one scale. The hypothesis whose per-part scales
    spread less wins (small parts discriminate: for a 3-texel part the two differ by 33 %)."""
    g = defaultdict(list)
    for q in rows:
        c, info = classify(q)
        if info:
            g[(q['f'], q['clut'], q['mode'])].append(info)
    res = Counter()
    for k, infos in g.items():
        if len(infos) < 4:
            continue
        se = spread([x for e, _ in infos for x in e])
        sm = spread([x for _, m in infos for x in m])
        res['m1' if sm < se * 0.7 else 'exact' if se < sm * 0.7 else '?'] += 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('logs', nargs='+')
    ap.add_argument('--frames', type=int, default=0, help='only the last N logged frames')
    ap.add_argument('--polys-only', action='store_true', default=True)
    a = ap.parse_args()
    rows = [q for q in parse(a.logs) if q['n'] == 4]
    if not rows:
        print('no quads in', a.logs)
        return
    frames = sorted({q['f'] for q in rows})
    if a.frames:
        keep = set(frames[-a.frames:])
        rows = [q for q in rows if q['f'] in keep]
        frames = sorted(keep)
    print(f'quads {len(rows)}  frames {frames[0]}..{frames[-1]} ({len(frames)} logged)')
    print('prim types', Counter(q['prim'] for q in rows), ' modes', Counter(q['mode'] for q in rows),
          ' hd', Counter(q['hd'] for q in rows))
    votes = defaultdict(Counter)
    scales = defaultdict(list)
    for q in rows:
        c, info = classify(q)
        key = (q['prim'], q['mode'], q['clut'], q['hd'])
        votes[key][c] += 1
        if info and c != '?':
            scales[key].append(info[1] if c == 'm1' else info[0])
    print('\nprim mode clut        hd   m1  exact  ?   scale(med)  example tex')
    ex = {}
    for q in rows:
        ex.setdefault((q['prim'], q['mode'], q['clut'], q['hd']), q['tex'])
    tot = Counter()
    for key, c in sorted(votes.items(), key=lambda kv: -sum(kv[1].values())):
        tot.update(c)
        s = sorted(x[0] for x in scales[key])
        med = f'{s[len(s) // 2]:.3f}' if s else '-'
        if sum(c.values()) >= 4:
            print(f'{key[0]:>4} {key[1]:>4} {str(key[2]):<11} {key[3]:>2} {c["m1"]:>5} {c["exact"]:>5} {c["?"]:>4}   {med:>8}   {ex[key]}')
    print('\nTOTAL per quad', dict(tot))
    print('per character group (frame, clut):', dict(group_test(rows)))


if __name__ == '__main__':
    main()
