"""LoRA v3 dataset from the 16x re-fits (ai/fit16, tools/refit16.py).

  python make_pairs_v3.py [--out ai/pairs_v3] [--test-out ai/pairs_v3_test] [--boards-only]
Triplets (control | ref | target) + mask, names <job>__<set>_<fi>[__head|__noref|__r2]:
  full  : sprite 8x on the 512 canvas (feet 500) -> teacher redraw at honest 8x (16x fit, area-downscaled)
  head  : 32x32 native window around the head at 16x (512 px) -> teacher 16x crop; caption "close-up of the head: ..."
  npc   : real map NPCs drawn by the teacher (Lahan), with an NPC board made of their own teacher frames
  noref : ~150 real NPC frames with the blank grey board and the no-reference caption
  gear  : as in v2 (blank board, mecha caption), honest 8x targets
Boards v3 (512 px): top 60 % = ChatGPT turnaround (characters) or teacher frames (NPCs); bottom row = teacher head
front | ChatGPT face (NPC: teacher head) | teacher head side/back. Frames used on a board are not used as targets
with that board. 30 % of character triplets keep the v2 board. Masks: background 0, body 140, head 255
(head and gear triplets: silhouette 255). Held-out jobs go to --test-out with the teacher target for evaluation.
"""
import argparse
import glob
import hashlib
import json
import re
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import MAG, place  # noqa: E402
from make_pairs_v2 import ref_board  # noqa: E402
from render_build import CAP_MECHA, CAP_NOREF, CAP_REF  # noqa: E402

AI = os.path.join(ROOT, 'ai')
FIT = os.path.join(AI, 'fit16')
FC = os.path.join(ROOT, 'for_chatgpt')
CAP_HEAD = 'close-up of the head: ' + CAP_REF
GREY = (205, 205, 205)
HOLD_JOBS = {'h_fei_b3005_0', 'g_worldmap_3951'}
HOLD_SLUGS = {'alice', 'timothy', 'sophia', 'grahf'}
HOLD_NPCS = 2
HEAD_N = 32           # head window, native px
SMALL = 20            # characters with fewer full frames are duplicated (__r2)
OLD_BOARD = 0.30


def load_index():
    idx = {}
    for p in sorted(glob.glob(os.path.join(FIT, 'index*.json'))):
        idx.update(json.load(open(p)))
    return idx


def ident(job, v):
    """Identity key that owns a board: character slug, 'npc:<id>' or None for gears."""
    if v['kind'] == 'gear':
        return None
    if v['kind'] == 'npc':
        return 'npc:' + re.sub(r'_r\d+$', '', job[2:])  # retry jobs (m_<nid>_r1) belong to the same NPC
    return v['slug']


def stable(name, k=100):
    return int(hashlib.md5(name.encode()).hexdigest(), 16) % k


def head_window(h, setkey, fi):
    """Native window (x0, y0) of HEAD_N px: centred on the topmost part, starting 4 px above the sprite top."""
    places = h.placements(setkey, fi)
    _, (ox, oy) = h.assemble(places)
    top = min(places, key=lambda p: p['y'])
    cx = top['x'] - ox + top['w'] / 2
    return int(round(cx - HEAD_N / 2)), (top['y'] - oy) - 4


def crop_pad(arr, x0, y0, n, fill):
    """n x n crop at (x0, y0) of an HxWxC array, padded with fill outside."""
    H, W = arr.shape[:2]
    out = np.empty((n, n, arr.shape[2]), arr.dtype)
    out[:] = fill
    sx0, sy0, dx0, dy0 = max(0, x0), max(0, y0), max(0, -x0), max(0, -y0)
    sx1, sy1 = min(W, x0 + n), min(H, y0 + n)
    if sx1 > sx0 and sy1 > sy0:
        out[dy0:dy0 + sy1 - sy0, dx0:dx0 + sx1 - sx0] = arr[sy0:sy1, sx0:sx1]
    return out


def on_bg(rgb, alpha, bg):
    out = rgb.copy()
    out[alpha < 128] = bg
    return out


def place_mask(m, size, feet):
    """place() for a single-channel mask (same scaling and position as the sprite)."""
    c = Image.new('L', (size, size), 0)
    if m.height > feet or m.width > size:
        k = min(feet / m.height, size / m.width)
        m = m.resize((int(m.width * k), int(m.height * k)), Image.NEAREST)
    c.paste(m, ((size - m.width) // 2, feet - m.height))
    return c


def skin_score(rgb, alpha):
    """Share of skin-like pixels in a head crop and their horizontal offset from the centre (-1..1)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(int)
    m = (alpha > 128) & (hsv[..., 0] >= 3) & (hsv[..., 0] <= 22) & (hsv[..., 1] >= 50) & (hsv[..., 1] <= 190) & (hsv[..., 2] >= 110)
    a = (alpha > 128).sum()
    if not a or not m.any():
        return 0.0, 0.0
    xs = np.where(m)[1]
    return m.sum() / a, (xs.mean() / rgb.shape[1] - 0.5) * 2


class Frame:
    def __init__(self, job, v, key, h):
        self.job, self.key, self.h = job, key, h
        self.kind, self.ident = v['kind'], ident(job, v)
        self.setkey, fi = key.rsplit('_', 1)
        self.fi = int(fi)
        self.name = f'{job}__{self.setkey}_{self.fi:03d}'
        self._o8 = self._f16 = None

    def o8(self):
        if self._o8 is None:
            self._o8 = frame_rgba(self.h, self.setkey, self.fi)
        return self._o8

    def f16(self):
        if self._f16 is None:
            self._f16 = np.asarray(Image.open(os.path.join(FIT, self.job, self.key + '.png')).convert('RGBA'))
        return self._f16

    def head16(self, bg):
        """(control, target, alpha) of the head window at 16x, or None when the window is mostly empty."""
        x0, y0 = head_window(self.h, self.setkey, self.fi)
        n = HEAD_N * 16
        f = self.f16()
        a = crop_pad(f[..., 3:], x0 * 16, y0 * 16, n, 0)[..., 0]
        if (a > 128).mean() < 0.15:
            return None
        o = np.asarray(self.o8())
        o16 = cv2.resize(o, (o.shape[1] * 2, o.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
        ctrl = crop_pad(o16, x0 * 16, y0 * 16, n, 0)
        c = on_bg(ctrl[..., :3], ctrl[..., 3], MAG)
        t = on_bg(crop_pad(f[..., :3], x0 * 16, y0 * 16, n, 0), a, bg)
        return c, t, a

    def full8(self):
        """(control, target, head box in 8x frame px) on the 512 canvas."""
        o = self.o8()
        f = self.f16()
        rgb = cv2.resize(np.ascontiguousarray(f[..., :3]), o.size, interpolation=cv2.INTER_AREA)
        t = Image.fromarray(np.dstack([rgb, np.asarray(o)[..., 3]]), 'RGBA')
        return place(o, 512, 500), place(t, 512, 500)

    def mask8(self, weighted):
        o = self.o8()
        al = (np.asarray(o)[..., 3] > 127).astype(np.uint8)
        if not weighted:
            return place_mask(Image.fromarray(al * 255), 512, 500)
        m = al * 140
        places = self.h.placements(self.setkey, self.fi)
        _, (ox, oy) = self.h.assemble(places)
        top = min(places, key=lambda p: p['y'])
        x0, y0 = (top['x'] - ox - 2) * 8, (top['y'] - oy - 2) * 8
        x1, y1 = (top['x'] - ox + top['w'] + 2) * 8, (top['y'] - oy + top['h'] + 2) * 8
        sub = m[max(0, y0):y1, max(0, x0):x1]
        sub[sub > 0] = 255
        return place_mask(Image.fromarray(m.astype(np.uint8)), 512, 500)

    def head_thumb(self, size=170):
        x0, y0 = head_window(self.h, self.setkey, self.fi)
        f = self.f16()
        n = HEAD_N * 16
        a = crop_pad(f[..., 3:], x0 * 16, y0 * 16, n, 0)[..., 0]
        t = on_bg(crop_pad(f[..., :3], x0 * 16, y0 * 16, n, 0), a, GREY)
        s, off = skin_score(crop_pad(f[..., :3], x0 * 16, y0 * 16, n, 0), a)
        self.cover = float((a > 128).mean())
        return Image.fromarray(t).resize((size, size), Image.LANCZOS), (s, off)

    def drop(self):
        self._o8 = self._f16 = None

    def full_thumb(self, w, h):
        f = self.f16()
        im = Image.fromarray(on_bg(f[..., :3], f[..., 3], GREY))
        im.thumbnail((w, h), Image.LANCZOS)
        return im


def field_frame(fr):
    """Walking / standing frames (map sets 400-449, cut-scene sets, NPC sets): the head is the topmost part there."""
    if fr.setkey == 'npc':
        return True
    try:
        n = int(fr.setkey.split('_')[0])
    except ValueError:
        return False
    return 400 <= n < 450 or 2336 <= n <= 2460


def pick_heads(frames):
    """(front, side_or_back) frames by skin share / horizontal offset of the skin in the head crop."""
    frames = [f for f in frames if field_frame(f)] or frames
    sc = []
    for fr in frames:
        try:
            _, (s, off) = fr.head_thumb(64)
        except Exception:  # noqa: BLE001
            continue
        finally:
            fr.drop()
        if getattr(fr, 'cover', 0) >= 0.3:
            sc.append((s, off, fr))
    if not sc:
        return []
    front = max(sc, key=lambda t: t[0] - 0.5 * abs(t[1]))
    smax = front[0]
    side = [t for t in sc if t[2] is not front[2] and 0.25 * smax <= t[0] <= 0.7 * smax]
    other = max(side, key=lambda t: abs(t[1]))[2] if side else min(sc, key=lambda t: t[0])[2]
    return [front[2]] if other is front[2] else [front[2], other]


def board_v3(slug, frames):
    """Character board: ChatGPT sheet top, bottom row teacher head | ChatGPT face | teacher head."""
    b = Image.new('RGB', (512, 512), GREY)
    sh = Image.open(os.path.join(FC, slug, 'chatgpt_sheet.png')).convert('RGB')
    sh.thumbnail((512, 307), Image.LANCZOS)
    b.paste(sh, ((512 - sh.width) // 2, 0))
    heads = pick_heads(frames)
    fa = Image.open(os.path.join(FC, slug, 'chatgpt_face.png')).convert('RGB')
    fa.thumbnail((170, 170), Image.LANCZOS)
    y = 512 - 170
    b.paste(fa, (171 + (170 - fa.width) // 2, y + (170 - fa.height) // 2))
    for k, fr in enumerate(heads[:2]):
        b.paste(fr.head_thumb()[0], (0 if k == 0 else 342, y))
    return b, heads


def board_npc(frames, min_frames=6):
    """NPC board: up to 4 teacher frames on top, 3 teacher heads below (all from the board frames)."""
    b = Image.new('RGB', (512, 512), GREY)
    sc = []
    for fr in frames:
        try:
            _, (s, off) = fr.head_thumb(64)
            sc.append((s, off, fr))
        except Exception:  # noqa: BLE001
            pass
        fr.drop()
    if len(sc) < min_frames:
        return None, []
    sc.sort(key=lambda t: -t[0])
    pick = [sc[0][2], sc[len(sc) // 3][2], sc[2 * len(sc) // 3][2], sc[-1][2]]  # front .. back
    for k, fr in enumerate(pick):
        im = fr.full_thumb(126, 300)
        b.paste(im, (k * 128 + (128 - im.width) // 2, 300 - im.height))
    for k, fr in enumerate([pick[0], pick[1], pick[3]]):
        b.paste(fr.head_thumb()[0], (k * 171, 342))
    return b, pick


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(AI, 'pairs_v3'))
    ap.add_argument('--test-out', default=os.path.join(AI, 'pairs_v3_test'))
    ap.add_argument('--boards-only', action='store_true')
    ap.add_argument('--min-board-frames', type=int, default=6, help='NPC board needs this many teacher frames (small NPC sets have only 1-4)')
    ap.add_argument('--hold-npcs', default='', help='comma list of NPC ids kept out of training (default: the 2 largest)')
    ap.add_argument('--npc-cap', type=int, default=0, help='max full-frame targets per NPC (0 = all)')
    ap.add_argument('--noref-every', type=int, default=0, help='one blank-board triplet for every N-th NPC (0 = 6 per NPC)')
    ap.add_argument('--no-test', action='store_true', help='do not write held-out triplets (the test set is kept fixed)')
    a = ap.parse_args()
    idx = load_index()
    excl_p = os.path.join(AI, 'campaign', '_exclude_frames.json')
    excl = {(j, t.replace(':', '_')) for j, ts in (json.load(open(excl_p)).items() if os.path.exists(excl_p) else []) for t in ts}
    heroes, by_ident, gears = {}, {}, []
    for job, v in sorted(idx.items()):
        if v['hero_dir'] not in heroes:
            heroes[v['hero_dir']] = Hero(os.path.join(ROOT, v['hero_dir']))
        for key in sorted(v['frames']):
            s, fi = key.rsplit('_', 1)
            if (job, f'{s}_{int(fi)}') in excl:
                continue
            fr = Frame(job, v, key, heroes[v['hero_dir']])
            (gears.append(fr) if fr.ident is None else by_ident.setdefault(fr.ident, []).append(fr))
    npcs = sorted(k for k in by_ident if k.startswith('npc:'))
    for k in npcs:  # one teacher per NPC: campaign (Nano Banana) frames win over the older pilot (n_*) frames
        if any(f.job.startswith('m_') for f in by_ident[k]):
            by_ident[k] = [f for f in by_ident[k] if f.job.startswith('m_')]
    if a.hold_npcs:
        hold_npc = {'npc:' + n for n in a.hold_npcs.split(',')}
    else:
        hold_npc = set(sorted(npcs, key=lambda k: -len(by_ident[k]))[:HOLD_NPCS])
    print('identities', len(by_ident), 'npcs', len(npcs), 'held-out npcs', sorted(hold_npc), 'gear frames', len(gears))

    bdir = os.path.join(a.out, 'boards')
    os.makedirs(bdir, exist_ok=True)
    boards, board_frames = {}, {}
    for ident_, frs in sorted(by_ident.items()):
        if ident_.startswith('npc:'):
            b, used = board_npc(frs, a.min_board_frames)
            if b is None:
                continue
        else:
            if not os.path.exists(os.path.join(FC, ident_, 'chatgpt_sheet.png')):
                print('no ChatGPT sheet for', ident_)
                continue
            b, used = board_v3(ident_, frs)
            boards[ident_ + '@v2'] = ref_board(ident_)
            boards[ident_ + '@v2'].save(os.path.join(bdir, ident_.replace(':', '_') + '@v2.png'))
        boards[ident_] = b
        board_frames[ident_] = {f.name for f in used}
        b.save(os.path.join(bdir, ident_.replace(':', '_') + '.png'))
    Image.new('RGB', (512, 512), GREY).save(os.path.join(bdir, '_blank.png'))
    print('boards', len([k for k in boards if '@' not in k]))
    if a.boards_only:
        return

    for root in (a.out, a.test_out):
        for d in ('control', 'ref', 'target', 'mask'):
            os.makedirs(os.path.join(root, d), exist_ok=True)
    split = {'train': [], 'test': []}
    stats = {}

    def write(root, name, c, r, t, m, cap):
        c.save(os.path.join(root, 'control', name + '.png'))
        r.save(os.path.join(root, 'ref', name + '.png'))
        t.save(os.path.join(root, 'target', name + '.png'))
        m.save(os.path.join(root, 'mask', name + '.png'))
        open(os.path.join(root, 'target', name + '.txt'), 'w').write(cap)
        split['test' if root == a.test_out else 'train'].append(name)
        kind = name.split('__')[-1] if name.count('__') > 1 else 'full'
        stats[kind] = stats.get(kind, 0) + 1

    blank = Image.new('RGB', (512, 512), GREY)
    for ident_, frs in sorted(by_ident.items()):
        if ident_ not in boards:
            continue
        is_npc = ident_.startswith('npc:')
        held = ident_ in hold_npc or ident_ in HOLD_SLUGS
        usable = [f for f in frs if f.name not in board_frames[ident_]]
        if is_npc and a.npc_cap and len(usable) > a.npc_cap:  # evenly spaced subset: different poses / directions
            usable = [usable[round(i * (len(usable) - 1) / (a.npc_cap - 1))] for i in range(a.npc_cap)]
        reps = 2 if (not held and not is_npc and len(usable) < SMALL) else 1
        if a.noref_every:
            noref_left = 1 if is_npc and not held and stable(ident_, a.noref_every) == 0 else 0
        else:
            noref_left = 6 if is_npc and not held else 0
        for fr in usable:
            held_fr = held or fr.job in HOLD_JOBS
            if held_fr and a.no_test:
                continue
            root = a.test_out if held_fr else a.out
            try:
                c, t = fr.full8()
                mk = fr.mask8(True)
                hd = fr.head16(MAG)
            except Exception as e:  # noqa: BLE001
                print('skip', fr.name, e)
                continue
            use_old = not is_npc and not held_fr and stable(fr.name) < OLD_BOARD * 100
            board = boards[ident_ + '@v2'] if use_old else boards[ident_]
            for k in range(reps):
                sfx = '' if k == 0 else '__r2'
                write(root, fr.name + sfx, c, board, t, mk, CAP_REF)
                if hd is not None:
                    hc, ht, ha = hd
                    write(root, fr.name + '__head' + sfx, Image.fromarray(hc), board, Image.fromarray(ht),
                          Image.fromarray(np.where(ha > 128, 255, 0).astype(np.uint8)), CAP_HEAD)
            if noref_left and (a.noref_every or stable(fr.name, 7) < 3):
                write(root, fr.name + '__noref', c, blank, t, mk, CAP_NOREF)
                noref_left -= 1
            fr.drop()
    for fr in gears:
        if fr.job in HOLD_JOBS and a.no_test:
            continue
        root = a.test_out if fr.job in HOLD_JOBS else a.out
        try:
            c, t = fr.full8()
            write(root, fr.name, c, blank, t, fr.mask8(False), CAP_MECHA)
        except Exception as e:  # noqa: BLE001
            print('skip', fr.name, e)
        fr.drop()
    json.dump(split, open(os.path.join(a.out, 'split.json'), 'w'), indent=0)
    json.dump({'board_frames': {k: sorted(v) for k, v in board_frames.items()}, 'hold_npc': sorted(hold_npc)},
              open(os.path.join(a.out, 'boards.json'), 'w'), indent=0)
    print('train', len(split['train']), 'test', len(split['test']), stats)


if __name__ == '__main__':
    main()
