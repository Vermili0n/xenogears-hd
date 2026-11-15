"""LPIPS of every test3 render against the teacher (lower = closer), inside the original silhouette.

  python metrics_pod.py --set test3 --res res_test3 [--out metrics_test3.json]
Run folders: res_test3/<run>/<tag>/<name>.png (infer_pod.py layout). Groups per run/tag:
  char / npc / gear      full frames (npc = map NPC with its NPC board), npc_noref = NPC with the blank board,
  head_pass              16x head render vs the teacher head,
  head_from_full         head window cut from the full-frame render (headmap.json), upscaled, vs the teacher head.
"""
import argparse
import json
import os

import cv2
import lpips
import numpy as np
import torch
from PIL import Image

MAG = np.array([255, 0, 255], np.uint8)


def sil(ctrl):
    a = ctrl.astype(int)
    return (abs(a[..., 0] - 255) + a[..., 1] + abs(a[..., 2] - 255)) > 60


def prep(img, mask, box, size=256):
    x = img.copy()
    x[~mask] = MAG
    x = Image.fromarray(x).crop(box)
    w, h = x.size
    k = size / max(w, h)
    x = x.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    c = Image.new('RGB', (size, size), tuple(MAG))
    c.paste(x, ((size - x.width) // 2, (size - x.height) // 2))
    t = torch.from_numpy(np.asarray(c)).permute(2, 0, 1).float() / 127.5 - 1
    return t.unsqueeze(0).cuda()


GATE = 12.0  # mean low-frequency Lab difference (head pass vs full-frame head) above which the head pass is rejected


def consistency(a, b, mask, sigma=12):
    """Mean Lab distance of blurred images inside the mask: large when the layout differs (face vs hair)."""
    la = cv2.GaussianBlur(cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), sigma)
    lb = cv2.GaussianBlur(cv2.cvtColor(b, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), sigma)
    return float(np.linalg.norm(la - lb, axis=-1)[mask].mean())


def bbox(mask, pad=8):
    ys, xs = np.where(mask)
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(mask.shape[1], xs.max() + pad + 1), min(mask.shape[0], ys.max() + pad + 1))


def load(p):
    return np.asarray(Image.open(p).convert('RGB'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', default='test3')
    ap.add_argument('--res', default='res_test3')
    ap.add_argument('--out', default='metrics_test3.json')
    a = ap.parse_args()
    net = lpips.LPIPS(net='alex').cuda().eval()
    jobs3 = {j['name']: j for j in json.load(open(os.path.join(a.set, 'jobs.json')))}
    jobs2 = {j['name']: j for j in json.load(open(os.path.join(a.set, 'jobs_v2.json')))}
    jobs2.update({n: j for n, j in jobs3.items() if n.endswith('__head')})  # v2 heads: cut from its full frames
    hmap = json.load(open(os.path.join(a.set, 'headmap.json')))
    report, per_item = {}, {}
    for run in sorted(os.listdir(a.res)):
        for tag in sorted(os.listdir(os.path.join(a.res, run))):
            d = os.path.join(a.res, run, tag)
            groups, items = {}, {}
            cur = ['']

            def add(g, v):
                groups.setdefault(g, []).append(v)
                items.setdefault(cur[0], {})[g] = round(float(v), 4)

            jobs = jobs2 if run.startswith('v2') else jobs3
            with torch.no_grad():
                for n, j in jobs.items():
                    cur[0] = n
                    p = os.path.join(d, n + '.png')
                    tgt = load(os.path.join(a.set, j['target']))
                    if n.endswith('__head'):
                        ctrl = load(os.path.join(a.set, j['control']))
                        m = sil(ctrl)
                        if not m.any():
                            continue
                        b = bbox(m)
                        fp = os.path.join(d, hmap[n]['full'] + '.png')
                        cut = None
                        if os.path.exists(fp):
                            cut = np.asarray(Image.open(fp).convert('RGB').crop(tuple(hmap[n]['box'])).resize(m.shape[::-1], Image.LANCZOS))
                            add('head_from_full', net(prep(cut, m, b), prep(tgt, m, b)).item())
                        if os.path.exists(p):
                            hp = load(p)
                            add('head_pass', net(prep(hp, m, b), prep(tgt, m, b)).item())
                            if cut is not None:
                                # gate: keep the head pass only when it agrees with the full-frame head (no face on a back view)
                                agree = consistency(hp, cut, m)
                                items.setdefault(n, {})['agree'] = round(agree, 2)
                                best = hp if agree < GATE else cut
                                add('head_gated', net(prep(best, m, b), prep(tgt, m, b)).item())
                                add('head_gate_kept', float(agree < GATE))
                        continue
                    if not os.path.exists(p):
                        continue
                    ctrl = load(os.path.join(a.set, j['control']))
                    m = sil(ctrl)
                    if not m.any():
                        continue
                    b = bbox(m)
                    g = 'gear' if n.startswith('g_') else ('npc_noref' if n.endswith('__noref') or (n.startswith('n_') and 'blank' in j['ref'])
                                                          else 'npc' if n.startswith('n_') else 'char')
                    add(g, net(prep(load(p), m, b), prep(tgt, m, b)).item())
            report[f'{run}/{tag}'] = {g: [round(float(np.mean(v)), 4), len(v)] for g, v in sorted(groups.items())}
            per_item[f'{run}/{tag}'] = items
            print(f'{run}/{tag}', report[f'{run}/{tag}'], flush=True)
    json.dump(report, open(a.out, 'w'), indent=1)
    json.dump(per_item, open(a.out.replace('.json', '_items.json'), 'w'))


if __name__ == '__main__':
    main()
