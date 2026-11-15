"""Nano Banana keyframe jobs for every anonymous map NPC set (massovka): one 16-cell grid per NPC.

  python campaign_npc_build.py [--dry] [--limit N]
Keyframes = frames that bring new sprite parts (greedy cover over whole-figure frames), filled up to 16 with evenly
spaced whole frames (the grid costs the same, more teacher frames = better NPC boards and training data).
Jobs are added to ai/campaign/jobs.json as m_<nid> (prompt npc_v2.txt, style reference only) and listed in
ai/campaign/npc_jobs.txt ("job|prompt|refs" lines for campaign_submit.sh on <JUMP_HOST>).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from campaign_build import OUT, STYLE, cover, thin, whole_frames  # noqa: E402
from render_build import groups  # noqa: E402

PER = 16


def keyframes(lay, setkey, hero_dir):
    frames = lay[setkey]['frames']
    ok = whole_frames(lay, setkey, hero_dir)
    fr = thin([f for f in cover(frames) if f in ok], PER)
    rest = [f for f in sorted(ok) if f not in fr]
    need = PER - len(fr)
    if need > 0 and rest:
        fr = sorted(fr + ([rest[len(rest) // 2]] if need == 1 else thin(rest, need)))
    return fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--shard', default='0/1', help='i/n: build every n-th NPC set (writes npc_frag_<i>.json)')
    ap.add_argument('--merge', action='store_true', help='merge the shard fragments into jobs.json and npc_jobs.txt')
    a = ap.parse_args()
    if a.merge:
        jp = os.path.join(OUT, 'jobs.json')
        jobs, lines = json.load(open(jp)), []
        for f in sorted(os.listdir(OUT)):
            if f.startswith('npc_frag_') and f.endswith('.json'):
                fr = json.load(open(os.path.join(OUT, f)))
                jobs.update(fr)
                lines += [f'{n}|npc_v2.txt|style' for n in fr]
        json.dump(jobs, open(jp, 'w'), indent=1)
        open(os.path.join(OUT, 'npc_jobs.txt'), 'w', newline='\n').write('\n'.join(sorted(lines)) + '\n')
        print('merged npc jobs', len(lines))
        return
    si, sn = map(int, a.shard.split('/'))
    jobs = {}
    lines, grids, frames_total = [], 0, 0
    todo = groups('massovka')[si::sn]
    if a.limit:
        todo = todo[:a.limit]
    for group, hd, _, _ in todo:
        nid = os.path.basename(hd)
        name = f'm_{nid}'
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        fr = keyframes(lay, 'npc', hd)
        if not fr:
            print('no whole frames', nid)
            continue
        frames_total += len(fr)
        grids += 1
        lines.append(f'{name}|npc_v2.txt|style')
        if a.dry:
            continue
        jobs[name] = {'hero_dir': os.path.relpath(hd, ROOT).replace('\\', '/'), 'set': 'npc', 'frames': fr,
                      'prompt': 'npc_v2.txt', 'refs': ['style'], 'grids': 1}
        d = os.path.join(OUT, name)
        if os.path.exists(os.path.join(d, 'in', 'grids.json')):
            continue
        shutil.rmtree(d, ignore_errors=True)
        subprocess.run([sys.executable, os.path.join(HERE, 'make_grids.py'), '--hero', name, '--hero-dir', hd, '--out', d,
                        '--frames', ','.join(f'npc:{f}' for f in fr), '--per', str(PER), '--prefix', 'g', '--grow'],
                       check=True, capture_output=True)
        shutil.copy(STYLE, os.path.join(d, 'in', 'ref_style.png'))
    if not a.dry:
        json.dump(jobs, open(os.path.join(OUT, f'npc_frag_{si}.json'), 'w'), indent=1)
    print('npc jobs', len(lines), 'grids', grids, 'keyframes', frames_total, f'~${grids * 0.057:.2f}')


if __name__ == '__main__':
    main()
