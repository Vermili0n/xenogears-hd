"""Training triplets for LoRA v2 ("sprite frame + character reference -> redraw") from the Nano Banana campaign.

  python make_pairs_v2.py --out ai/pairs_v2 [--holdout c_alice_3d2b1c,h_fei_b3005_0]
For every frame accepted by prod_fit (ai/<job>_keys/work/<set>_<fi>_red.png, or the pilot folders below):
  control/<name>.png  = xBR sprite at 8x on magenta, bottom-centred in a 512 cell (as in make_pairs.py)
  ref/<name>.png      = the character's identity board: ChatGPT turnaround sheet on top, face close-up below
  target/<name>.png   = the redraw, same placement, original silhouette, magenta outside (+ .txt caption)
Jobs whose output was judged bad by eye are listed in BAD and skipped. split.json: held-out jobs for the test.
"""
import argparse
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ai_redraw import Hero  # noqa: E402
from make_pairs import pair  # noqa: E402

C = os.path.join(ROOT, 'ai', 'campaign')
FC = os.path.join(ROOT, 'for_chatgpt')
CAP = 'redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the second image, same pose and silhouette, flat magenta background'
BAD = {'c_dominia_yizkor_850066', 'c_dominia_yizkor_270c13', 'c_kelvena_72b597', 'c_kelvena_c2df43', 'g_field_111471'}
PILOT = [  # (prod_fit work dir, hero folder, refs slug)
    ('ai/elly_keys/work', 'extracted/disc1_full/elly', 'elly'),
    ('ai/bart_keys/work', 'extracted/disc1_full/bart', 'bart'),
    ('ai/billy_keys/work', 'extracted/disc1_full/billy', 'billy'),
]


def ref_board(slug, size=512):
    """Sheet (top) + face (bottom-centre) on light grey, one 512 square."""
    b = Image.new('RGB', (size, size), (205, 205, 205))
    sh = Image.open(os.path.join(FC, slug, 'chatgpt_sheet.png')).convert('RGB')
    sh.thumbnail((size, int(size * 0.62)), Image.LANCZOS)
    b.paste(sh, ((size - sh.width) // 2, 0))
    fa = Image.open(os.path.join(FC, slug, 'chatgpt_face.png')).convert('RGB')
    fa.thumbnail((int(size * 0.38), int(size * 0.38)), Image.LANCZOS)
    b.paste(fa, ((size - fa.width) // 2, size - fa.height))
    return b


def slug_of(job):
    """c_<slug>_<nid6> / h_<hero>_... / g_... -> refs folder (None for gears: no identity reference)."""
    if job.startswith('h_'):
        h = job.split('_')[1]
        return 'emeralda_adult' if job == 'h_emeralda_adult' else h
    if job.startswith('c_'):
        return job[2:].rsplit('_', 1)[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'ai', 'pairs_v2'))
    ap.add_argument('--holdout', default='c_alice_3d2b1c,h_fei_b3005_0,g_worldmap_3951')
    a = ap.parse_args()
    for d in ('control', 'ref', 'target'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    jobs = json.load(open(os.path.join(C, 'jobs.json')))
    hold = set(a.holdout.split(','))
    split, boards, n = {'train': [], 'test': []}, {}, 0
    exp = os.path.join(C, '_exclude_frames.json')  # single frames rejected by eye (e.g. eyepatch on both eyes)
    excl = {(j, t) for j, ts in (json.load(open(exp)).items() if os.path.exists(exp) else []) for t in ts}
    sources = []
    for job, v in jobs.items():
        if job in BAD:
            continue
        sources.append((job, os.path.join(ROOT, 'ai', f'{job}_keys', 'work'), os.path.join(ROOT, v['hero_dir']), slug_of(job)))
    for w, hd, slug in PILOT:
        sources.append((os.path.basename(os.path.dirname(w)), os.path.join(ROOT, w), os.path.join(ROOT, hd), slug))
    for job, w, hd, slug in sources:
        if not os.path.isdir(w):
            continue
        h = Hero(hd)
        if slug and slug not in boards:
            boards[slug] = ref_board(slug)
        for f in sorted(os.listdir(w)):
            if not f.endswith('_red.png'):
                continue
            parts = f[:-8].rsplit('_', 1)
            setkey, fi = parts[0], int(parts[1])
            if setkey not in h.layout:
                continue
            if (job, f'{setkey}:{fi}') in excl:
                continue
            name = f'{job}__{setkey}_{fi:03d}'
            try:
                c, t = pair(h, setkey, fi, os.path.join(w, f), 512, 500)
            except Exception:  # noqa: BLE001
                continue
            c.save(os.path.join(a.out, 'control', name + '.png'))
            (boards[slug] if slug else Image.new('RGB', (512, 512), (205, 205, 205))).save(os.path.join(a.out, 'ref', name + '.png'))
            t.save(os.path.join(a.out, 'target', name + '.png'))
            cap = CAP if slug else 'redraw this pre-rendered mecha sprite as a clean detailed illustration, same pose and silhouette, flat magenta background'
            open(os.path.join(a.out, 'target', name + '.txt'), 'w').write(cap)
            split['test' if job in hold else 'train'].append(name)
            n += 1
    json.dump(split, open(os.path.join(a.out, 'split.json'), 'w'), indent=1)
    print('triplets', n, 'train', len(split['train']), 'test', len(split['test']), 'characters', len(boards))


if __name__ == '__main__':
    main()
