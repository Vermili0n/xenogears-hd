"""The headless runs that fill and measure the table of pictures found by content (data/sprite_alias_table.csv), one
after another (one heavy process at a time), in one mode:

  python tools/alias_table_runs.py <out folder> <mode> [--table=<csv>] [--label=<name>] [--user=<folder>] [run ...]
  python tools/alias_table_runs.py <out folder> --sum [label ...]

mode: none (no lookup by content), table (the table only, --table=), index (the index only,
out/alias/sprite_alias_index.bin), record (the index, each lookup written into <label>/<run>.record.csv as a line of
the table, and XENO_ALIAS_REPORT into <label>/<run>.report.csv for tools/sprite_alias_sheet.py). The run's files go
into <out folder>/<label> (by default the mode's name).
runs (all by default):
  newgame  pack_sweep, every field map entered from a new game (90 frames each)
  s32      pack_sweep, every field map entered from story point 32 (out/sweep_sprites/hd/s32_map23.state, Russian disc)
  story    story_states over the story walk's states (out/states/story, 120 frames each)
  user     story_states over a folder of copies of the player's states (--user=, Russian disc, 120 frames each)
  heroes   sprite_coverage: every frame of the 11 party sprite sets, own palettes and the story walk's
--sum prints, per label, each run's sprite pieces wholly from the pack / partly / from VRAM, the 2D layer's, the hero
frames wholly HD (own palettes) and the states that did not load.
"""
import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, 'bridge', 'build', 'Release')
GAMES = os.path.join(ROOT, 'weltall', 'Games')
RUSSIAN = os.path.join(ROOT, 'games_ru', 'xenogears_rus_xz.CUE')
PACK = os.environ.get('XENO_PACK', os.path.join(ROOT, 'pack'))  # the HD pack folder
INDEX = os.path.join(ROOT, 'out', 'alias', 'sprite_alias_index.bin')
S32 = os.path.join(ROOT, 'out', 'sweep_sprites', 'hd', 's32_map23.state')
STORY = os.path.join(ROOT, 'out', 'states', 'story')
PALETTES = os.path.join(ROOT, 'out', 'sweep_sprites', 'walk', 'sprite_palettes.csv')
RUNS = ['newgame', 's32', 'story', 'user', 'heroes']


def option(name, default=None):
    for arg in sys.argv[3:]:
        if arg.startswith(f'--{name}='):
            return arg.split('=', 1)[1]
    return default


def run(out, mode, name, user):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('XENO_ALIAS', 'XENO_TRANSLATION', 'XENO_SWEEP_STATE'))}
    if mode in ('index', 'record'):
        env['XENO_ALIAS'] = INDEX
    if mode == 'table':
        env['XENO_ALIAS_TABLE'] = os.path.abspath(option('table'))
    if mode == 'record':
        env['XENO_ALIAS_RECORD'] = os.path.join(out, f'{name}.record.csv')
        env['XENO_ALIAS_REPORT'] = os.path.join(out, f'{name}.report.csv')
    if name == 'newgame':
        command = [os.path.join(RELEASE, 'pack_sweep.exe'), GAMES, PACK, os.path.join(out, 'newgame.csv')]
    elif name == 's32':
        env['XENO_SWEEP_STATE'] = S32
        env['XENO_TRANSLATION'] = RUSSIAN
        command = [os.path.join(RELEASE, 'pack_sweep.exe'), GAMES, PACK, os.path.join(out, 's32.csv')]
    elif name == 'story':
        command = [os.path.join(RELEASE, 'story_states.exe'), GAMES, PACK, STORY, os.path.join(out, 'story.csv')]
    elif name == 'user':
        env['XENO_TRANSLATION'] = RUSSIAN
        command = [os.path.join(RELEASE, 'story_states.exe'), GAMES, PACK, user, os.path.join(out, 'user.csv')]
    else:
        command = [os.path.join(RELEASE, 'sprite_coverage.exe'), GAMES, PACK, os.path.join(out, 'heroes'), '0', '10', PALETTES]
        os.makedirs(os.path.join(out, 'heroes'), exist_ok=True)
    for made in (os.path.join(out, f'{name}.csv'), os.path.join(out, f'{name}.record.csv'), os.path.join(out, f'{name}.report.csv'),
                 os.path.join(out, f'{name}.csv.missing.txt')):
        if os.path.exists(made):
            os.remove(made)
    with open(os.path.join(out, f'{name}.log'), 'w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    print(f'{mode} {name}: exit {result.returncode}', flush=True)


def ints(row, *names):
    return [int(row[n] or 0) for n in names]


def summary(folder):
    lines = []
    for name in RUNS:
        path = os.path.join(folder, f'{name}.csv')
        if name == 'heroes':
            heroes = os.path.join(folder, 'heroes')
            if not os.path.isdir(heroes):
                continue
            whole = frames = 0
            for c in range(11):
                for row in csv.DictReader(open(os.path.join(heroes, f'frames_{c}.csv'))):
                    if row['palette_variant'] == 'own':
                        frames += 1
                        whole += row['verdict'] == 'hd'
            lines.append(f'  heroes: frames wholly HD {whole} of {frames}')
            continue
        if not os.path.exists(path):
            continue
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        total = [0] * 6
        for row in rows:
            for i, value in enumerate(ints(row, 'sprite_pieces', 'sprite_hd', 'sprite_partial', 'sprite_vram', 'screen_textured', 'screen_hd')):
                total[i] += value
        failed = sum(1 for row in rows if row.get('load_error'))
        lines.append(f'  {name}: {len(rows)} rows{f" ({failed} not loaded)" if name in ("story", "user") else ""}; sprite pieces {total[0]}: '
                     f'wholly from the pack {total[1]}, partly {total[2]}, from VRAM {total[3]}; 2D textured {total[4]}, HD {total[5]}')
    return lines


def main():
    out = os.path.abspath(sys.argv[1])
    if sys.argv[2] == '--sum':
        labels = sys.argv[3:] or sorted(d for d in os.listdir(out) if os.path.isdir(os.path.join(out, d)))
        for label in labels:
            print(label)
            print('\n'.join(summary(os.path.join(out, label))))
        return
    mode = sys.argv[2]
    if mode not in ('none', 'table', 'index', 'record') or (mode == 'table' and not option('table')):
        sys.exit(__doc__)
    folder = os.path.join(out, option('label', mode))
    os.makedirs(folder, exist_ok=True)
    names = [a for a in sys.argv[3:] if not a.startswith('--')] or RUNS
    user = option('user')
    for name in names:
        if name == 'user' and not user:
            print('user: no --user folder, skipped')
            continue
        run(folder, mode, name, user and os.path.abspath(user))


if __name__ == '__main__':
    main()
