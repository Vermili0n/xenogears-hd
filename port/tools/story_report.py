"""What the story walk found, summed: python tools/story_report.py [out/sweep_story]

From live.csv (every frame the explorer played, by segment) and story.csv (each state replayed through the bridge):
the frames and segments by program, the bridge's tallies in total, and for each class of FSession::Unhandled the frames
it was in, its summed count, the segments and the states it was met in, with the first few of each as examples.
Writes <folder>/report.txt and prints it.
"""
import csv
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = {'-1': 'none', '0': 'debug', '1': 'field', '2': 'battle', '3': 'worldmap', '4': 'battling', '5': 'menu', '6': 'movie'}


def classes(header):
    return [name[:-len('_frames')] for name in header if name.endswith('_frames') and name != 'first_frame']


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'out', 'sweep_story')
    lines = []
    say = lines.append
    live = list(csv.DictReader(open(os.path.join(folder, 'live.csv'), encoding='utf-8')))
    say(f'live.csv: {len(live)} segments, {sum(int(r["frames"]) for r in live)} frames')
    by_program = defaultdict(lambda: [0, 0])
    for row in live:
        by_program[PROGRAMS.get(row['program'], row['program'])][0] += 1
        by_program[PROGRAMS.get(row['program'], row['program'])][1] += int(row['frames'])
    say('  by program (segments, frames): ' + ', '.join(f'{k} {v[0]}/{v[1]}' for k, v in sorted(by_program.items())))
    totals = {k: sum(int(r[k]) for r in live) for k in ['builds', 'sprite_pieces', 'sprite_hd', 'sprite_partial', 'sprite_vram', 'scenery_hd',
                                                       'scenery_vram', 'scenery_hd_mixed', 'screen_textured', 'screen_hd']}
    say('  tallies over builds: ' + ', '.join(f'{k} {v}' for k, v in totals.items()))
    stories = sorted({int(r['story']) for r in live})
    say(f'  story values met: {stories[0]}..{stories[-1]} ({len(stories)} values); field maps: {sorted({int(r["map"]) for r in live if r["program"] == "1"})}')
    say('')
    say('class: frames with it (all frames), summed count, segments; examples (segment story/map/program frames)')
    for name in classes(live[0].keys()):
        frames = sum(int(r[name + '_frames']) for r in live)
        total = sum(int(r[name]) for r in live)
        hit = [r for r in live if int(r[name + '_frames']) > 0]
        examples = '; '.join(f'#{r["segment"]} s{r["story"]}/m{r["map"]}/{PROGRAMS.get(r["program"], r["program"])} {r[name + "_frames"]}f' for r in hit[:4])
        say(f'  {name}: {frames} frames, sum {total}, {len(hit)} segments; {examples}')
    path = os.path.join(folder, 'story.csv')
    if os.path.exists(path):
        states = list(csv.DictReader(open(path, encoding='utf-8')))
        say('')
        say(f'story.csv: {len(states)} states; load errors {sum(1 for s in states if s["load_error"])}, core errors {sum(1 for s in states if s["core_error"])}')
        for s in states:
            if s['load_error'] or s['core_error']:
                say(f'  {s["state"]}: load "{s["load_error"]}" core "{s["core_error"]}"')
        keys = ['sprite_pieces', 'sprite_hd', 'sprite_partial', 'sprite_vram', 'scenery_hd', 'scenery_vram', 'scenery_hd_mixed', 'screen_textured', 'screen_hd',
                'miss_no_upload', 'miss_split', 'miss_name', 'missing_names']
        say('  tallies (sum over states x frames): ' + ', '.join(f'{k} {sum(int(s[k]) for s in states)}' for k in keys))
        for name in classes(states[0].keys()):
            hit = [s for s in states if int(s[name + '_frames']) > 0]
            if hit:
                say(f'  {name}: {len(hit)} states, {sum(int(s[name + "_frames"]) for s in hit)} frames, sum {sum(int(s[name]) for s in hit)}; '
                    + ', '.join(s['state'][:-6] for s in hit[:3]))
    text = '\n'.join(lines)
    open(os.path.join(folder, 'report.txt'), 'w', encoding='utf-8').write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
