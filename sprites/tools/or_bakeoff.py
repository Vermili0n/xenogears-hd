"""Model bake-off through the OpenRouter Images API (run on a non-RU host). Key is read from stdin.

  cat key.txt | python3 or_bakeoff.py --dir xeno_or [--models a,b] [--grids walk_front,...] [--dry]

Inputs  <dir>/in/grid_<name>.png, ref_sheet.png, ref_face.png, ref_style.png
Outputs <dir>/out/<model-slug>__<grid>.png and <dir>/out/log.jsonl (one line per request: id, cost, error).
Resumable: existing outputs are skipped.
"""
import argparse
import base64
import concurrent.futures as cf
import json
import os
import sys
import threading
import time

import requests

API = 'https://openrouter.ai/api/v1/images'
MODELS = {  # model -> extra request params
    'qwen/qwen-image-2.1-pro': {'resolution': '1K', 'aspect_ratio': '1:1', 'seed': 1234},
    'qwen/qwen-image-2.1-turbo': {'resolution': '1K', 'aspect_ratio': '1:1', 'seed': 1234},
    'black-forest-labs/flux-3-image': {'resolution': '1K', 'aspect_ratio': '1:1'},
    'black-forest-labs/flux-3-image-klein': {'resolution': '1K', 'aspect_ratio': '1:1'},
    'google/gemini-nano-banana-2.1': {'resolution': '1K', 'aspect_ratio': '1:1'},
    'bytedance-seed/seedream-5-0-pro': {'resolution': '1K', 'aspect_ratio': '1:1', 'seed': 1234},
    'google/gemini-3-pro-image': {'resolution': '1K', 'aspect_ratio': '1:1'},
    'openai/gpt-image-2.5-sunburst': {'quality': 'high'},
}
PROMPT = (
    "Image 1 is a {grid} grid of {n} animation frames of a retro pixel-art game sprite of an original character, upscaled. "
    "Images 2-4 are references of the same character: image 2 is a turnaround sheet, image 3 is a face close-up, "
    "image 4 shows the exact rendering style wanted at sprite proportions.\n"
    "Task: redraw image 1 as clean high-resolution 90s anime illustrations of this character, in the style of image 4, "
    "with the face and outfit details of images 2 and 3. This is a precise trace-over: the result will be laid exactly "
    "over image 1, so matching its geometry matters more than anything else.\n"
    "Rules:\n"
    "1. Same canvas as image 1: the same {grid} grid and size. Each figure stays in its cell at exactly the same position "
    "and size: same top of the head, same feet line, same left and right extents.\n"
    "2. Exactly the same pose in every frame: legs, feet, arms, fists, head direction and ponytail as in image 1. "
    "Do not change the stance. Keep the compact sprite proportions.\n"
    "3. Same colors as image 1.\n"
    "4. Clean face with clearly visible eyes wherever the face is visible, strong likeness to image 3.\n"
    "5. Exactly {n} figures, one per cell, in the same order as image 1.\n"
    "6. The background of every cell is the same flat solid magenta #FF00FF: no gradients, no colored or textured "
    "backgrounds, no shadows, no floor, no text, no borders, no grid lines between the cells, no extra objects."
)
lock = threading.Lock()


def data_url(path):
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()


def one(key, d, model, grid, extra, dry, style='style', tag='', res=''):
    slug = model.replace('/', '_')
    out = os.path.join(d, 'out', f'{slug}__{grid}{tag}.png')
    if os.path.exists(out):
        return f'skip {slug} {grid}'
    refs = [os.path.join(d, 'in', f'grid_{grid}.png')] + [os.path.join(d, 'in', f'ref_{r}.png') for r in ('sheet', 'face', style)]
    meta = json.load(open(os.path.join(d, 'in', 'grids.json')))[grid]
    cols, rows = meta[0].get('cols', 2), meta[0].get('rows', 2)
    extra = dict(extra)
    if res and 'resolution' in extra:
        extra['resolution'] = res
    prompt = PROMPT.format(grid=f'{cols}x{rows}', n=len(meta))
    body = {'model': model, 'prompt': prompt,
            'input_references': [{'type': 'image_url', 'image_url': {'url': data_url(p)}} for p in refs], **extra}
    if dry:
        return f'dry {slug} {grid} {len(json.dumps(body)) // 1024} KB'
    t0 = time.time()
    rec = {'model': model, 'grid': grid}
    try:
        r = requests.post(API, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                          json=body, timeout=600)
        rec['status'] = r.status_code
        j = r.json() if r.headers.get('content-type', '').startswith('application/json') else {'raw': r.text[:500]}
        rec['id'] = j.get('id')
        rec['usage'] = j.get('usage')
        if r.ok and j.get('data'):
            img = base64.b64decode(j['data'][0]['b64_json'])
            with open(out, 'wb') as f:
                f.write(img)
            rec['bytes'] = len(img)
        else:
            rec['error'] = j.get('error') or j.get('raw') or str(j)[:500]
    except Exception as e:  # network errors are logged, the run continues
        rec['error'] = repr(e)
    rec['sec'] = round(time.time() - t0, 1)
    with lock:
        with open(os.path.join(d, 'out', 'log.jsonl'), 'a') as f:
            f.write(json.dumps(rec) + '\n')
    return f"{slug} {grid}: {rec.get('status')} {rec['sec']}s cost={(rec.get('usage') or {}).get('cost')} err={str(rec.get('error'))[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='xeno_or')
    ap.add_argument('--models', default=','.join(MODELS))
    ap.add_argument('--grids', default='walk_front,walk_side,walk_back,kick')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--style', default='style', help='ref_<style>.png used as image 4 (style/consistency reference)')
    ap.add_argument('--tag', default='', help='suffix for output names (repeat runs)')
    ap.add_argument('--res', default='', help='override resolution: 1K/2K/4K')
    a = ap.parse_args()
    key = sys.stdin.readline().strip()
    os.makedirs(os.path.join(a.dir, 'out'), exist_ok=True)
    jobs = [(m, g) for g in a.grids.split(',') for m in a.models.split(',')]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda mg: one(key, a.dir, mg[0], mg[1], MODELS[mg[0]], a.dry, a.style, a.tag, a.res), jobs):
            print(res, flush=True)


if __name__ == '__main__':
    main()
