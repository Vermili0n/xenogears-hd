"""The regression of the night's tasks, in one go: each Godot run's shot against its reference, pixel by pixel, the
numbers the log prints, the headless sweep of maps 1-2 against out/sweep/sweep.csv, and the live 20 s run's stalls and
underruns. Usage: python tools/regress.py <out folder for this run's shots and logs> [--no-live] [--game=<folder>]
[--build=<folder>] [--quiet]
--game: the Godot project to run (by default game/; game_work/ is a copy run while the player's game holds game/bin);
--build: the bridge's build folder whose Release/pack_sweep.exe sweeps (by default bridge/build).
--quiet: the live run unheard (sound=0; its underruns then say nothing: no sound is made).
Every run has the shell's own brightening of dark places off (dark=0): the references are the game's picture as it is.
Prints one line a check: OK / DIFF and what differs.
"""
import os
import re
import subprocess
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
SHOTS = os.path.join(ROOT, 'out', 'shots')
PACK = os.environ.get('XENO_PACK', os.path.join(ROOT, 'pack'))  # the HD pack folder

# name, game args, reference shot (relative to out/shots), what the log must say
RUNS = [
    ('ff6300_en', 'lang=en ff=6300 script=1:none', 'task3/after_6300.png', [r'"map": 14,', r'"leader_position": \(115, 0, -455\)']),
    # Since task 7 (13.11) the save point's model (a sprite's child) is drawn: 24 more scenery polygons than task 4's 3405.
    ('state_en', 'lang=en state=out/states/test.state script=20:none', 'task7/reference/state_en.png',
     [r'"hd_upload": 3429, "hd_rect": 1,', r'"sprite_pieces": 9, "sprite_hd": 9,', r'"screen_textured": 25, "screen_hd": 5,']),
    ('battle5000_en', 'lang=en map=4 ff=5000 script=1:none', 'battle/battle_5000.png', [r'"program": 2,']),
    ('ff6300_ru', 'ff=6300 script=1:none', None, [r'"map": 14,', r'"leader_position": \(115, 0, -455\)']),
    # Since 15b99a7 (13.11) the minimap's land is opaque and its sea blends, as without the pack: task 6's en_b_1.png differs
    # there only; the reference is that run's shot.
    ('worldmap_en', 'lang=en card=out/saves/usa.srm slot=1 script=150:none,62:down,12:none', 'task7/reference/worldmap_en.png', [r'"program": 3,']),
]


def compare(path, reference):
    a = Image.open(path).convert('RGB')
    b = Image.open(reference).convert('RGB')
    if a.size != b.size:
        return f'size {a.size} vs {b.size}'
    diff = ImageChops.difference(a, b)
    box = diff.getbbox()
    if box is None:
        return None
    data = list(diff.get_flattened_data()) if hasattr(diff, 'get_flattened_data') else list(diff.getdata())
    pixels = sum(1 for p in data if p != (0, 0, 0))
    return f'{pixels} pixels differ, box {box}, max {max(max(p) for p in data)}'


def option(name, default):
    for arg in sys.argv[2:]:
        if arg.startswith(f'--{name}='):
            return os.path.abspath(arg.split('=', 1)[1])
    return default


def main():
    out = os.path.abspath(sys.argv[1])
    game = option('game', os.path.join(ROOT, 'game'))
    build = option('build', os.path.join(ROOT, 'bridge', 'build'))
    os.makedirs(out, exist_ok=True)
    errors = 0
    for name, args, reference, patterns in RUNS:
        shot = os.path.join(out, name + '.png')
        run = subprocess.run([GODOT, '--path', game, '--'] + args.split() + ['dark=0', f'shot={shot}'], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=900, cwd=ROOT)
        log = run.stdout + run.stderr
        open(os.path.join(out, name + '.log'), 'w', encoding='utf-8').write(log)
        shot_line = next((line for line in log.splitlines() if line.startswith('xeno: shot ') and '{' in line), '')
        missing = [p for p in patterns if not re.search(p, shot_line)]
        bad = [line for line in log.splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]
        differs = compare(shot, os.path.join(SHOTS, reference)) if reference and os.path.exists(shot) else None
        ok = not missing and not bad and differs is None and os.path.exists(shot)
        errors += 0 if ok else 1
        print(f'{"OK  " if ok else "DIFF"} {name}: {"shot missing " if not os.path.exists(shot) else ""}'
              f'{"log lacks " + str(missing) + " " if missing else ""}{str(len(bad)) + " script/shader errors " if bad else ""}'
              f'{"pixels: " + differs if differs else ("= " + reference if reference else "")}')
        sys.stdout.flush()
    # pack_sweep of maps 1-2 against the full sweep's rows.
    csv = os.path.join(out, 'ps12.csv')
    if os.path.exists(csv):
        os.remove(csv)
    subprocess.run([os.path.join(build, 'Release', 'pack_sweep.exe'), os.path.join(ROOT, 'weltall', 'Games'), PACK, csv, '1', '2'],
                   capture_output=True, text=True, timeout=900, cwd=ROOT)
    # Maps 1-2 as task 7 left them (map 2 draws its gears since: more scenery than out/sweep/sweep.csv; map 1 the same), and
    # since 15b99a7 map 1's 20 NPC pieces whose picture is a column short "partial" (309 -> 289 wholly from the pack).
    reference = os.path.join(SHOTS, 'task7', 'reference', 'ps12.csv')
    reference_rows = {line.split(',')[0]: line.strip().replace(',"",', ',,') for line in open(reference, encoding='utf-8')}
    # The merged sweep writes an empty error unquoted.
    rows = [line.strip().replace(',"",', ',,') for line in open(csv, encoding='utf-8')][1:]
    same = all(reference_rows.get(row.split(',')[0]) == row for row in rows) and len(rows) == 2
    errors += 0 if same else 1
    print(f'{"OK  " if same else "DIFF"} pack_sweep 1-2: {len(rows)} rows {"= task7/reference/ps12.csv" if same else str(rows)}')
    if '--no-live' not in sys.argv:
        run = subprocess.run([GODOT, '--path', game, '--', 'map=1', 'quit_after=20', 'dark=0'] + (['sound=0'] if '--quiet' in sys.argv else []), capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=300, cwd=ROOT)
        log = run.stdout + run.stderr
        open(os.path.join(out, 'live_map1.log'), 'w', encoding='utf-8').write(log)
        stalls = [line for line in log.splitlines() if 'xeno: stall' in line]
        quit_line = next((line for line in log.splitlines() if 'quit_after' in line), '')
        under = re.search(r'underruns (\d+);', quit_line)
        bad = [line for line in log.splitlines() if 'SCRIPT ERROR' in line or 'SHADER ERROR' in line]
        ok = not stalls and under is not None and under.group(1) == '0' and not bad
        errors += 0 if ok else 1
        print(f'{"OK  " if ok else "DIFF"} live map=1 20 s: {len(stalls)} stall lines, {quit_line[:230]}')
    print('regression:', 'all OK' if errors == 0 else f'{errors} differ')


if __name__ == '__main__':
    main()
