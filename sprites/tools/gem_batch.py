"""Gemini Batch API (50% price) for grid redraws. Key is read from stdin. Run on the non-RU host.

  cat key | python3 gem_batch.py submit --dir JOBDIR --refs REFDIR --model gemini-3-pro-image --size 4K [--grids f00,f01]
  cat key | python3 gem_batch.py poll   --dir JOBDIR [--wait]

JOBDIR/in/grid_<name>.png + grids.json (from make_grids.py), REFDIR/ref_{sheet,face,style}.png.
Uploads go through the Files API (kept 48 h, cached in JOBDIR/uploads.json); the batch name is written to
JOBDIR/batches.json right after submission. Results: JOBDIR/out/<name>.png, usage in JOBDIR/out/batch_log.jsonl.
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

# without the face close-up: it can pull the model into drawing 16 identical portraits (seen twice on run frames)
PROMPT_NOFACE = (PROMPT.replace("Images 2-4 are references of the same character: image 2 is a turnaround sheet, image 3 is a face close-up, "
                                "image 4 shows the exact rendering style wanted at sprite proportions.",
                                "Images 2-3 are references of the same character: image 2 is a turnaround sheet, "
                                "image 3 shows the exact rendering style wanted at sprite proportions.")
                 .replace("with the face and outfit details of images 2 and 3.", "with the face and outfit details of image 2.")
                 .replace("strong likeness to image 3.", "strong likeness to image 2."))

BASE = 'https://generativelanguage.googleapis.com'


def upload(key, path, cache):
    st = os.stat(path)
    ck = f'{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}'
    if ck in cache and time.time() - cache[ck]['t'] < 40 * 3600:
        return cache[ck]['uri']
    data = open(path, 'rb').read()
    r = requests.post(f'{BASE}/upload/v1beta/files', headers={
        'x-goog-api-key': key, 'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
        'X-Goog-Upload-Header-Content-Length': str(len(data)), 'X-Goog-Upload-Header-Content-Type': 'image/png',
        'Content-Type': 'application/json'}, json={'file': {'display_name': os.path.basename(path)}}, timeout=60)
    r.raise_for_status()
    url = r.headers['X-Goog-Upload-URL']
    r = requests.post(url, headers={'Content-Length': str(len(data)), 'X-Goog-Upload-Offset': '0',
                                    'X-Goog-Upload-Command': 'upload, finalize'}, data=data, timeout=300)
    r.raise_for_status()
    uri = r.json()['file']['uri']
    cache[ck] = {'uri': uri, 't': time.time()}
    return uri


def cmd_submit(a, key):
    meta = json.load(open(os.path.join(a.dir, 'in', 'grids.json')))
    grids = a.grids.split(',') if a.grids else sorted(meta)
    cpath = os.path.join(a.dir, 'uploads.json')
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    names = ('sheet', a.style) if a.noface else ('sheet', 'face', a.style)
    if a.ref_list is not None:  # explicit references (e.g. NPC mode: style only)
        names = tuple(r for r in a.ref_list.split(',') if r)
    refs = [upload(key, os.path.join(a.refs, f'ref_{r}.png'), cache) for r in names]
    prompt_t = PROMPT_NOFACE if a.noface else PROMPT
    if a.prompt_file:
        prompt_t = open(a.prompt_file, encoding='utf-8').read()
    reqs = []
    for g in grids:
        cols = meta[g][0].get('cols', 2)
        rows = meta[g][0].get('rows', 2)
        guri = upload(key, os.path.join(a.dir, 'in', f'grid_{g}.png'), cache)
        json.dump(cache, open(cpath, 'w'))
        parts = [{'text': prompt_t.format(grid=f'{cols}x{rows}', n=len(meta[g]))}]
        parts += [{'file_data': {'mime_type': 'image/png', 'file_uri': u}} for u in [guri] + refs]
        reqs.append({'request': {'contents': [{'role': 'user', 'parts': parts}],
                                 'generation_config': {'response_modalities': ['IMAGE'],
                                                       'image_config': {'aspect_ratio': '1:1', 'image_size': a.size}}},
                     'metadata': {'key': g}})
    body = {'batch': {'display_name': a.name or os.path.basename(os.path.abspath(a.dir)),
                      'input_config': {'requests': {'requests': reqs}}}}
    r = requests.post(f'{BASE}/v1beta/models/{a.model}:batchGenerateContent', headers={'x-goog-api-key': key},
                      json=body, timeout=300)
    j = r.json()
    if not r.ok:
        print('SUBMIT FAILED', r.status_code, json.dumps(j)[:800])
        sys.exit(1)
    name = j.get('name')
    bpath = os.path.join(a.dir, 'batches.json')
    rec = json.load(open(bpath)) if os.path.exists(bpath) else []
    rec.append({'name': name, 'model': a.model, 'grids': grids, 'submitted': time.strftime('%Y-%m-%d %H:%M:%S')})
    json.dump(rec, open(bpath, 'w'), indent=1)
    print('submitted', name, len(grids), 'requests')


def find_key(obj, k):
    """Depth-first search for a key in nested dicts/lists."""
    if isinstance(obj, dict):
        if k in obj:
            return obj[k]
        for v in obj.values():
            r = find_key(v, k)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, k)
            if r is not None:
                return r
    return None


def cmd_poll(a, key):
    bpath = os.path.join(a.dir, 'batches.json')
    os.makedirs(os.path.join(a.dir, 'out'), exist_ok=True)
    while True:
        pending = 0
        rec = json.load(open(bpath))
        for b in rec:
            if b.get('done'):
                continue
            r = requests.get(f"{BASE}/v1beta/{b['name']}", headers={'x-goog-api-key': key}, timeout=300)
            j = r.json()
            state = find_key(j, 'state')
            print(b['name'], state, flush=True)
            if state not in ('BATCH_STATE_SUCCEEDED', 'JOB_STATE_SUCCEEDED', 'BATCH_STATE_FAILED', 'JOB_STATE_FAILED',
                             'BATCH_STATE_CANCELLED', 'BATCH_STATE_EXPIRED', 'JOB_STATE_CANCELLED', 'JOB_STATE_EXPIRED'):
                pending += 1
                continue
            inl = find_key(j, 'inlinedResponses')
            if isinstance(inl, dict):
                inl = inl.get('inlinedResponses', [])
            for item in inl or []:
                g = (item.get('metadata') or {}).get('key')
                resp = item.get('response') or {}
                img = None
                for c in resp.get('candidates', []):
                    for p in c.get('content', {}).get('parts', []):
                        if 'inlineData' in p:
                            img = base64.b64decode(p['inlineData']['data'])
                log = {'batch': b['name'], 'grid': g, 'usage': resp.get('usageMetadata'),
                       'error': item.get('error') or (None if img else [c.get('finishReason') for c in resp.get('candidates', [])])}
                if img:
                    open(os.path.join(a.dir, 'out', f'{g}.png'), 'wb').write(img)
                with open(os.path.join(a.dir, 'out', 'batch_log.jsonl'), 'a') as f:
                    f.write(json.dumps(log) + '\n')
                print(' ', g, 'OK' if img else f"FAIL {log['error']}", flush=True)
            b['done'] = state
            json.dump(rec, open(bpath, 'w'), indent=1)
        if not a.wait or pending == 0:
            break
        time.sleep(60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['submit', 'poll'])
    ap.add_argument('--dir', required=True)
    ap.add_argument('--refs', default='')
    ap.add_argument('--model', default='gemini-3-pro-image')
    ap.add_argument('--size', default='4K')
    ap.add_argument('--style', default='style')
    ap.add_argument('--grids', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--wait', action='store_true')
    ap.add_argument('--noface', action='store_true', help='leave out the face close-up reference')
    ap.add_argument('--prompt-file', default='', help='prompt template with {grid} and {n}')
    ap.add_argument('--ref-list', default=None, help='comma list of ref names after the grid ("" = none)')
    a = ap.parse_args()
    key = sys.stdin.readline().strip()
    (cmd_submit if a.cmd == 'submit' else cmd_poll)(a, key)


if __name__ == '__main__':
    main()
