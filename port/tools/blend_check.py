"""Checks the 2D layer's blends against the PS1 GPU's arithmetic, by numbers.

For each scene (a game state reached by command-line arguments) and each chosen run of its 2D layer (the runs main.gd
prints as "xeno: flat runs"), four shots of the same frame, all made by one run of the game (main.gd, checks=):
  B  - the frame with the 2D layer's runs before this one (k = 0: no 2D layer at all),
  R  - the frame with this run too,
  Fb, Fw - this run alone, its blending pixels drawn opaque as their F, over a black and over a white clear colour
       without the 3D world; a pixel the run blends at is one where Fb == Fw.
At sample pixels the run blends, the PS1's result is computed from B and F in its 5 bits (b = B * 31 / 255, f likewise;
average (b >> 1) + (f >> 1), add min(31, b + f), subtract max(0, b - f), add a quarter min(31, b + (f >> 2))) and
compared with R in 5 bits; and in 8 bits with the same formulas unrounded. Passes when every channel is within one
step of 31 (5 bits) and within 255 / 31 (8 bits).

Usage: python tools/blend_check.py [--per-run N] [--out out/blend_check.txt]
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, 'tools', 'godot', 'Godot_v4.7.2-stable_win64_console.exe')
WORK = os.path.join(ROOT, 'out', 'blend_check')
MODES = {1: 'average', 2: 'add', 3: 'subtract', 4: 'add quarter'}
# Scenes: name, arguments, runs to check (None: the first run of each blending mode, and the last one).
SCENES = [
    ('dialog over the field', 'map=4 ff=6134 script=640:none', None),
    ('field menu (shade, boxes)', 'state=out/states/test.state script=40:none,2:square,100:none', None),
    ('chapter card (band, letters)', 'map=4 ff=6950 script=1:none', None),
    ('title with its menu', 'boot=1 script=150:none,1:cross,80:none,1:cross,60:none', None),
    ('battle HUD window', 'map=4 ff=4940 script=1:none', None),
    # B + F/4 was met nowhere on the paths scanned (the new game to frame 9000, the boot, the field menu): the menu's
    # averaging boxes drawn as adding a quarter (main.gd as_blend=1:4) check that mode's arithmetic.
    ('field menu, its boxes as add a quarter', 'state=out/states/test.state script=40:none,2:square,100:none as_blend=1:4', None),
]
RUN_PATTERN = re.compile(r'\[(\d), "([^"]*)", (\d), (\w+), Vector4\(([^)]*)\), (\w+)\]')


def shoot(args, path):
    """One shot of the game with these arguments; the runs it drew."""
    command = [GODOT, '--path', os.path.join(ROOT, 'game'), '--'] + args.split() + ['shot=' + path]
    run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
    lines = [line for line in run.stdout.splitlines() if line.startswith('xeno: flat runs')]
    if not os.path.exists(path):
        raise RuntimeError('no shot: ' + ' '.join(command) + '\n' + run.stdout[-2000:] + run.stderr[-2000:])
    return [(int(m[0]), m[1]) for m in RUN_PATTERN.findall(lines[-1])] if lines else []


def load(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(np.int64)


def ps1(mode, b, f):
    """The GPU's blend in its 5 bits, clamped."""
    if mode == 1:
        return (b >> 1) + (f >> 1)
    if mode == 2:
        return np.minimum(31, b + f)
    if mode == 3:
        return np.maximum(0, b - f)
    return np.minimum(31, b + (f >> 2))


def exact(mode, b, f):
    """The same blend on 8-bit values, unrounded."""
    if mode == 1:
        return (b + f) / 2.0
    if mode == 2:
        return np.minimum(255.0, b + f)
    if mode == 3:
        return np.maximum(0.0, b - f)
    return np.minimum(255.0, b + f / 4.0)


def to5(values):
    return np.rint(values * 31.0 / 255.0).astype(np.int64)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--per-run', type=int, default=8, help='sample pixels per run')
    parser.add_argument('--out', default=os.path.join(ROOT, 'out', 'blend_check.txt'))
    options = parser.parse_args()
    os.makedirs(WORK, exist_ok=True)
    lines = []
    total = {'samples': 0, 'fail': 0, 'max5': 0, 'max8': 0.0}
    by_mode = {}

    def say(text):
        print(text)
        lines.append(text)

    for index, (name, args, chosen) in enumerate(SCENES):
        full = os.path.join(WORK, f's{index}_full.png')
        runs = shoot(args, full)
        say(f'== {name}: {args}; runs (blend) {[r[0] for r in runs]}')
        if chosen is None:
            chosen = []
            for mode in MODES:
                found = [k for k, r in enumerate(runs) if r[0] == mode]
                if found:
                    chosen.append(found[0])
                    if found[-1] != found[0]:
                        chosen.append(found[-1])
        chosen = sorted(set(chosen))
        # One run of the game makes every check's shots of the same frame (main.gd, checks=).
        checked = os.path.join(WORK, f's{index}.png')
        if chosen:
            shoot(f'{args} checks={"+".join(str(k) for k in chosen)}', checked)
        for k in chosen:
            mode = runs[k][0]
            b_path, r_path = os.path.join(WORK, f's{index}_r{k}_B.png'), os.path.join(WORK, f's{index}_r{k}_R.png')
            fb_path, fw_path = os.path.join(WORK, f's{index}_r{k}_Fb.png'), os.path.join(WORK, f's{index}_r{k}_Fw.png')
            B, R, Fb, Fw = load(b_path), load(r_path), load(fb_path), load(fw_path)
            covered = np.all(Fb == Fw, axis=2)
            # Away from the run's edges: the pixel and its 8 neighbours all covered.
            inner = covered.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    inner &= np.roll(np.roll(covered, dy, axis=0), dx, axis=1)
            ys, xs = np.nonzero(inner)
            if len(ys) == 0:
                say(f'  run {k} ({MODES[mode]}, {runs[k][1][-24:] or "VRAM"}): no pixel blends')
                continue
            # Most samples where the result is not simply clamped (it then tells the blend's arithmetic), the rest anywhere.
            b_all, f_all = B[ys, xs].astype(float), Fb[ys, xs].astype(float)
            raw = {1: (b_all + f_all) / 2.0, 2: b_all + f_all, 3: b_all - f_all, 4: b_all + f_all / 4.0}[mode]
            telling = np.nonzero(np.any((raw > 0.0) & (raw < 255.0), axis=1))[0]
            other = np.setdiff1d(np.arange(len(ys)), telling)
            count_telling = min(len(telling), options.per_run - min(len(other), options.per_run // 4))
            picks = np.concatenate([telling[np.linspace(0, len(telling) - 1, num=count_telling).astype(int)] if count_telling else np.array([], int),
                                    other[np.linspace(0, len(other) - 1, num=min(len(other), options.per_run - count_telling)).astype(int)] if len(other) else np.array([], int)])
            worst5, worst8, fails = 0, 0.0, 0
            for pick in picks:
                y, x = ys[pick], xs[pick]
                b, f, r = B[y, x], Fb[y, x], R[y, x]
                want5 = ps1(mode, to5(b), to5(f))
                got5 = to5(r)
                d5 = int(np.abs(got5 - want5).max())
                d8 = float(np.abs(r - exact(mode, b.astype(float), f.astype(float))).max())
                worst5, worst8 = max(worst5, d5), max(worst8, d8)
                bad = d5 > 1 or d8 > 255.0 / 31.0
                fails += bad
                ints = lambda values: tuple(int(v) for v in values)
                say(f'  run {k} {MODES[mode]:11s} px ({x:4d},{y:3d}) B {ints(b)} F {ints(f)} -> PS1 {ints(want5)} got {ints(got5)} '
                    f'(8-bit {ints(r)} vs {ints(np.rint(exact(mode, b.astype(float), f.astype(float))))}) {"FAIL" if bad else "ok"}')
            say(f'  run {k} ({MODES[mode]}): {len(picks)} samples ({count_telling} unclamped) of {len(ys)} blending pixels, worst {worst5} step(s) of 31, '
                f'{worst8:.1f} of 255, {fails} failing')
            total['samples'] += len(picks)
            total['fail'] += fails
            total['max5'] = max(total['max5'], worst5)
            total['max8'] = max(total['max8'], worst8)
            mode_total = by_mode.setdefault(MODES[mode], [0, 0])
            mode_total[0] += len(picks)
            mode_total[1] += fails
    say(f'TOTAL: {total["samples"]} samples, {total["fail"]} failing; worst {total["max5"]} step(s) of 31, {total["max8"]:.1f} of 255; '
        f'by mode (samples, failing): {by_mode}')
    with open(options.out, 'w', encoding='utf-8') as out:
        out.write('\n'.join(lines) + '\n')
    return 1 if total['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
