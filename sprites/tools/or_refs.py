"""Character references through OpenRouter's image API (same prompts as the ChatGPT helper) when the web limit is out.

  cat key.txt | python3 or_refs.py --dir <char folder> --step sheet|face [--model openai/gpt-5.4-image-2]
Inputs: collage.png (+ chatgpt_sheet.png for the face step, so the face matches the sheet). Output: chatgpt_<step>.png.
"""
import argparse
import base64
import json
import os
import sys
import time

import requests

API = 'https://openrouter.ai/api/v1/images'


def data_url(path):
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--step', choices=['sheet', 'face'], required=True)
    ap.add_argument('--prompt-file', required=True)
    ap.add_argument('--model', default='openai/gpt-5.4-image-2')
    a = ap.parse_args()
    key = sys.stdin.read().strip()
    refs = [os.path.join(a.dir, 'collage.png')]
    if a.step == 'face' and os.path.exists(os.path.join(a.dir, 'chatgpt_sheet.png')):
        refs.append(os.path.join(a.dir, 'chatgpt_sheet.png'))
    prompt = open(a.prompt_file, encoding='utf-8').read()
    if a.step == 'face' and len(refs) > 1:
        prompt += ' The second attached picture is the turnaround sheet already drawn for this character: keep the same design.'
    size = '1536x1024' if a.step == 'sheet' else '1024x1024'
    body = {'model': a.model, 'prompt': prompt, 'size': size,
            'input_references': [{'type': 'image_url', 'image_url': {'url': data_url(p)}} for p in refs]}
    t0 = time.time()
    r = requests.post(API, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, json=body, timeout=900)
    j = r.json() if r.headers.get('content-type', '').startswith('application/json') else {'raw': r.text[:800]}
    if r.ok and j.get('data'):
        out = os.path.join(a.dir, f'chatgpt_{a.step}.png')
        open(out, 'wb').write(base64.b64decode(j['data'][0]['b64_json']))
        print('ok', out, f'{time.time() - t0:.0f}s', 'cost', (j.get('usage') or {}).get('cost'))
    else:
        print('FAILED', r.status_code, json.dumps(j)[:800])
        sys.exit(1)


if __name__ == '__main__':
    main()
