"""Second build of the eyepatch fix: the frames re-done from sketches (eyepatch4) + blue irises + the chin stripe of the head part
b66110c6 (flat seam fill in its last rows: real pixels from a composite of the same head). Nothing is written to the pack here.

  python patch_final2.py compose
  python patch_final2.py slice
  python patch_final2.py preview <prefix>
"""
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
import patch_final as pf  # noqa: E402
from patch_compose import offset_key  # noqa: E402
from pack_heads import Hero, pack_frame  # noqa: E402
from patch_sheets import head_box as sheet_box  # noqa: E402

XS = pf.XS
R4 = os.path.join(XS, 'ai', 'redraw', 'eyepatch4')
T = pf.T
# frame -> test folder of eyepatch4
R2 = {'c_bart_70a4dc__npc_033': 'r3_11_55', 'h_bart__2354_0_024': 'r3_7_55', 'h_bart__2354_0_025': 'r3_11_55',
      'h_bart__2354_0_026': 'r3_11_55', 'h_bart__2354_0_027': 'r3_7_55', 'h_bart__2354_0_028': 'r3_7_68',
      'h_bart__2356_0_047': 'r3_11_55', 'h_bart__2356_0_048': 'r3_11_68', 'h_bart__430_0_065': 'r3_11_55',
      'h_bart__430_0_108': 'r2_7_62', 'h_bart__430_0_188': 'r2_11_62', 'h_bart__430_0_196': 'r3_7_68',
      'h_bart__430_0_203': 'r2_7_50', 'h_bart__430_0_215': 'r2_7_50'}
# irises to make blue: frame -> (x, y, rx, ry) on the head close-up
IRIS = {'h_bart__430_0_108': (285, 215, 11, 12), 'h_bart__430_0_188': (271, 211, 11, 12), 'h_bart__430_0_203': (261, 210, 12, 15),
        'h_bart__430_0_215': (166, 222, 7, 13)}
HEAD_PART = 'b66110c6-84f5630b'
HEAD_ROWS = 18    # parts starting above this frame row can show on the head
RES =os.path.join(XS, 'pod', 'report', 'prod', 'res_prod', 'v4')
# frames added after the first sheet: only in eyepatch4
for _n in ('h_bart__2354_0_024', 'h_bart__2354_0_025', 'h_bart__2354_0_026', 'h_bart__2354_0_027'):
    pf.PICKS[_n] = 0


def blue_iris(a, c):
    """Iris inside an ellipse: luminance -> blue ramp, the pupil stays dark, highlights stay."""
    x, y, rx, ry = c
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    d = np.sqrt(((xx - x) / rx) ** 2 + ((yy - y) / ry) ** 2)
    k = np.clip((1.05 - d) / 0.2, 0, 1)[..., None]
    rgb = a[..., :3].astype(float)
    lum = rgb @ np.array([0.3, 0.59, 0.11])
    grad = np.clip(((yy - y) / ry + 1) / 2, 0, 1)
    t = np.clip(lum / 150 * 0.6 + grad * 0.55, 0, 1)
    t[d < 0.42] *= 0.2
    lo, mid, hi = np.array([16, 26, 66.0]), np.array([38, 88, 188.0]), np.array([105, 165, 235.0])
    col = np.where(t[..., None] < 0.5, lo + (mid - lo) * (t[..., None] * 2), mid + (hi - mid) * (t[..., None] * 2 - 1))
    keep = (lum > 190)[..., None]
    col = np.where(keep, rgb, col)
    out = a.copy().astype(float)
    out[..., :3] = rgb * (1 - k) + col * k
    return out.round().astype(np.uint8)


def tone_blue(a, mask):
    """The LoRA's blue is too vivid next to the rest of the drawing (and goes violet): calmer, same lightness. Only inside the repaint."""
    rgb = a.astype(float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    vivid = (b > 1.3 * np.maximum(r, g)) & (b > 60) & (cv2.dilate(mask, np.ones((25, 25), np.uint8)) > 0)
    lum = rgb @ np.array([0.3, 0.59, 0.11])
    calm = np.clip(lum[..., None] * np.array([0.62, 0.95, 1.5]), 0, 255)
    k = cv2.GaussianBlur(vivid.astype(np.float32), (0, 0), 1.0)[..., None] * 0.6
    return (rgb * (1 - k) + calm * k).round().astype(np.uint8)


def compose():
    res = os.path.join(pf.F, 'v4')
    os.makedirs(res, exist_ok=True)
    picks = dict(pf.PICKS)
    json.dump({'picks': picks, 'round2': R2, 'iris': IRIS}, open(os.path.join(pf.R3, 'picks.json'), 'w'), indent=1)
    for n, p in picks.items():
        shutil.copyfile(os.path.join(RES, n + '.png'), os.path.join(res, n + '.png'))
        src = os.path.join(R4, 'tests', R2[n], 'v4', n + '__head.png') if n in R2 else pf.head_src(n, p)
        im = np.asarray(Image.open(src).convert('RGB'))
        if n in IRIS:
            im = blue_iris(im, IRIS[n])
        im = tone_blue(im, np.asarray(Image.open(mask_of(n)).convert('L')))
        Image.fromarray(im).save(os.path.join(res, n + '__head.png'))
    render = os.path.join(pf.R3, 'comp', '_render')
    os.makedirs(render, exist_ok=True)
    json.dump({n: pf.META[n] for n in picks}, open(os.path.join(render, 'meta.json'), 'w'))
    for g in sorted({pf.META[n]['group'] for n in picks}):
        w = pf.work_of(g)
        shutil.rmtree(w, ignore_errors=True)
        os.makedirs(w)
        r = subprocess.run([sys.executable, 'compose_set.py', '--render', render, '--res', res, '--work', w, '--name', g,
                            '--out-scale', '8', '--offset-key', offset_key(g)], cwd=T, capture_output=True, text=True)
        print(g, r.stdout.strip()[-80:], r.stderr.strip()[-300:] if r.returncode else '', flush=True)
        c = json.load(open(os.path.join(os.path.dirname(w), 'compose.json')))
        print('  not passed:', {k: v for k, v in c.items() if v.get('head') != 'pass'})


def fix_stripe():
    """Last rows of the shared head part were a flat seam fill: real pixels of frame 132 (same head, x=3) from row 10 down."""
    p = os.path.join(pf.BART, 'parts', HEAD_PART + '.png')
    part = np.array(Image.open(p).convert('RGBA'))
    red = np.asarray(Image.open(os.path.join(pf.BART, 'work', '430_0_132_red.png')).convert('RGB'))
    S = 8
    x, y = 3 * S + 3, 2    # best match of the part on this composite (stripe_align.py): the slicer's uv compensation
    r0 = 10 * S
    H, W = part.shape[:2]
    sub = red[r0 + y:H + y, x:x + W]
    h_, w_ = sub.shape[:2]
    op = part[r0:r0 + h_, :w_, 3] > 0
    d = part[r0:r0 + h_, :w_, :3]
    before = np.abs(d.astype(int) - sub.astype(int)).mean(axis=-1)[op].mean()
    d[op] = sub[op]
    Image.fromarray(part).save(p)
    print('head part: replaced rows >=10, mean change', round(float(before), 1), 'texel check above the cut:',
          round(float(np.abs(part[8 * S:r0, :w_, :3].astype(int) - red[8 * S + y:r0 + y, x:x + w_].astype(int)).mean()), 1))


def slice_parts():
    pf.slice_parts()


MASK_ROUND1 = pf.mask_src


def mask_of(n):
    if n in R2:
        return os.path.join(R4, 'mask', n + '__head.png')
    return MASK_ROUND1(n, pf.PICKS[n])


def preview(prefix):
    h = Hero(pf.HD)
    pf.mask_src = lambda name, pick: mask_of(name)  # touched() reads the masks through this
    frames = [n for n in pf.PICKS if pf.META[n]['group'] == 'h_bart']
    names = {}
    for n in frames:
        for part in pf.touched(h, n):
            names.setdefault(part, []).append(n)
    names.setdefault(HEAD_PART, [])
    # upper parts have windows (transparent texels): the part under them shows through. Left as it is in the pack, such a part made the
    # "keyhole" and the rectangles around the eye -> the frame's own slice for every part visible on the head, unless a frame outside
    # the picks also uses it (those are listed and stay as they are)
    all_use = {}
    for s in h.layout:
        for fi in range(len(h.layout[s]['frames'])):
            try:
                pl = h.placements(s, fi)
            except Exception:  # noqa: BLE001
                continue
            for p in pl:
                all_use.setdefault(f"{p['block']}-{p['pal']}", set()).add((s, fi))
    fixed = set()
    for n in frames:
        m = pf.META[n]
        fixed.add((m['set'], m['frame']))
        for d in m['dups']:
            ds, df = d.split('__')[1].rsplit('_', 1)
            fixed.add((ds, int(df)))
    kept = {}
    for n in frames:
        m = pf.META[n]
        pl = h.placements(m['set'], m['frame'])
        x0, y0 = min(p['x'] for p in pl), min(p['y'] for p in pl)
        for p in pl:
            nm = f"{p['block']}-{p['pal']}"
            if p['y'] - y0 >= HEAD_ROWS or nm in names:
                continue
            outside = all_use.get(nm, set()) - fixed
            if outside:
                kept.setdefault(nm, sorted(outside)[:4])
            else:
                names[nm] = [n]
    print('head parts left as they are (other frames use them):', kept)
    k = 12
    new_cache, missing = {}, []
    for nm in names:
        f = os.path.join(pf.BART, 'parts', nm + '.png')
        if not os.path.exists(f):
            missing.append(nm)
            continue
        im = np.asarray(Image.open(f).convert('RGBA')).copy()
        im[..., 3] = np.where(im[..., 3] > 0, 255, 0)
        nw, nh = h.part(*nm.split('-')).size
        new_cache[nm] = (Image.fromarray(im, 'RGBA').resize((nw * k, nh * k), Image.LANCZOS), True)
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
    picked = {(pf.META[n]['set'], pf.META[n]['frame']) for n in frames}
    others = sorted({f for v in use.values() for f in v} - picked)
    json.dump({'parts': sorted(new_cache), 'missing': missing, 'others': [list(o) for o in others]},
              open(os.path.join(pf.BART, 'selected.json'), 'w'), indent=1)
    print(len(new_cache), 'parts,', len(missing), 'not sliced:', missing, '|', len(others), 'other frames share them:', others)
    now_cache = {}

    def cell(s, fi):
        old, _ = h.assemble(h.placements(s, fi))
        y0, y1 = sheet_box(old, 0.38)
        now, _ = pack_frame(h, s, fi, k, now_cache)
        new, _ = pack_frame(h, s, fi, k, new_cache)
        o = old.crop((0, y0, old.width, y1)).resize((old.width * k, (y1 - y0) * k), Image.NEAREST)
        return f'{s}:{fi}', [o, now.crop((0, y0 * k, now.width, y1 * k)), new.crop((0, y0 * k, new.width, y1 * k))]

    cells = [cell(pf.META[n]['set'], pf.META[n]['frame']) for n in frames] + [cell(s, fi) for s, fi in others]
    W, Hmax = 1990, 1500
    pages, page, x, y, rh = [], [], 6, 6, 0
    for lab, ims in cells:
        w, h_ = sum(i.width + 3 for i in ims) + 10, ims[0].height + 16
        if x + w > W and page:
            x, y, rh = 6, y + rh + 4, 0
        if y + h_ > Hmax and page:
            pages.append(page)
            page, x, y, rh = [], 6, 6, 0
        page.append((x, y, lab, ims))
        x += w
        rh = max(rh, h_)
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
        p = f'{prefix}_{pi + 1}.png'
        s.save(p)
        print(p, s.size, len(pg))


if __name__ == '__main__':
    if sys.argv[1] == 'compose':
        compose()
    elif sys.argv[1] == 'slice':
        slice_parts()
    else:
        preview(sys.argv[2])
