"""Same jobs as gem_batch.py (JOBDIR/in/grid_*.png + ref_*.png), but through OpenRouter's image API, synchronously.

  cat key.txt | python3 or_batch.py --dir JOBDIR --prompt-file prompts/hero.txt --ref-list sheet,face,style \
      [--model google/gemini-nano-banana-2.1] [--resolution 4K] [--grids f00,f01] [--workers 3]
Results: JOBDIR/out/<grid>.png (skipped if present), log JOBDIR/out/or_log.jsonl (status, cost, size).
429/5xx are retried with backoff.
"""
import argparse
import base64
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API = 'https://openrouter.ai/api/v1/images'
lock = threading.Lock()


def png_size(b):
    """(w, h) from a PNG/JPEG/WEBP header without PIL (server has no Pillow)."""
    if b[1:4] == b'PNG':
        return int.from_bytes(b[16:20], 'big'), int.from_bytes(b[20:24], 'big')
    return len(b)


def data_url(path):
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()


def one(key, a, meta, g, refs, prompt_t):
    out = os.path.join(a.dir, 'out', f'{g}.png')
    if os.path.exists(out):
        return f'{g} skip'
    cols, rows = meta[g][0].get('cols', 4), meta[g][0].get('rows', 4)
    body = {'model': a.model, 'prompt': prompt_t.format(grid=f'{cols}x{rows}', n=len(meta[g])),
            'resolution': a.resolution, 'aspect_ratio': '1:1',
            'input_references': [{'type': 'image_url', 'image_url': {'url': u}}
                                 for u in [data_url(os.path.join(a.dir, 'in', f'grid_{g}.png'))] + refs]}
    rec = {'grid': g}
    for attempt in range(6):
        t0 = time.time()
        try:
            r = requests.post(API, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                              json=body, timeout=900)
            j = r.json() if r.headers.get('content-type', '').startswith('application/json') else {'raw': r.text[:300]}
        except Exception as e:  # noqa: BLE001
            r, j = None, {'error': repr(e)}
        rec.update(status=getattr(r, 'status_code', None), sec=round(time.time() - t0, 1), usage=j.get('usage'))
        if r is not None and r.ok and j.get('data'):
            img = base64.b64decode(j['data'][0]['b64_json'])
            open(out, 'wb').write(img)
            rec['size'] = png_size(img)
            break
        rec['error'] = str(j.get('error') or j.get('raw'))[:300]
        if rec['status'] not in (429, 500, 502, 503, 504, None):
            break
        time.sleep(20 * (attempt + 1))
    with lock:
        with open(os.path.join(a.dir, 'out', 'or_log.jsonl'), 'a') as f:
            f.write(json.dumps(rec) + '\n')
    return f"{g} {rec['status']} {rec.get('size')} cost={(rec.get('usage') or {}).get('cost')} {rec.get('error', '')[:120]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--prompt-file', required=True)
    ap.add_argument('--ref-list', default='sheet,face,style')
    ap.add_argument('--model', default='google/gemini-nano-banana-2.1')
    ap.add_argument('--resolution', default='4K')
    ap.add_argument('--grids', default='')
    ap.add_argument('--workers', type=int, default=3)
    a = ap.parse_args()
    key = sys.stdin.read().strip()
    meta = json.load(open(os.path.join(a.dir, 'in', 'grids.json')))
    grids = a.grids.split(',') if a.grids else sorted(meta)
    refs = [data_url(os.path.join(a.dir, 'in', f'ref_{r}.png')) for r in a.ref_list.split(',') if r]
    prompt_t = open(a.prompt_file, encoding='utf-8').read()
    os.makedirs(os.path.join(a.dir, 'out'), exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda g: one(key, a, meta, g, refs, prompt_t), grids):
            print(res, flush=True)


if __name__ == '__main__':
    main()
