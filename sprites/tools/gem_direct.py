"""Direct Gemini API (own key, read from stdin) - synchronous generateContent for grid redraws.

  cat gemini_key.txt | python3 gem_direct.py --dir xeno_or --model gemini-nano-banana-2.1 --grids g16_walk --size 4K --tag nb21

Same inputs/prompt as or_bakeoff.py; output <dir>/out/<model>__<grid>_<tag>.png, log in <dir>/out/gem_log.jsonl.
"""
import argparse
import base64
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from or_bakeoff import PROMPT  # noqa: E402

API = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
PROMPT_NPC = (
    "Image 1 is a {grid} grid of {n} animation frames of a retro pixel-art game sprite, upscaled. "
    "Image 2 only shows the drawing style wanted (it is a different character - copy its rendering, not its design).\n"
    "Task: redraw image 1 as clean high-resolution 90s anime illustrations in the style of image 2: clean lineart, "
    "cel shading, crisp details. Keep the design, colors, clothing and proportions of the sprite in image 1 exactly. "
    "This is a precise trace-over: the result will be laid exactly over image 1, so matching its geometry matters most.\n"
    "Rules:\n"
    "1. Same canvas and the same {grid} grid; every figure stays in its cell at exactly the same position and size.\n"
    "2. Exactly the same pose in every frame; do not change the stance or the direction.\n"
    "3. Same colors as image 1.\n"
    "4. Exactly {n} figures, one per cell, in the same order.\n"
    "5. Flat solid magenta #FF00FF background in every cell, no grid lines, no shadows, no text, no extra objects.")


def parts_for(d, grid, style, npc=False, prompt_file='', refs=None):
    meta = json.load(open(os.path.join(d, 'in', 'grids.json')))[grid]
    cols, rows = meta[0].get('cols', 2), meta[0].get('rows', 2)
    template = open(prompt_file, encoding='utf-8').read() if prompt_file else (PROMPT_NPC if npc else PROMPT)
    parts = [{'text': template.format(grid=f'{cols}x{rows}', n=len(meta))}]
    if refs is not None:  # explicit reference list (may be empty) after the grid
        imgs = [f'grid_{grid}.png'] + [f'ref_{r}.png' for r in refs]
    else:
        imgs = [f'grid_{grid}.png', f'ref_{style}.png'] if npc else [f'grid_{grid}.png', 'ref_sheet.png', 'ref_face.png', f'ref_{style}.png']
    for p in imgs:
        with open(os.path.join(d, 'in', p), 'rb') as f:
            parts.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(f.read()).decode()}})
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='xeno_or')
    ap.add_argument('--model', required=True)
    ap.add_argument('--grids', required=True)
    ap.add_argument('--size', default='4K')
    ap.add_argument('--style', default='style')
    ap.add_argument('--tag', default='')
    ap.add_argument('--npc', action='store_true', help='NPC mode: no character references, style image only')
    ap.add_argument('--prompt-file', default='', help='custom prompt template with {grid} and {n}')
    ap.add_argument('--refs', default=None, help='comma list of ref_<name>.png after the grid ("" = none)')
    ap.add_argument('--thinking', default='', help='thinking level (e.g. minimal) if the model supports it')
    a = ap.parse_args()
    key = sys.stdin.readline().strip()
    os.makedirs(os.path.join(a.dir, 'out'), exist_ok=True)
    for grid in a.grids.split(','):
        out = os.path.join(a.dir, 'out', f"{a.model}__{grid}{'_' + a.tag if a.tag else ''}.png")
        gen = {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '1:1', 'imageSize': a.size}}
        if a.thinking:
            gen['thinkingConfig'] = {'thinkingLevel': a.thinking}
        refs = None if a.refs is None else [r for r in a.refs.split(',') if r]
        body = {'contents': [{'role': 'user', 'parts': parts_for(a.dir, grid, a.style, a.npc, a.prompt_file, refs)}],
                'generationConfig': gen}
        t0 = time.time()
        r = requests.post(API.format(model=a.model), headers={'x-goog-api-key': key}, json=body, timeout=900)
        rec = {'model': a.model, 'grid': grid, 'tag': a.tag, 'status': r.status_code, 'sec': round(time.time() - t0, 1)}
        j = r.json()
        rec['usage'] = j.get('usageMetadata')
        img = None
        for c in j.get('candidates', []):
            for p in c.get('content', {}).get('parts', []):
                if 'inlineData' in p:
                    img = base64.b64decode(p['inlineData']['data'])
        if img:
            with open(out, 'wb') as f:
                f.write(img)
            rec['bytes'] = len(img)
        else:
            rec['error'] = j.get('error') or [c.get('finishReason') for c in j.get('candidates', [])] or str(j)[:500]
        with open(os.path.join(a.dir, 'out', 'gem_log.jsonl'), 'a') as f:
            f.write(json.dumps(rec) + '\n')
        print(json.dumps(rec)[:600], flush=True)


if __name__ == '__main__':
    main()
