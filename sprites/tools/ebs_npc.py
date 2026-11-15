"""ebsynth fill for massovka NPCs (run on the laptop): every cover frame without a model redraw is synthesized from
the two nearest keyframes that passed QA.

  python ebs_npc.py --plan ai/npc_lahan/plan.json [--ids a,b]
Reads extracted/npc/<id> and ai/npc_<id>_prod/work/npc_<k>_red.png; writes npc_<t>_red.png there (+ fills.json).
"""
import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from ebs_fill import Frames, fill_one  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--ids', default='')
    a = ap.parse_args()
    plan = json.load(open(os.path.join(ROOT, a.plan) if not os.path.isabs(a.plan) else a.plan))
    ids = a.ids.split(',') if a.ids else list(plan)
    t0 = time.time()
    done = 0
    for nid in ids:
        work = os.path.join(ROOT, 'ai', f'npc_{nid}_prod', 'work')
        if not os.path.isdir(work):
            print(nid, 'no work dir', flush=True)
            continue
        have = sorted(int(f.split('_')[1]) for f in os.listdir(work) if f.startswith('npc_') and f.endswith('_red.png'))
        old = os.path.join(work, 'fills.json')
        if os.path.exists(old):  # frames synthesized in an earlier run are redone, never used as keys
            prev = {int(k) for k in json.load(open(old))}
            have = [f for f in have if f not in prev]
        keys = [k for k in plan[nid]['keys'] if k in have]
        if not keys:
            print(nid, 'no keyframes passed', flush=True)
            continue
        F = Frames(Hero(os.path.join(ROOT, 'extracted', 'npc', nid)), 'npc')
        desc = {}

        def d(fi):
            """Pose/colour descriptor: frame bottom-centred on a fixed canvas, downscaled."""
            if fi not in desc:
                c4, m4, _ = F.get(fi)
                rgba = np.dstack([c4, m4.astype(np.uint8) * 255])
                can = np.zeros((360, 300, 4), np.uint8)
                hh, ww = min(360, rgba.shape[0]), min(300, rgba.shape[1])
                can[360 - hh:, (300 - ww) // 2:(300 - ww) // 2 + ww] = rgba[-hh:, :ww]
                desc[fi] = np.asarray(Image.fromarray(can).resize((15, 18), Image.BOX), np.float32).reshape(-1)
            return desc[fi]

        fills = {}
        with tempfile.TemporaryDirectory() as tmp:
            for t in plan[nid]['cover']:
                if t in have:
                    continue
                # the two most similar passed keyframes (pose + facing), not the nearest by index
                near = sorted(keys, key=lambda k: float(np.abs(d(k) - d(t)).mean()))[:2]
                try:
                    fill_one(F, work, 'npc', t, near, tmp)
                    fills[t] = near
                    done += 1
                except Exception as ex:  # noqa: BLE001
                    print(nid, t, 'fail', ex, flush=True)
        json.dump(fills, open(os.path.join(work, 'fills.json'), 'w'))
        print(nid, 'filled', len(fills), f'({time.time() - t0:.0f}s total)', flush=True)
    print('DONE filled', done, flush=True)


if __name__ == '__main__':
    main()
