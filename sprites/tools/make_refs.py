"""Generate character reference candidates (front face, full-body front/side/back) from the dialogue portrait.

Uses stable-diffusion.cpp txt2img with an IP-Adapter on the HD portrait, several seeds per view.
Output: ai/refs_cand/<hero>/<view>_<seed>.png + a contact sheet ai/refs_cand/<hero>_<view>.png
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VIEWS = {
    'face':  ('portrait, upper body, looking at viewer, facing viewer, front view, straight-on, symmetrical face', 832, 1024),
    'front': ('full body, standing, front view, facing viewer, arms at sides, straight-on', 704, 1216),
    'side':  ('full body, standing, from side, profile, facing right', 704, 1216),
    'back':  ('full body, standing, from behind, back view, facing away', 704, 1216),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hero', default='fei')
    ap.add_argument('--views', default='face,front')
    ap.add_argument('--seeds', default='11,22,33,44')
    ap.add_argument('--model', default=os.path.join(HERE, 'models', 'animagine-xl-4.0-q8_0.gguf'))
    ap.add_argument('--ip-model', default=os.path.join(HERE, 'models', 'ip-adapter-plus_sdxl_vit-h.safetensors'))
    ap.add_argument('--ip-strength', type=float, default=0.5)
    ap.add_argument('--steps', type=int, default=28)
    ap.add_argument('--cfg', type=float, default=5.0)
    ap.add_argument('--extra', default='')
    ap.add_argument('--fit', choices=['auto', 'gpu'], default='gpu')
    ap.add_argument('--device', default='CUDA0')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, 'heroes.json'), encoding='utf-8'))
    common, h = cfg['_common'], cfg[a.hero]
    portrait = os.path.join(ROOT, 'ai', 'refs', h['portrait']) if h.get('portrait') else ''
    out = os.path.join(ROOT, 'ai', 'refs_cand', a.hero)
    os.makedirs(out, exist_ok=True)
    sd = os.path.join(HERE, 'sdcpp', 'sd-cli.exe')
    neg = common['negative_xl'] + ', multiple views, reference sheet, cropped, out of frame'
    extra = a.extra.split()
    if a.fit == 'gpu':
        extra += ['--params-backend', f'diffusion={a.device},vae={a.device},te=cpu', '--diffusion-fa']
    for view in a.views.split(','):
        vprompt, W, H = VIEWS[view]
        prompt = (f"masterpiece, high score, great score, absurdres, {h['prompt_xl']}, {vprompt}, "
                  "simple background, white background, anime screencap, 90s anime style")
        files = []
        for seed in a.seeds.split(','):
            dst = os.path.join(out, f'{view}_{seed}.png')
            if not os.path.exists(dst):
                cmd = [sd, '-M', 'img_gen', '-m', a.model, '-p', prompt, '-n', neg, '-W', str(W), '-H', str(H),
                       '--steps', str(a.steps), '--cfg-scale', str(a.cfg), '--sampling-method', 'euler_a',
                       '-s', seed, '-o', dst] + extra
                if portrait and os.path.exists(a.ip_model):
                    cmd += ['--ip-adapter', a.ip_model, '--clip_vision',
                            os.path.join(HERE, 'models', 'clip_vision_vit_h.safetensors'),
                            '--ip-adapter-image', portrait, '--ip-adapter-strength', str(a.ip_strength)]
                subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
            files.append(dst)
            print(f'{view} seed {seed} done', flush=True)
        ims = [Image.open(f).convert('RGB') for f in files]
        sheet = Image.new('RGB', (sum(i.width for i in ims) + 10 * len(ims), max(i.height for i in ims) + 30), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        x = 0
        for f, im in zip(files, ims):
            sheet.paste(im, (x, 30))
            d.text((x + 6, 8), os.path.basename(f), fill=(255, 230, 120))
            x += im.width + 10
        sheet.save(os.path.join(ROOT, 'ai', 'refs_cand', f'{a.hero}_{view}.png'))


if __name__ == '__main__':
    main()
