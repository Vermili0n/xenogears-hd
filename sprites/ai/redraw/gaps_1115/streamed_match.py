r"""Is a streamed block set (scan_streamed.py's candidates: files 2410, 2427, 3837) the same drawing as a drawn set?
  python streamed_match.py -> streamed\match.json + stdout
Every frame of the target (streamed\f<file>, extract_heroes cut) is assembled and compared texel for texel (opaque mask
and colours, after cropping to the figure) with every frame of every extracted set that has the target's palette
(extracted/disc1_full, gears_wm, battle, npc_full) - id_chi/retarget.match_frames, over all candidates.
"""
import json
import os

import numpy as np

from gcommon import HERE, ROOT
from ai_redraw import Hero  # noqa: E402

TARGETS = ['f2410', 'f2427', 'f3837']
ROOTS = ['disc1_full', 'gears_wm', 'battle', 'npc_full']


def crop(a):
    ys, xs = np.nonzero(a[..., 3] > 0)
    if not len(ys):
        return None
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def frames_of(h):
    out = {}
    for sk, s in h.layout.items():
        for fi in range(len(s['frames'])):
            try:
                img, _ = h.assemble(h.placements(sk, fi))
            except Exception:  # noqa: BLE001
                continue
            c = crop(np.asarray(img))
            if c is not None:
                out[(sk, fi)] = c
    return out


def key(c):
    return c.shape, (c[..., 3] > 0).tobytes(), np.where(c[..., 3:] > 0, c[..., :3], 0).tobytes()


def main():
    res = {}
    for t in TARGETS:
        th = Hero(os.path.join(HERE, 'streamed', t))
        pals = {p for s in th.layout.values() for p in s['palettes']}
        tf = frames_of(th)
        want = {key(c): k for k, c in tf.items()}
        hits = {}
        for r in ROOTS:
            base = os.path.join(ROOT, 'extracted', r)
            for d in sorted(os.listdir(base)):
                lp = os.path.join(base, d, 'layout.json')
                if not os.path.exists(lp):
                    continue
                lay = json.load(open(lp))
                if not pals & {p for s in lay.values() for p in s.get('palettes', [])}:
                    continue
                try:
                    sf = frames_of(Hero(os.path.join(base, d)))
                except Exception:  # noqa: BLE001
                    continue
                for k, c in sf.items():
                    tk = want.get(key(c))
                    if tk:
                        hits.setdefault(f'{tk[0]}:{tk[1]}', []).append(f'{r}/{d}:{k[0]}:{k[1]}')
        res[t] = {'frames': len(tf), 'matched': len(hits), 'palettes': sorted(pals), 'hits': hits}
        print(t, 'frames', len(tf), 'matched texel for texel', len(hits), 'palettes', sorted(pals),
              'sources', sorted({v.split(':')[0] for vs in hits.values() for v in vs}), flush=True)
    json.dump(res, open(os.path.join(HERE, 'streamed', 'match.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
