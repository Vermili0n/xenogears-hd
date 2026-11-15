"""Jobs for re-rendering the QA fix list (ai/prod/fixlist.json: {"<frame name>": "back" | "eyepatch" | "eyepatch_left" | "glasses" | "front" | "flip" | "boots" | "white_coat" | "visor" | "creature" | "short_hair" | "dog" | "mask"}).

Every listed frame is re-rendered together with its head close-up (<name>__head, when the job exists) with a hint
appended to the prompt. Frames whose control image is byte-identical (twin groups) are rendered once.

  python fix_jobs.py --test [--per-kind 6]   -> ai/prod/jobs_fixtest.json: a sample of distinct cases, each with every
                                                hint variant (names <job>__<variant>) - pick the best variant by eye
  python fix_jobs.py --back B1 --back-head B2 --eyepatch E1 -> ai/prod/jobs_fix.json + fix_map.json (rendered -> all names)
  (29.10 test on Bart: B1/B2 both fix back views, B2 adds the strap knot on heads but misplaced a body part once; E1 puts
  the patch on the sprite's eye in front views, E2 mirrored it once; 3/4 views: both hints cover the NEAR eye - leave
  3/4 frames out of the list)
Render on the pod into a separate folder (infer_pod --out res_fix), then tools/fix_apply.py puts the results in place.
"""
import argparse
import hashlib
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROD = os.path.join(ROOT, 'ai', 'prod')

HINTS = {
    'back': {
        'B1': ', back view seen from behind, the face is not visible',
        'B2': ', seen from behind: the back of his head and the long braid down his back, the eyepatch strap knot on the '
              'back of the head, no face visible',
    },
    'eyepatch': {
        'E1': ', he wears a black eyepatch over one eye exactly where the sprite shows the dark patch',
        'E2': ', a black eyepatch covers one eye (not a headband), only one eye is visible',
    },
    # frames whose SPRITE has the patch on the viewer's left (his right eye); the user wants it on his left eye
    'eyepatch_left': {
        'L1': ', he wears a black eyepatch over his left eye, which is on the right side of the picture; '
              'his right eye on the left side of the picture is open',
    },
    # Citan: the sprite shows the glasses glint, the render dropped the glasses (29.10 QA, untested hint)
    'glasses': {
        'G1': ', he wears small round wire-rimmed glasses over his eyes',
    },
    # the reverse of 'back' (29.10 QA, Fei): the sprite faces the viewer with the head bowed (top of the head, belt buckle
    # and chest seen), the render drew the back with the ponytail or hair over the face (untested hints)
    'front': {
        'F1': ', front view: he faces the viewer with his head bowed forward so the top of his head is seen, '
              'his chest and belt buckle face the viewer, the ponytail hangs behind his back',
    },
    # top-down poses read upside down: the legs at the top of the sprite were drawn as hair, the head as boots
    'flip': {
        'V1': ', seen from above: his head is at the bottom of the picture and his legs and boots are at the top',
    },
    # lying figures: the boots at the end of the legs were drawn as a hair tuft
    'boots': {
        'S1': ', he lies stretched out, the end of his legs opposite the head shows his brown boots, no hair there',
    },
    # masked / visored NPCs (m_1590970b92, m_5ae1bcc718): the sprite's dark band over the eyes was dropped, open eyes
    # drawn under it - generic wording, the sprite shows the visor's shape and colour (untested hint)
    'visor': {
        'R1': ', a mask covers the face exactly as the sprite shows it: a dark visor over the eyes and a dark band over '
              'the mouth, no eyes and no mouth are visible',
    },
    # m_7d47706ecb (bearded man): his board gave him a ponytail in back views; user 29.10: the character has short hair
    # like his twin m_42ee795e87 - back / 3/4-back frames re-rendered without the ponytail (untested hint)
    'short_hair': {
        'H1': ', he has short cropped hair, no ponytail and no hair tie, the back of his head and neck show short hair',
    },
    # m_638d594da7 (green cat-creature seen from above): one frame drawn as a cloaked human with a face (untested hint)
    'creature': {
        'C1': ', this is a green cat-like creature with long pointed ears and a striped tail seen from above, its head at '
              'the bottom of the picture, not a human, no human face',
    },
    # m_aefa9b1fa9 (rabbit-eared figure in a white mask): some front frames drew a human face instead of the mask (untested)
    'mask': {
        'M1': ', the face is covered by a white mask with dark slanted eye holes and red marks exactly as the sprite shows it, '
              'no human eyes are visible',
    },
    # m_87d09a2f5d (dog): one frame got a human face on the dog's head (untested hint)
    'dog': {
        'D1': ', this is a dog with a dog muzzle, black nose and floppy ears, not a human face',
    },
    # Kim (c_kim_b47428): the sprite wears the white doctor's coat, the board's dark jacket won (untested hint)
    'white_coat': {
        'W1': ', he wears a long white doctor\'s coat exactly as the sprite shows it, not a dark jacket',
    },
}


def load_jobs():
    jobs = {}
    for fn in ('jobs_v4.json', 'jobs_v2.json'):
        for j in json.load(open(os.path.join(PROD, fn))):
            jobs[j['name']] = j
    return jobs


def ctrl_md5(j):
    return hashlib.md5(open(os.path.join(PROD, j['control']), 'rb').read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', action='store_true')
    ap.add_argument('--per-kind', type=int, default=6)
    ap.add_argument('--back', choices=sorted(HINTS['back']))
    ap.add_argument('--eyepatch', choices=sorted(HINTS['eyepatch']))
    ap.add_argument('--back-head', choices=sorted(HINTS['back']), help='hint for the head close-ups of back views '
                    '(default: same as --back)')
    a = ap.parse_args()
    fix = json.load(open(os.path.join(PROD, 'fixlist.json')))
    dp = os.path.join(PROD, 'fix_done.json')  # names already re-rendered and applied (fix_apply.py)
    done = set(json.load(open(dp))) if os.path.exists(dp) and not a.test else set()
    fix = {k: v for k, v in fix.items() if k not in done}
    jobs = load_jobs()
    # distinct cases: frame + head share the frame's control hash key; the board is part of the key - the same frame
    # in two massovka NPCs (or Emeralda / adult Emeralda) is drawn with different boards and must stay apart
    cases = defaultdict(list)                                   # (kind, md5, board) -> [frame names]
    for name, kind in sorted(fix.items()):
        cases[(kind, ctrl_md5(jobs[name]), jobs[name]['ref'])].append(name)
    out, fmap = [], {}
    if a.test:
        for kind in HINTS:
            picked = [v[0] for k, v in sorted(cases.items()) if k[0] == kind]
            step = max(1, len(picked) // a.per_kind)
            for name in picked[::step][:a.per_kind]:
                for nm in (name, name + '__head'):
                    if nm not in jobs:
                        continue
                    j = jobs[nm]
                    for var, hint in [('plain', '')] + sorted(HINTS[kind].items()):
                        out.append(dict(j, name=f'{nm}__{var}', prompt=j['prompt'] + hint))
        path = os.path.join(PROD, 'jobs_fixtest.json')
    else:
        if not (a.back and a.eyepatch):
            ap.error('--back and --eyepatch are required (or --test)')
        choice = {'back': HINTS['back'][a.back], 'eyepatch': HINTS['eyepatch'][a.eyepatch],
                  'eyepatch_left': HINTS['eyepatch_left']['L1'], 'glasses': HINTS['glasses']['G1'],
                  'front': HINTS['front']['F1'], 'flip': HINTS['flip']['V1'], 'boots': HINTS['boots']['S1'],
                  'white_coat': HINTS['white_coat']['W1'], 'visor': HINTS['visor']['R1'],
                  'creature': HINTS['creature']['C1'], 'short_hair': HINTS['short_hair']['H1'],
                  'dog': HINTS['dog']['D1'], 'mask': HINTS['mask']['M1']}
        head_choice = dict(choice, back=HINTS['back'][a.back_head or a.back])
        generic_head = dict(choice, back=HINTS['back'][a.back])   # B2 names Bart's braid and strap: Bart only
        for (kind, _, _), names in sorted(cases.items()):
            for suffix in ('', '__head'):
                rep = names[0] + suffix
                if rep not in jobs:
                    continue
                j = jobs[rep]
                hc = head_choice if 'bart' in rep.split('__')[0] else generic_head
                out.append(dict(j, prompt=j['prompt'] + (hc if suffix else choice)[kind]))
                fmap[rep] = [n + suffix for n in names if n + suffix in jobs]
        path = os.path.join(PROD, 'jobs_fix.json')
        json.dump(fmap, open(os.path.join(PROD, 'fix_map.json'), 'w'), indent=1)
    json.dump(out, open(path, 'w'), indent=1)
    print(f'{len(fix)} listed frames, {len(cases)} distinct cases -> {len(out)} jobs in {os.path.basename(path)}')


if __name__ == '__main__':
    main()
