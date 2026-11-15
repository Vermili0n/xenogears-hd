"""Eyepatch: picked repaints -> composites -> (Bart hero sets) parts -> preview of the frames AS THE GAME WILL BUILD THEM.
Nothing is written to the pack here. Only parts that a repaint mask touches are candidates, so the jackets stay as they are.

  python patch_final.py compose
  python patch_final.py slice
  python patch_final.py preview <prefix>
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

XS = r'<XENO_SPRITES>'
T = os.path.join(XS, 'tools')
R1 = os.path.join(XS, 'ai', 'redraw', 'eyepatch')
R3 = os.path.join(XS, 'ai', 'redraw', 'eyepatch3')
F = os.path.join(R3, 'final')
BART = os.path.join(XS, 'ai', 'prod_work', 'h_bart_patch')
HD = os.path.join(XS, 'extracted', 'disc1_full', 'bart')
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
sys.path.insert(0, T)
from pack_heads import Hero, pack_frame  # noqa: E402
from patch_compose import offset_key  # noqa: E402
from patch_sheets import head_box as sheet_box  # noqa: E402

# seed, or 't<seed>' = the test round with its own mask
PICKS = {
    'c_bart_70a4dc__npc_033': 11, 'c_bart_9522cf__npc_011': 7, 'c_bart_c7ad1d__npc_024': 7,
    'c_sigurd_harcourt_172669__npc_008': 31, 'c_sigurd_harcourt_172669__npc_073': 11,
    'h_bart__2354_0_028': 23, 'h_bart__2354_0_032': 7, 'h_bart__2356_0_047': 7, 'h_bart__2356_0_048': 23,
    'h_bart__2356_0_059': 11, 'h_bart__2357_0_027': 11, 'h_bart__2357_0_028': 11, 'h_bart__2441_0_019': 7,
    'h_bart__430_0_064': 7, 'h_bart__430_0_065': 11, 'h_bart__430_0_073': 7, 'h_bart__430_0_105': 7,
    'h_bart__430_0_108': 11, 'h_bart__430_0_132': 't23', 'h_bart__430_0_133': 11, 'h_bart__430_0_135': 31,
    'h_bart__430_0_167': 't11', 'h_bart__430_0_169': 't7', 'h_bart__430_0_187': 't7', 'h_bart__430_0_188': 11,
    'h_bart__430_0_189': 7, 'h_bart__430_0_190': 7, 'h_bart__430_0_194': 7, 'h_bart__430_0_195': 23,
    'h_bart__430_0_196': 7, 'h_bart__430_0_203': 23, 'h_bart__430_0_215': 11,
}
META = json.load(open(os.path.join(XS, 'ai', 'prod', 'meta.json')))


def head_src(name, pick):
    if isinstance(pick, str):
        return os.path.join(R3, 'tests', f't3_{pick[1:]}', 'v4', name + '__head.png')
    return os.path.join(R3, f'res_{pick}', 'v4', name + '__head.png')


def mask_src(name, pick):
    return os.path.join(R3, 'mask', name + '__head' + ('.t3' if isinstance(pick, str) else '') + '.png')


def work_of(g):
    return os.path.join(BART, 'work') if g == 'h_bart' else os.path.join(F, g, 'work')


def compose():
    res = os.path.join(F, 'v4')
    os.makedirs(res, exist_ok=True)
    json.dump({'picks': PICKS}, open(os.path.join(R3, 'picks.json'), 'w'), indent=1)
    for n, p in PICKS.items():
        shutil.copyfile(os.path.join(R1, 'before', n + '.png'), os.path.join(res, n + '.png'))
        shutil.copyfile(head_src(n, p), os.path.join(res, n + '__head.png'))
    render = os.path.join(R3, 'comp', '_render')
    for g in sorted({META[n]['group'] for n in PICKS}):
        w = work_of(g)
        shutil.rmtree(w, ignore_errors=True)
        os.makedirs(w)
        r = subprocess.run([sys.executable, 'compose_set.py', '--render', render, '--res', res, '--work', w, '--name', g,
                            '--out-scale', '8', '--offset-key', offset_key(g)], cwd=T, capture_output=True, text=True)
        print(g, r.stdout.strip()[-100:], r.stderr.strip()[-300:] if r.returncode else '', flush=True)
        c = json.load(open(os.path.join(os.path.dirname(w), 'compose.json')))
        print('  not passed:', {k: v for k, v in c.items() if v.get('head') != 'pass'})


def slice_parts():
    frames = [n for n in PICKS if META[n]['group'] == 'h_bart']
    only = ','.join(f"{META[n]['set']}:{META[n]['frame']}" for n in frames)
    shutil.rmtree(os.path.join(BART, 'parts'), ignore_errors=True)
    r = subprocess.run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', 'prod_work/h_bart_patch', '--hero-dir', HD, '--scale', '8',
                        '--exact-mask', '--ring', '0', '--uv-compensate', '--only', only], cwd=T, capture_output=True, text=True)
    print(r.stdout.strip()[-300:], r.stderr.strip()[-300:] if r.returncode else '')
    print(len(os.listdir(os.path.join(BART, 'parts'))), 'parts')


def touched(h, name):
    """Names of the parts of a frame that its repaint mask touches."""
    m = META[name]
    places = h.placements(m['set'], m['frame'])
    _, (x0, y0) = h.assemble(places)
    hx, hy = m['head']
    mask = np.asarray(Image.open(mask_src(name, PICKS[name])).convert('L').resize((32, 32), Image.BOX)) > 40
    out = {}
    for p in places:
        im = h.part(p['block'], p['pal'])
        if p['flipx']:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flipy']:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        a = np.asarray(im)[..., 3] > 0
        n = 0
        for py, px in zip(*np.nonzero(a)):
            u, v = p['x'] - x0 + px - hx, p['y'] - y0 + py - hy
            if 0 <= u < 32 and 0 <= v < 32 and mask[v, u]:
                n += 1
        if n:
            out[f"{p['block']}-{p['pal']}"] = n
    return out


def preview(prefix):
    h = Hero(HD)
    frames = [n for n in PICKS if META[n]['group'] == 'h_bart']
    names = {}
    for n in frames:
        for part, c in touched(h, n).items():
            names.setdefault(part, []).append(n)
    parts_dir = os.path.join(BART, 'parts')
    use = {}
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            for p in pl:
                nm = f"{p['block']}-{p['pal']}"
                if nm in names:
                    use.setdefault(nm, set()).add((s, fi))
    k = 8
    cache_new = {}
    missing = []
    for nm in names:
        f = os.path.join(parts_dir, nm + '.png')
        if not os.path.exists(f):
            missing.append(nm)
            continue
        im = np.asarray(Image.open(f).convert('RGBA')).copy()
        im[..., 3] = np.where(im[..., 3] > 0, 255, 0)
        nw, nh = h.part(*nm.split('-')).size
        cache_new[nm] = (Image.fromarray(im, 'RGBA').resize((nw * k, nh * k), Image.LANCZOS), True)
    picked = {(META[n]['set'], META[n]['frame']) for n in frames}
    others = sorted({f for v in use.values() for f in v} - picked)
    json.dump({'parts': sorted(cache_new), 'missing': missing, 'others': others}, open(os.path.join(BART, 'selected.json'), 'w'), indent=1)
    print(len(cache_new), 'parts touched,', len(missing), 'not sliced,', len(others), 'other frames share them')
    cache_now = {}

    def cell(s, fi, lab):
        old, _ = h.assemble(h.placements(s, fi))
        y0, y1 = sheet_box(old, 0.34)
        now, _ = pack_frame(h, s, fi, k, cache_now)
        new, _ = pack_frame(h, s, fi, k, dict(cache_new))
        o = old.crop((0, y0, old.width, y1)).resize((old.width * k, (y1 - y0) * k), Image.NEAREST)
        return lab, [o, now.crop((0, y0 * k, now.width, y1 * k)), new.crop((0, y0 * k, new.width, y1 * k))]

    def sheet(cells, out):
        W, Hmax = 1980, 1500
        pages, page, x, y, rh = [], [], 8, 8, 0
        for lab, ims in cells:
            w, h_ = sum(i.width + 3 for i in ims) + 12, ims[0].height + 16
            if x + w > W and page:
                x, y, rh = 8, y + rh + 4, 0
            if y + h_ > Hmax and page:
                pages.append(page)
                page, x, y, rh = [], 8, 8, 0
            page.append((x, y, lab, ims))
            x += w
            rh = max(rh, h_)
        if page:
            pages.append(page)
        for pi, pg in enumerate(pages):
            H = max(c[1] + c[3][0].height + 20 for c in pg)
            s = Image.new('RGB', (W, H), (150, 170, 90))
            d = ImageDraw.Draw(s)
            for x, y, lab, ims in pg:
                d.text((x, y), lab, fill=(255, 255, 0))
                xx = x
                for i in ims:
                    s.paste(i, (xx, y + 13), i)
                    xx += i.width + 3
            p = f'{out}_{pi + 1}.png'
            s.save(p)
            print(p, s.size, len(pg))
    sheet([cell(META[n]['set'], META[n]['frame'], f"{META[n]['set']}:{META[n]['frame']}") for n in frames], prefix + '_fix')
    if others:
        sheet([cell(s, fi, f'{s}:{fi}') for s, fi in others], prefix + '_shared')


if __name__ == '__main__':
    if sys.argv[1] == 'compose':
        compose()
    elif sys.argv[1] == 'slice':
        slice_parts()
    else:
        preview(sys.argv[2])
