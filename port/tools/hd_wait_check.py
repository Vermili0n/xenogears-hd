"""The pack's pictures drawn late: live runs of the game window with hdlog=, the old rule (hdsync=0: VRAM's texels until a
picture is loaded) against the new (hdsync=1: a frame's new pictures loaded before it is shown), and what each costs.

  python tools/hd_wait_check.py <out folder> [scene ...]

Per scene and rule: game frames, sprite pieces drawn from VRAM only because their picture was not loaded yet (and of
them in frames past the scene's first), 2D primitives the same, sprite pieces from VRAM for any reason, pictures loaded
and their wait (ms from first asked for to ready), the frame's longest synchronous load, the window's quit line (sound
underruns, longest process gap) and its stall / error lines.
"""
import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
HOLDS = 'at=2:hold=up+circle,5:hold=down+circle,8:hold=left+circle,11:hold=right+circle,14:hold=up+circle,17:hold=none'
SCENES = {
    # The night on the way back (story 16, map 15): Citan follows Fei; both run.
    'night_run': ['state=out/sweep_sprites/hd/s108.state', HOLDS],
    # Lahan the day before the festival (story 7, map 1): Fei runs among the villagers.
    'lahan_run': ['state=out/sweep_sprites/hd/s010.state', HOLDS],
    # The first battle of the prologue.
    'battle': ['map=4', 'ff=4400'],
    # The world map from the user's save (slot 1), walking.
    'world_map': ['card=out/saves/usa.srm', 'slot=1', 'at=5:hold=up,9:hold=right,13:hold=down,17:hold=none'],
    # Lahan from a new game's state, no buttons (the regression's live run).
    'map1': ['map=1'],
    # A map with Weltall's pilot stand-ins (Fei and Citan drawn small, port rows: pictures found by content), new game.
    'pilots': ['map=267'],
    # The user's pause: the night run, the cheat panel (F1: the game stands, the loader goes on) open from 3 s to 5 s.
    'night_pause': ['state=out/sweep_sprites/hd/s108.state', 'at=1:hold=up+circle,3:panel,5:panel,7:hold=none'],
}


def run(folder, scene, sync):
    log = os.path.join(folder, f'{scene}_sync{sync}.csv')
    args = [GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + SCENES[scene] + ['quit_after=20', f'hdsync={sync}', 'hdlog=' + os.path.relpath(log, ROOT).replace('\\', '/')]
    out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    lines = [line for line in out.splitlines() if 'quit_after' in line or 'stall' in line or 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]
    final = {}
    for row in csv.DictReader(open(log)):
        final[int(row['game_frame'])] = row  # the last pass of each frame is the one shown
    frames = sorted(final)
    first = frames[0] if frames else 0
    total = lambda column, after=-1: sum(int(final[f][column]) for f in frames if f > after)
    # Past the scene's first second (30 frames): where the old rule's waits are no longer the map's entry.
    keys = list(csv.DictReader(open(log + '.keys.csv')))
    waits = sorted(float(k['ms']) for k in keys if k['kind'] == 'picture' and float(k['ms']) >= 0)
    sync_longest = max([int(final[f]['sync_usec']) for f in frames] + [0]) / 1000.0
    summary = (f"{scene} hdsync={sync}: frames {len(frames)}; sprite pieces {total('sprite_pieces')}, waiting {total('sprite_waiting')} "
               f"(after the first 30 frames {total('sprite_waiting', first + 30)}), from VRAM {total('sprite_vram')}; 2D textured {total('screen_textured')}, "
               f"waiting {total('screen_waiting')} (after 30: {total('screen_waiting', first + 30)}); pictures {len(waits)}, wait ms median "
               f"{waits[len(waits) // 2] if waits else 0:.1f} p90 {waits[int(len(waits) * 0.9)] if waits else 0:.1f} max {waits[-1] if waits else 0:.1f}; "
               f"longest synchronous load {sync_longest:.1f} ms; frames with a sprite piece waiting {sum(1 for f in frames if int(final[f]['sprite_waiting']) > 0)}")
    if scene == 'night_pause':
        # The frames on either side of the panel (the game stands while it is open: no frames are built).
        gap = max(range(1, len(frames)), key=lambda i: int(final[frames[i]]['usec']) - int(final[frames[i - 1]]['usec']))
        before, after = final[frames[gap - 1]], final[frames[gap]]
        summary += (f"; panel: {(int(after['usec']) - int(before['usec'])) / 1e6:.2f} s between frames {frames[gap - 1]} and {frames[gap]}, "
                    f"sprite pieces waiting {before['sprite_waiting']} before it, {after['sprite_waiting']} after")
    return summary, lines


def main():
    folder = sys.argv[1]
    scenes = sys.argv[2:] or list(SCENES)
    with open(os.path.join(folder, 'hd_wait_check.txt'), 'a') as report:
        for scene in scenes:
            for sync in (0, 1):
                summary, lines = run(folder, scene, sync)
                print(summary)
                report.write(summary + '\n')
                for line in lines:
                    print('   ', line)
                    report.write('    ' + line + '\n')
                report.flush()


if __name__ == '__main__':
    main()
