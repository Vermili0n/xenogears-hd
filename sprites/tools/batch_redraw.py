"""Resumable batch AI redraw of hero sprites (portable: all paths relative to the xeno_sprites folder).

  python batch_redraw.py gen   --heroes fei,elly [--field-only] [--limit N]
  python batch_redraw.py slice --heroes fei,elly

gen  : for every plan row (plans/<hero>.csv) without ai/<hero>/work/<set>_<frame>_red.png, assemble the
       frame, build the smooth base and run stable-diffusion.cpp; the cropped redraw is saved as *_red.png.
slice: cut all finished redraws into 4x parts -> ai/<hero>/parts/<texhash>-<palhash>.png (ready for the pack).
"""
import argparse
import csv
import json
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import BG, OPAQUE, SCALE, Hero, erode, sd_redraw, xbr4  # noqa: E402


PROFILES = {
    # model, controlnet, ip-adapter, clip-skip, prompt keys
    'sd15': ('Counterfeit-V3.0_fix_fp16.safetensors', 'control_v11f1e_sd15_tile_fp16.safetensors',
             'ip-adapter-plus_sd15.safetensors', 2, ('prefix', 'prompt', 'negative')),
    'sdxl': ('animagine-xl-4.0-opt.safetensors', 'controlnet_tile_sdxl_xinsir.safetensors',
             'ip-adapter-plus_sdxl_vit-h.safetensors', 1, ('prefix_xl', 'prompt_xl', 'negative_xl')),
}


def settings(hero, cfg, a):
    common = cfg['_common']
    h = cfg[hero]
    model, cnet, ipa, clip_skip, (kpre, kprompt, kneg) = PROFILES[a.profile]
    model = a.model or os.path.join(HERE, 'models', model)
    cnet = None if a.no_controlnet else (a.controlnet or os.path.join(HERE, 'models', cnet))
    ipa = a.ip_model or os.path.join(HERE, 'models', ipa)
    ref = os.path.join(ROOT, 'ai', 'refs', h['portrait']) if h.get('portrait') else ''
    use_ip = bool(ref) and os.path.exists(ref) and a.ip_strength > 0 and os.path.exists(ipa)
    sd = a.sd or os.path.join(HERE, 'sdcpp', 'sd-cli.exe')
    prompt = common[kpre] + h.get(kprompt, h['prompt'])
    extra = a.extra
    if a.lora:  # name:weight, file <lora-dir>/<name>.safetensors
        prompt = f'<lora:{a.lora}>, ' + prompt
        extra = (extra + ' --lora-model-dir ' + (a.lora_dir or os.path.join(ROOT, 'lora', hero))).strip()
    return SimpleNamespace(
        sd=sd, model=model, controlnet=cnet if cnet and os.path.exists(cnet) else None,
        control_strength=a.control_strength,
        prompt=prompt, negative=common[kneg],
        strength=a.strength, cfg=a.cfg, steps=a.steps, sampler=a.sampler, scheduler=a.scheduler, seed=a.seed,
        clip_skip=a.clip_skip or clip_skip,
        ip_adapter=ipa if use_ip else None, ip_adapter_path=ipa if os.path.exists(ipa) else None,
        clip_vision=os.path.join(HERE, 'models', 'clip_vision_vit_h.safetensors'),
        ip_image=ref if use_ip else None, ip_strength=a.ip_strength, extra=extra, verbose=a.verbose)


def read_plan(hero, field_only):
    with open(os.path.join(ROOT, 'plans', f'{hero}.csv')) as f:
        rows = [(r['set'], int(r['frame']), int(r['priority'])) for r in csv.DictReader(f)]
    return [(s, fi) for s, fi, p in rows if not field_only or p == 0]


def base_for(hero_obj, setkey, fi, gen):
    places = hero_obj.placements(setkey, fi)
    frame, origin = hero_obj.assemble(places)
    c4, m4 = xbr4(frame)
    base = np.asarray(Image.fromarray(c4).resize((c4.shape[1] * gen, c4.shape[0] * gen), Image.LANCZOS))
    mask = np.asarray(Image.fromarray((m4 * 255).astype(np.uint8)).resize(
        (m4.shape[1] * gen, m4.shape[0] * gen), Image.LANCZOS)) > 127
    return places, origin, c4, m4, base, mask


def cmd_gen(a, cfg):
    for hero in a.heroes.split(','):
        st = settings(hero, cfg, a)
        hobj = Hero(a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', hero))
        work = os.path.join(ROOT, 'ai', hero + a.out_tag, 'work')
        os.makedirs(work, exist_ok=True)
        plan = read_plan(hero, a.field_only)
        refs = {}
        if a.only:
            plan = []
            for t in a.only.split(','):
                t, _, ref = t.partition('@')
                s, fi = t.split(':')
                plan.append((s, int(fi)))
                if ref:
                    refs[(s, int(fi))] = os.path.join(ROOT, 'ai', 'refs', ref + '.png')
        todo = [(s, fi) for s, fi in plan if not os.path.exists(os.path.join(work, f'{s}_{fi:03d}_red.png'))]
        if a.limit:
            todo = todo[:a.limit]
        print(f'[{hero}] plan {len(plan)} frames, to do {len(todo)}', flush=True)
        t0 = time.time()
        for k, (s, fi) in enumerate(todo, 1):
            tag = f'{s}_{fi:03d}'
            places, _, c4, m4, base, mask = base_for(hobj, s, fi, a.gen)
            if (s, fi) in refs and os.path.exists(refs[(s, fi)]):
                st.ip_image = refs[(s, fi)]
                st.ip_adapter = st.ip_adapter or st.ip_adapter_path
            red = sd_redraw(base, mask, st, work, tag)
            Image.fromarray(red, 'RGB').save(os.path.join(work, f'{tag}_red.png'))
            for junk in (f'{tag}_init.png', f'{tag}_out.png'):
                p = os.path.join(work, junk)
                if os.path.exists(p) and not a.keep:
                    os.remove(p)
            el = time.time() - t0
            eta = el / k * (len(todo) - k)
            print(f'[{hero}] {k}/{len(todo)} {tag}  {el / k:.0f}s/frame  ETA {eta / 3600:.1f}h', flush=True)


def xbr_at(img, scale):
    """xBR 4x (colour + mask), brought to `scale` (8 = 4x xBR then 2x Lanczos / nearest mask)."""
    c4, m4 = xbr4(img)
    if scale == 4:
        return c4, m4
    k = scale // 4
    c = np.asarray(Image.fromarray(c4).resize((c4.shape[1] * k, c4.shape[0] * k), Image.LANCZOS))
    return c, np.kron(m4, np.ones((k, k), bool))


def cmd_slice(a, cfg):
    SCALE = a.scale  # noqa: N806  (replacement scale of the written parts)
    for hero in a.heroes.split(','):
        hdir = a.hero_dir or os.path.join(ROOT, 'extracted', 'disc1_full', hero)
        hobj = Hero(hdir)
        work = os.path.join(ROOT, 'ai', hero + a.out_tag, 'work')
        out = os.path.join(ROOT, 'ai', hero + a.out_tag, 'parts')
        prev = os.path.join(ROOT, 'ai', hero + a.out_tag, 'frames')
        os.makedirs(out, exist_ok=True)
        os.makedirs(prev, exist_ok=True)
        best, xc = {}, {}
        low = {(t.split(':')[0], int(t.split(':')[1])) for t in a.low_priority.split(',') if t}
        mid = {(t.split(':')[0], int(t.split(':')[1])) for t in a.mid_priority.split(',') if t}
        forced = {k: (v.split(':')[0], int(v.split(':')[1])) for k, v in json.load(open(a.owners)).items()} if a.owners else {}
        cand = [(t.split('@')[0].split(':')[0], int(t.split('@')[0].split(':')[1])) for t in a.only.split(',')] if a.only else read_plan(hero, False)
        done = [(s, fi) for s, fi in cand if os.path.exists(os.path.join(work, f'{s}_{fi:03d}_red.png'))]
        for s, fi in done:
            tag = f'{s}_{fi:03d}'
            places = hobj.placements(s, fi)
            frame, (x0, y0) = hobj.assemble(places)
            c4, m4 = xbr_at(frame, SCALE)
            m4_smooth = m4  # xBR-rounded outer silhouette of the whole frame
            if a.exact_mask:  # texel-exact silhouette: parts butt against each other like in the original, no gaps
                m4 = np.kron(np.asarray(frame)[..., 3] > 0, np.ones((SCALE, SCALE), bool))
            red = Image.open(os.path.join(work, f'{tag}_red.png')).convert('RGB')
            red4 = np.asarray(red.resize((c4.shape[1], c4.shape[0]), Image.LANCZOS)).copy()
            if a.ring:
                ring = m4 & ~erode(m4, a.ring)
                red4[ring] = c4[ring]
            Image.fromarray(np.dstack([red4, np.where(m4, 255, 0).astype(np.uint8)]), 'RGBA').save(
                os.path.join(prev, f'{tag}.png'))
            H4, W4 = m4.shape
            owner = np.full((H4, W4), -1, np.int32)
            pm = []
            for k, p in enumerate(places):
                key = (p['block'], p['pal'])
                if key not in xc:
                    pimg = hobj.part(p['block'], p['pal'])
                    pc, pmx = xbr_at(pimg, SCALE)
                    if a.exact_mask:
                        pmx = np.kron(np.asarray(pimg)[..., 3] > 0, np.ones((SCALE, SCALE), bool))
                    xc[key] = (pc, pmx)
                pc4, pm4 = xc[key]
                if p['flipx']:
                    pc4, pm4 = pc4[:, ::-1], pm4[:, ::-1]
                if p['flipy']:
                    pc4, pm4 = pc4[::-1], pm4[::-1]
                X, Y = (p['x'] - x0) * SCALE, (p['y'] - y0) * SCALE
                h, w = pm4.shape
                owner[Y:Y + h, X:X + w][pm4] = k
                pm.append((pc4, pm4, X, Y))
            for k, p in enumerate(places):
                pc4, pm4, X, Y = pm[k]
                h, w = pm4.shape
                vis = (owner[Y:Y + h, X:X + w] == k) & pm4
                col = pc4.copy()
                if vis.any():
                    col[vis] = red4[Y:Y + h, X:X + w][vis]
                mask = pm4
                if a.exact_mask:  # exact (flush) where the part meets other parts, smooth along the figure's outline
                    mask = pm4 & m4_smooth[Y:Y + h, X:X + w]
                if p['flipx']:
                    col, mask, vis = col[:, ::-1], mask[:, ::-1], vis[:, ::-1]
                if p['flipy']:
                    col, mask, vis = col[::-1], mask[::-1], vis[::-1]
                share = vis.sum() / max(1, mask.sum())
                if (s, fi) in low:  # fallback frames (e.g. ebsynth fills) lose every tie against model redraws
                    share *= 0.01
                elif (s, fi) in mid:  # local-model redraws: beat ebsynth fills, lose to keyframes
                    share *= 0.1
                name = f"{p['block']}-{p['pal']}"
                if forced.get(name) == (s, fi):  # owner chosen by part_owners.py (fewer seams)
                    share = 2.0
                if name not in best or share > best[name][0]:
                    best[name] = (share, np.dstack([col, np.where(mask, OPAQUE, 0).astype(np.uint8)]))
        # every palette variant of a block gets the redraw only for the palette it was drawn with;
        # other palettes of the same block (battle effects) keep their pack/xBR versions.
        for name, (share, img) in best.items():
            if a.uv_compensate:
                img = uv_compensate(img, SCALE)
            Image.fromarray(np.ascontiguousarray(img), 'RGBA').save(os.path.join(out, name + '.png'))
        print(f'[{hero}] sliced {len(done)} frames -> {len(best)} parts', flush=True)


def uv_compensate(img, scale):
    """Xenogears draws every sprite part as a polygon of the part's true size whose UVs span only size-1 texels
    (u0..u0+w-1), so the game stretches the texture by w/(w-1) (h/(h-1)) inside the part. Pre-squeeze the HD
    image into its first (w-1) x (h-1) texels so that after the game's stretch it lands exactly on the layout;
    the last texel column/row (barely sampled) repeats the edge."""
    H, W = img.shape[:2]
    w, h = W // scale, H // scale
    tw, th = (w - 1) * scale if w > 1 else W, (h - 1) * scale if h > 1 else H
    if (tw, th) == (W, H):
        return img
    rgb = np.asarray(Image.fromarray(np.ascontiguousarray(img[..., :3])).resize((tw, th), Image.LANCZOS))
    al = np.asarray(Image.fromarray(np.ascontiguousarray(img[..., 3])).resize((tw, th), Image.NEAREST))
    out = np.zeros_like(img)
    out[:th, :tw, :3] = rgb
    out[:th, :tw, 3] = al
    out[th:, :tw] = out[th - 1:th, :tw]
    out[:, tw:] = out[:, tw - 1:tw]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['gen', 'slice'])
    ap.add_argument('--heroes', default='fei')
    ap.add_argument('--hero-dir', default='', help='sprite folder for a single hero/NPC (default extracted/disc1_full/<hero>)')
    ap.add_argument('--field-only', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--sd', help='path to sd-cli.exe (default tools/sdcpp/sd-cli.exe)')
    ap.add_argument('--profile', choices=list(PROFILES), default='sd15')
    ap.add_argument('--model', help='override checkpoint path')
    ap.add_argument('--controlnet', help='override ControlNet path')
    ap.add_argument('--no-controlnet', action='store_true')
    ap.add_argument('--ip-model', help='override IP-Adapter path')
    ap.add_argument('--clip-skip', type=int, default=0)
    ap.add_argument('--sampler', default='dpm++2m')
    ap.add_argument('--scheduler', default='karras')
    ap.add_argument('--out-tag', default='', help='suffix for ai/<hero><tag> output folder (A/B tests)')
    ap.add_argument('--only', default='', help='explicit frames instead of the plan: 427_0:190,427_0:51')
    ap.add_argument('--gen', type=int, default=4, help='generation scale over 4x (4 -> 16x)')
    ap.add_argument('--strength', type=float, default=0.42)
    ap.add_argument('--control-strength', type=float, default=0.8)
    ap.add_argument('--ip-strength', type=float, default=0.35)
    ap.add_argument('--cfg', type=float, default=6.0)
    ap.add_argument('--steps', type=int, default=24)
    ap.add_argument('--seed', type=int, default=1234)
    ap.add_argument('--ring', type=int, default=2)
    ap.add_argument('--scale', type=int, default=SCALE, choices=[4, 8], help='replacement scale of the written parts')
    ap.add_argument('--uv-compensate', action='store_true', help='pre-squeeze parts for the game (size-1) UV span')
    ap.add_argument('--exact-mask', action='store_true', help='texel-exact part masks (no xBR rounding): no gaps between parts')
    ap.add_argument('--extra', default='')
    ap.add_argument('--low-priority', default='', help='set:frame list used for parts only when no other frame has them')
    ap.add_argument('--mid-priority', default='', help='set:frame list between keyframes and --low-priority frames')
    ap.add_argument('--owners', default='', help='json {part: set:frame} from part_owners.py')
    ap.add_argument('--lora', default='', help='character LoRA as name:weight, e.g. fei_lora:0.7')
    ap.add_argument('--lora-dir', default='', help='folder with <name>.safetensors (default lora/<hero>)')
    ap.add_argument('--fit', choices=['auto', 'gpu'], default='auto', help='gpu: weights on the GPU, text encoders on CPU, flash attention')
    ap.add_argument('--device', default='CUDA0')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    if a.fit == 'gpu':
        d = a.device
        a.extra = (a.extra + f' --params-backend diffusion={d},controlnet={d},vae={d},te=cpu --diffusion-fa').strip()
    with open(os.path.join(HERE, 'heroes.json'), encoding='utf-8') as f:
        cfg = json.load(f)
    (cmd_gen if a.cmd == 'gen' else cmd_slice)(a, cfg)


if __name__ == '__main__':
    main()
