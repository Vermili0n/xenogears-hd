"""Masked repaint on the pod: FLUX.2 klein + LoRA redraw ONLY the masked area of an existing render, the rest stays pixel
for pixel. Control sprite + board are the same two condition images as in production.

  python repaint_pod.py --jobs jobs.json --out res_7 --seed 7 --lora lora/xeno_klein_v4.safetensors [--neg "..."] [--strength 1.0]
jobs.json: [{"name", "control", "ref", "prompt", "base", "mask"[, "neg", "strength"]}] (paths relative to the jobs file);
mask: white = redraw. base may carry a rough drawing inside the mask: with strength < 1 the model starts from it instead of pure
noise, so it refines the drawing and cannot move it. After every step the area outside the mask is reset to the base image noised
to the current level, so the new drawing is blended with what stays; the final image takes the outside pixels from the base itself.
Writes <out>/v4/<name>.png (512 canvas, like infer_pod.py). Resumable.
"""
import argparse
import json
import os
import time

import numpy as np
import torch
from diffusers import Flux2KleinPipeline
from diffusers.pipelines.flux2.pipeline_flux2_klein import compute_empirical_mu
from diffusers.utils.torch_utils import randn_tensor
from PIL import Image, ImageFilter

from infer_pod import crop_box

TOKEN = 16  # px per latent token: VAE 8x + patchify 2x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--lora', required=True)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--steps', type=int, default=28)
    ap.add_argument('--cfg', type=float, default=4.0)
    ap.add_argument('--neg', default='')
    ap.add_argument('--strength', type=float, default=1.0)
    ap.add_argument('--feather', type=float, default=5.0, help='blur of the final pixel mask, px')
    ap.add_argument('--model', default='black-forest-labs/FLUX.2-klein-base-4B')
    a = ap.parse_args()
    base_dir = os.path.dirname(os.path.abspath(a.jobs))
    jobs = json.load(open(a.jobs))
    out = f'{a.out}/v4'
    os.makedirs(out, exist_ok=True)
    pipe = Flux2KleinPipeline.from_pretrained(a.model, torch_dtype=torch.bfloat16).to('cuda')
    pipe.load_lora_weights(a.lora, adapter_name='xeno')
    pipe.set_adapters(['xeno'], adapter_weights=[1.0])
    negs = {}

    def neg_embeds(text):
        if not text:
            return None
        if text not in negs:
            with torch.no_grad():
                negs[text], _ = pipe.encode_prompt(prompt=text, device='cuda', num_images_per_prompt=1, max_sequence_length=512,
                                                   text_encoder_out_layers=(9, 18, 27))
        return negs[text]

    todo = [j for j in jobs if not os.path.exists(f"{out}/{j['name']}.png")]
    print('jobs', len(jobs), 'todo', len(todo), flush=True)
    t0 = time.time()
    for k, j in enumerate(todo):
        ctrl = Image.open(os.path.join(base_dir, j['control'])).convert('RGB')
        box = crop_box(ctrl)
        w, h = box[2] - box[0], box[3] - box[1]
        canvas = Image.open(os.path.join(base_dir, j['base'])).convert('RGB')
        base = canvas.crop(box)
        mask = Image.open(os.path.join(base_dir, j['mask'])).convert('L').crop(box)
        g = torch.Generator('cuda').manual_seed(a.seed)
        with torch.no_grad():
            t = pipe.image_processor.preprocess(base, height=h, width=w).to('cuda', pipe.vae.dtype)
            z0 = pipe._encode_vae_image(t, generator=g).to(torch.bfloat16)
        noise = randn_tensor(z0.shape, generator=g, device=z0.device, dtype=z0.dtype)
        m = np.asarray(mask.resize((w // TOKEN, h // TOKEN), Image.BOX), dtype=np.float32) / 255
        mt = torch.from_numpy((m > 0.1).astype(np.float32)).to(z0.device, z0.dtype)[None, None]
        z0p, noisep, mp = pipe._pack_latents(z0), pipe._pack_latents(noise), pipe._pack_latents(mt)
        # start point: pure noise (strength 1) or the base noised to the level of the first step kept
        strength = float(j.get('strength', a.strength))
        n = max(1, int(round(a.steps * strength)))
        sig = np.linspace(1.0, 1 / a.steps, a.steps)[a.steps - n:].tolist()
        mu = compute_empirical_mu(image_seq_len=z0p.shape[1], num_steps=n)
        pipe.scheduler.set_timesteps(sigmas=sig, device='cuda', mu=mu)
        s0 = pipe.scheduler.sigmas[0].to(z0.device, z0.dtype)
        start = (1 - s0) * z0 + s0 * noise

        def keep_outside(p, i, _t, kw):
            s = p.scheduler.sigmas[i + 1].to(z0p.device, z0p.dtype)
            return {'latents': mp * kw['latents'] + (1 - mp) * ((1 - s) * z0p + s * noisep)}

        im = pipe(prompt=j['prompt'], image=[ctrl.crop(box), Image.open(os.path.join(base_dir, j['ref'])).convert('RGB')],
                  height=h, width=w, num_inference_steps=n, sigmas=sig, guidance_scale=a.cfg, generator=g, latents=start,
                  negative_prompt_embeds=neg_embeds(j.get('neg', a.neg)), callback_on_step_end=keep_outside,
                  callback_on_step_end_tensor_inputs=['latents']).images[0]
        soft = mask.filter(ImageFilter.GaussianBlur(a.feather))
        canvas.paste(Image.composite(im, base, soft), box[:2])
        canvas.save(f"{out}/{j['name']}.png")
        if (k + 1) % 10 == 0 or k + 1 == len(todo):
            dt = (time.time() - t0) / (k + 1)
            print(f'{k + 1}/{len(todo)} {dt:.1f}s/img eta {dt * (len(todo) - k - 1) / 60:.1f} min', flush=True)


if __name__ == '__main__':
    main()
