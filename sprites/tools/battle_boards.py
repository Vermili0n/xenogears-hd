"""Self boards for battle sets drawn without a reference: a board made of the set's own good HD frames, in the layout
the LoRA saw for map NPCs (make_pairs_v3.board_npc: frames on top, three close-ups below), so that a second render
keeps one identity and one palette over the whole set.

  python battle_boards.py <out dir> [--bad flags.json] [--rank rank.json] [--picks picks.json] <group> ...
Frames come from ai/prod_work/<group>/parts as the game draws them. --picks {group: {"frames": [f, f, f, f],
"heads": [[frame, x, y, size], x3]}} fixes the choice by hand (either key may be absent); otherwise four frames are taken
automatically: not in --bad, full-size, closest to the sprite (--rank, battle_qa.py), distinct poses; the close-ups show
the top of the figure. Writes <out>/self_<set id>.png, <out>/picks.json and contact sheets <out>/_sheet_<n>.png for
the eye check.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from battle_qa import frames_of  # noqa: E402
from make_pairs_v3 import GREY, crop_pad  # noqa: E402
from nisan_joe_post import game_frame  # noqa: E402


def auto_pick(h, sk, n, bad, zs):
    rows = []
    for fi in range(n):
        try:
            old, _ = h.assemble(h.placements(sk, fi))
        except Exception:  # noqa: BLE001  (empty frame)
            continue
        a = np.asarray(old)[..., 3] > 0
        rows.append((fi, int(a.sum()), np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((16, 16), Image.BOX), float).ravel() / 255))
    med = float(np.median([r[1] for r in rows]))
    cand = [r for r in rows if r[0] not in bad and r[1] >= 0.7 * med and zs.get(r[0], 0.0) < 1.5]
    if len(cand) < 4:
        cand = [r for r in rows if r[0] not in bad and r[1] >= 0.5 * med] or rows
    cand.sort(key=lambda r: zs.get(r[0], 0.0))  # closest to the sprite first
    pick = [min(cand, key=lambda r: r[0])]
    for far in (0.12, 0.06, 0.0):  # distinct poses, as far as the clean frames allow
        for c in cand:
            if len(pick) < 4 and all(c[0] != p[0] and float(np.abs(c[2] - p[2]).mean()) >= far for p in pick):
                pick.append(c)
    return [p[0] for p in pick]


def on_grey(im):
    g = Image.new('RGB', im.size, GREY)
    g.paste(im, (0, 0), im)
    return g


def board(h, sk, parts, pick, heads=None):
    cache = {}
    fr = [game_frame(h, sk, fi, parts, 8, cache) for fi in pick]
    hs = [im.height // 8 for im in fr]
    wide = float(np.median([im.width / im.height for im in fr])) > 0.9
    b = Image.new('RGB', (512, 512), GREY)
    top = [fr[0], fr[min(2, len(fr) - 1)]] if wide else fr  # wide monsters: two large frames instead of four tiny ones
    cw = 512 // len(top)
    for k, im in enumerate(top):
        t = on_grey(im)
        t.thumbnail((cw - 2, 300), Image.LANCZOS)
        b.paste(t, (k * cw + (cw - t.width) // 2, 300 - t.height))
    n = 32 if max(hs) < 56 else 48 if max(hs) < 90 else 64  # close-up window, native px
    for k, i in enumerate([0, min(1, len(fr) - 1), len(fr) - 1]):
        if heads:  # by hand: [frame, x, y, size] in native px of that frame
            fi, x0, y0, m = heads[k]
            a = np.asarray(game_frame(h, sk, fi, parts, 8, cache))
        else:  # the top of the figure: window centred on the silhouette's upper rows
            a, m = np.asarray(fr[i]), n
            x0, y0 = int(np.where(a[:m * 4, :, 3] > 0)[1].mean() / 8 - m / 2), -4
        c = crop_pad(a, x0 * 8, y0 * 8, m * 8, 0)
        b.paste(on_grey(Image.fromarray(c, 'RGBA')).resize((170, 170), Image.LANCZOS), (k * 171, 342))
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--bad', default='')
    ap.add_argument('--rank', default='')
    ap.add_argument('--picks', default='')
    ap.add_argument('groups', nargs='+')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    bad = json.load(open(a.bad)) if a.bad else {}
    rank = json.load(open(a.rank)) if a.rank else {}
    picks = json.load(open(a.picks)) if a.picks else {}
    used, boards = {}, []
    for g in a.groups:
        h, sk, parts, n = frames_of(g)
        zs = {fi: z for _, z, fi in rank.get(g, [])}
        hand = picks.get(g) or {}
        used[g] = {'frames': hand.get('frames') or auto_pick(h, sk, n, set(bad.get(g, [])), zs)}
        if hand.get('heads'):
            used[g]['heads'] = hand['heads']
        b = board(h, sk, parts, used[g]['frames'], used[g].get('heads'))
        b.save(os.path.join(a.out, f'self_{g[2:]}.png'))
        boards.append((g, used[g]['frames'], b))
        print(g, used[g], flush=True)
    json.dump(used, open(os.path.join(a.out, 'picks.json'), 'w'), indent=0)
    for k in range(0, len(boards), 6):
        c = Image.new('RGB', (3 * 520, 2 * 536), (60, 60, 60))
        d = ImageDraw.Draw(c)
        for i, (g, p, b) in enumerate(boards[k:k + 6]):
            x, y = (i % 3) * 520, (i // 3) * 536
            d.text((x + 4, y + 2), f'{g} {p}', fill=(255, 255, 0))
            c.paste(b, (x + 4, y + 18))
        c.save(os.path.join(a.out, f'_sheet_{k // 6 + 1}.png'))


if __name__ == '__main__':
    main()
