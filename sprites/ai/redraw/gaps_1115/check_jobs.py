r"""Integrity of pod job folders before upload (16.11.2026).

  python ai\redraw\gaps_1115\check_jobs.py pod_multitex pod_rest
Per folder: every jobs*.json run.sh names is read, every job's control/ref exists and opens as an image (control 512x512),
names are unique per output folder, run.sh refers to existing jobs files and LoRAs the README lists; prints the count of
pictures each run.sh line will make.
"""
import json
import os
import re
import sys

from PIL import Image

from gcommon import HERE, ROOT


def check(folder):
    d = os.path.join(HERE, folder)
    run = open(os.path.join(d, 'run.sh')).read()
    bad, total = [], 0
    for m in re.finditer(r'--jobs redraw/' + folder + r'/(\S+) --out redraw/' + folder + r'/(\S+) .*?--lora lora/(\S+)', run):
        jf, out, lora = m.groups()
        p = os.path.join(d, jf)
        if not os.path.exists(p):
            bad.append(f'{jf}: missing')
            continue
        jobs = json.load(open(p))
        names = [j['name'] for j in jobs]
        if len(set(names)) != len(names):
            bad.append(f'{jf}: duplicate names')
        for j in jobs:
            for key in ('control', 'ref'):
                if not j.get(key):
                    if key == 'control':
                        bad.append(f"{j['name']}: no control")
                    continue
                q = os.path.join(d, j[key])
                try:
                    im = Image.open(q)
                    im.load()
                    if key == 'control' and im.size != (512, 512):
                        bad.append(f"{j['name']}: control {im.size}")
                except Exception as ex:  # noqa: BLE001
                    bad.append(f"{j['name']}: {key} {j[key]} {ex}")
            if not j.get('prompt'):
                bad.append(f"{j['name']}: no prompt")
        lp =os.path.join(ROOT, 'lora', 'klein_' + lora.split('_')[2].split('.')[0], lora)
        if not os.path.exists(lp):
            bad.append(f'LoRA {lora} not at {lp}')
        print(f'  {jf} -> {out}: {len(jobs)} pictures, LoRA {lora}')
        total += len(jobs)
    print(f'{folder}: {total} pictures, problems {len(bad)}')
    for b in bad[:20]:
        print('   ', b)
    return total, bad


def main():
    for f in sys.argv[1:]:
        check(f)


if __name__ == '__main__':
    main()
