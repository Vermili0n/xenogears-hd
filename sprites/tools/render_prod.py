"""Production render package (LoRA v4 + v2 for gears): only part-cover frames, boards per identity, sharded jobs.

  python render_prod.py --out ai/prod [--workers 12] [--count]
Groups:
  important - heroes + story characters (incl. map NPC sets confirmed as them, ai/story_match/decisions.json):
              full frame + 16x head pass, the identity's v3 board (ai/pairs_v4/boards/<slug>.png or
              for_chatgpt/<slug>/board_v3.png); gears: blank board + mecha caption, rendered with LoRA v2
  massovka  - map NPC sets with a board (ai/pairs_v4/boards, ai/boards_extra accepted, own_board decisions); no head pass
  battle    - only battle sets whose palette matches an identity / boarded NPC (BATTLE_MAP); other monsters later
Frames: per group a greedy cover of all its parts (block-pal) - every texture is drawn once, frames that bring
no new part are not rendered. Parts already installed by the pilots (DONE_PARTS) are left out.
Writes <out>/control/*.png, <out>/boards/*.png, <out>/jobs_v4.json, <out>/jobs_v2.json, <out>/meta.json.
"""
import argparse
import json
import os
import shutil
import sys
from multiprocessing import Pool

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_grids import frame_rgba  # noqa: E402
from make_pairs import place  # noqa: E402
from make_pairs_v3 import CAP_HEAD, GREY, head_window  # noqa: E402
from render_build import BLANK, CAP_MECHA, CAP_REF, groups  # noqa: E402
from render_set import head_control  # noqa: E402

B4 = os.path.join(ROOT, 'ai', 'pairs_v4', 'boards')
BX = os.path.join(ROOT, 'ai', 'boards_extra', 'boards')
# parts installed by the v4 pilots (Alice, Timothy, 2 Lahan villagers, Fei battle + deathblows)
DONE_DIRS = ['p3h_alice', 'p3h_timothy', 'p3n_npc36e3', 'p3n_npcf6ad', 'p3h_fei', 'p4h_fei', 'p5h_fei']
DONE_GROUPS = {'c_alice_3d2b1c', 'c_timothy_d8943c', 'm_36e3637a9a', 'm_f6ad8ce563'}
# battle sets whose palette matches a boarded identity (28.10 check): group -> board slug / npc id
BATTLE_MAP = {'b_1416323aa6': 'rico', 'b_6e4318387b': 'elly', 'b_3dfe522a32': 'npc:f7eebf297c',
              'b_4165d11931': 'npc:477633c50b', 'b_4c0acc20fc': 'npc:ff1a494be6'}


def slug_board(slug):
    for p in (os.path.join(B4, slug + '.png'), os.path.join(ROOT, 'for_chatgpt', slug, 'board_v3.png')):
        if os.path.exists(p):
            return p
    return None


def npc_board(nid):
    acc = set(json.load(open(os.path.join(BX, '..', 'accepted.json')))['accepted'])
    for d, name in ((B4, f'npc_{nid[:10]}.png'), (BX, f'npc_{nid[:10]}.png')):
        if os.path.exists(os.path.join(d, name)) and (d == B4 or name in acc):
            return os.path.join(d, name)
    return None


def part_names(lay, sk, fi):
    v = lay[sk]
    pal = v['palettes']
    return {f"{q['block']}-{pal[min(q['clut'], len(pal) - 1)]}" for q in v['frames'][fi]}


def cover(lay, sets, done):
    frames = []
    for sk in sets:
        for fi in range(len(lay[sk]['frames'])):
            p = part_names(lay, sk, fi) - done
            if p:
                frames.append((sk, fi, p))
    left = set().union(*[f[2] for f in frames]) if frames else set()
    out = []
    while left:
        sk, fi, p = max(frames, key=lambda t: len(t[2] & left))
        out.append((sk, fi))
        left -= p
    return out


def plan():
    """[(group, hero_dir, [(set, frame)], board path or None, kind)] kind: hero | gear | npc"""
    done = set()
    for d in DONE_DIRS:
        p = os.path.join(ROOT, 'ai', d, 'parts')
        if os.path.isdir(p):
            done |= {f[:-4] for f in os.listdir(p) if f.endswith('.png')}
    dec = json.load(open(os.path.join(ROOT, 'ai', 'story_match', 'decisions.json')))
    own = {n: v for n, v in dec.get('own_board', {}).items()}
    items, skipped = [], []
    for g, hd, sk, cap in groups('important'):
        if g in DONE_GROUPS:
            continue
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        if cap == CAP_MECHA:
            items.append((g, hd, cover(lay, list(sk), done), None, 'gear'))
            continue
        by_slug = {}
        for s, slug in sk.items():
            by_slug.setdefault(slug, []).append(s)
        for slug, sets in by_slug.items():  # emeralda: child / adult sets have different boards
            b = slug_board(slug)
            if b is None:
                skipped.append((g, slug, 'no board'))
                continue
            items.append((g if len(by_slug) == 1 else f'{g}_{slug}', hd, cover(lay, sets, done), b, 'hero'))
    for g, hd, sk, cap in groups('massovka'):
        if g in DONE_GROUPS:
            continue
        nid = os.path.basename(hd)
        b = own[nid]['board'] if nid in own else npc_board(nid)
        if b is not None and not os.path.isabs(b):
            b = os.path.join(ROOT, b)
        if b is None:
            skipped.append((g, nid, 'no NPC board'))
            continue
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        kind = 'hero' if nid in own and own[nid]['identity'] == 'karellen_past' else 'npc'
        items.append((g, hd, cover(lay, list(sk), done), b, kind))
    for g, hd, sk, cap in groups('battle'):
        if g not in BATTLE_MAP:
            continue
        ident = BATTLE_MAP[g]
        b = npc_board(ident[4:]) if ident.startswith('npc:') else slug_board(ident)
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        items.append((g, hd, cover(lay, list(sk), done), b, 'npc' if ident.startswith('npc:') else 'hero'))
    return items, skipped


def build_group(args):
    """Controls of one group -> (jobs, meta). Runs in a worker process."""
    g, hd, frames, board, kind, out = args
    h = Hero(hd)
    bname = 'boards/_blank.png' if board is None else f'boards/{os.path.basename(board)}'
    jobs, meta = [], {}
    for sk, fi in frames:
        name = f'{g}__{sk}_{fi:03d}'
        try:
            o8 = frame_rgba(h, sk, fi)
        except Exception:  # noqa: BLE001  (empty frame)
            continue
        x0, y0 = head_window(h, sk, fi)
        meta[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': sk, 'frame': fi, 'head': [x0, y0],
                      'dups': [], 'group': g, 'kind': kind}
        place(o8, 512, 500).save(os.path.join(out, 'control', name + '.png'))
        jobs.append({'name': name, 'control': f'control/{name}.png', 'ref': bname,
                     'prompt': CAP_MECHA if kind == 'gear' else CAP_REF, 'lora': 'v2' if kind == 'gear' else 'v4'})
        if kind != 'hero':
            continue
        hc, cov = head_control(o8, x0, y0)
        if cov < 0.15:
            continue
        meta[name]['head_job'] = name + '__head'
        hc.save(os.path.join(out, 'control', name + '__head.png'))
        jobs.append({'name': name + '__head', 'control': f'control/{name}__head.png', 'ref': bname, 'prompt': CAP_HEAD,
                     'lora': 'v4'})
    return jobs, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'prod'))
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--count', action='store_true')
    a = ap.parse_args()
    items, skipped = plan()
    nf = {k: sum(len(f) for _, _, f, _, kk in items if kk == k) for k in ('hero', 'gear', 'npc')}
    print('groups', len(items), 'cover frames', nf, 'skipped', len(skipped))
    if a.count:
        for s in skipped:
            print('  skip', *s)
        return
    os.makedirs(os.path.join(a.out, 'control'), exist_ok=True)
    os.makedirs(os.path.join(a.out, 'boards'), exist_ok=True)
    Image.new('RGB', (512, 512), GREY).save(os.path.join(a.out, 'boards', '_blank.png'))
    for _, _, _, b, _ in items:
        if b is not None:
            shutil.copyfile(b, os.path.join(a.out, 'boards', os.path.basename(b)))
    jobs, meta = [], {}
    with Pool(a.workers) as pool:
        for k, (j, m) in enumerate(pool.imap_unordered(build_group, [(*it, a.out) for it in items])):
            jobs += j
            meta.update(m)
            if (k + 1) % 50 == 0:
                print('groups done', k + 1, '/', len(items), 'jobs', len(jobs), flush=True)
    jobs.sort(key=lambda j: j['name'])
    for tag in ('v4', 'v2'):
        sel = [{k: v for k, v in j.items() if k != 'lora'} for j in jobs if j['lora'] == tag]
        json.dump(sel, open(os.path.join(a.out, f'jobs_{tag}.json'), 'w'), indent=0)
        print(tag, 'jobs', len(sel))
    json.dump(meta, open(os.path.join(a.out, 'meta.json'), 'w'), indent=0)
    json.dump(skipped, open(os.path.join(a.out, 'skipped.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
