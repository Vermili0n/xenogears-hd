"""Field gears in the hero sprite format (01.11.2026): walking / jumping frames that were never rendered.

On field maps a gear's standing pose comes from its world-map / map sheet (HD), but walking streams the parts of its
hero-format set (disc 1 files 443-459, e.g. 443 = Weltall) - not extracted before, so it stays native. The game
uploads each block either whole or without its last row (dumps 01.11: 70 whole, 77 "h-1"), so both names are
installed.

  python gear_redraw.py jobs --hero weltall [--file 443] [--group g_weltall] [--out ai/redraw/<group>]
  python gear_redraw.py jobs --hero gear444:444,gear445:445,... --out ai/redraw/g_gears      (several gears, one run;
      group of each = g_<name>)
      extract (once) + controls of a part cover of the set (mecha caption, LoRA v2) + README.txt with the pod commands
  python gear_redraw.py install --dir ai/redraw/<group> [--groups g_a,g_b] [--dry]      (RetroArch closed)
      compose (8x, no head pass) -> slice (exact masks, UV compensation) -> seam fill -> BC7: <block>-<pal>.bc7 and
      the h-1 alias for every part. Existing pack files are not overwritten. Written names: <dir>/installed.txt.
"""
import argparse
import csv
import json
import mmap
import os
import shutil
import subprocess
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'xeno_bc7'))
import bc7pack  # noqa: E402
from alias_dump_parts import PACK  # noqa: E402
from extract_heroes import load_sets  # noqa: E402
from render_prod import build_group, cover  # noqa: E402
from seam_fill import fill_interior, frame_interior  # noqa: E402
from xfs import get_file, read_toc  # noqa: E402
from xspr import pixel_blocks  # noqa: E402

FULL = os.path.join(ROOT, 'extracted', 'disc1_full')
USER = os.path.join(ROOT, 'work', 'disc1_user.bin')   # file numbers of the USA disc (the RUS table is shifted)
S = 8
SEC_PER_JOB = 15

README = r"""Field gear {group}: {n_jobs} frames (part cover of {n_frames}), about {eta} min on one L40S. LoRA v2, seed 42.

Pod (HOST / PORT from RunPod; run from the xeno_sprites folder in PowerShell). A fresh pod: setup as in
КАК_ПЕРЕРИСОВАТЬ.md step 3.1, plus the gear LoRA:
   scp -P PORT lora\klein_v2\xeno_klein_v2.safetensors root@HOST:/workspace/lora/

Upload and render:
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r {rel} root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup sh -c 'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/{name}/jobs.json --out redraw/{name}/res --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v2.safetensors; echo RENDER_DONE' > redraw/{name}/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/{name}/infer.log; ls /workspace/redraw/{name}/res/v2 | wc -l"
   (done: RENDER_DONE and {n_jobs} files)

Download, stop the pod:
   scp -P PORT -r root@HOST:/workspace/redraw/{name}/res {rel}\

Install (RetroArch closed):
   python tools\gear_redraw.py install --dir {rel}
"""


def extract(hero, fileno):
    hd = os.path.join(FULL, hero)
    if not os.path.exists(os.path.join(hd, 'layout.json')):
        mp = os.path.join(ROOT, 'work', f'map_{hero}.json')
        json.dump({hero: [fileno]}, open(mp, 'w'))
        subprocess.run([sys.executable, os.path.join(HERE, 'extract_heroes.py'), '--user', USER, '--out', FULL,
                        '--map', mp], check=True)
    return hd


def cmd_jobs(a):
    heroes = [h.split(':') for h in a.hero.split(',')]
    if len(heroes) == 1 and len(heroes[0]) == 1:
        heroes = [(heroes[0][0], str(a.file))]
    multi = len(heroes) > 1
    out = os.path.abspath(a.out or os.path.join(ROOT, 'ai', 'redraw', a.group or f'g_{heroes[0][0]}'))
    if os.path.exists(os.path.join(out, 'jobs.json')):
        sys.exit(f'{out} already has jobs.json')
    for d in ('control', 'boards'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, 'ai', 'prod', 'boards', '_blank.png'), os.path.join(out, 'boards', '_blank.png'))
    jobs, meta, n_frames, groups = [], {}, 0, []
    for hero, fileno in heroes:
        hd = extract(hero, int(fileno))
        lay = json.load(open(os.path.join(hd, 'layout.json')))
        group = f'g_{hero}' if multi or not a.group else a.group
        j, m = build_group((group, hd, cover(lay, sorted(lay), set()), None, 'gear', out))
        jobs += j
        meta.update(m)
        n_frames += sum(len(v['frames']) for v in lay.values())
        groups.append(f'{group} {len(j)}')
    json.dump(jobs, open(os.path.join(out, 'jobs.json'), 'w'), indent=1)
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'), indent=1)
    rel = os.path.relpath(out, ROOT)
    open(os.path.join(out, 'README.txt'), 'w', encoding='utf-8').write(README.format(
        group=', '.join(groups), n_jobs=len(jobs), n_frames=n_frames, eta=max(1, len(jobs) * SEC_PER_JOB // 60),
        rel=rel, name=os.path.basename(out)))
    print(f'{len(jobs)} jobs (cover of {n_frames} frames): {", ".join(groups)} -> {out}')


def block_bytes(index_csv):
    """name (block-pal) -> raw 4bpp bytes of the block, from the disc set the extraction used."""
    rows = list(csv.DictReader(open(index_csv)))
    fh = open(USER, 'rb')
    mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    toc = read_toc(mm)
    sets = {}
    out = {}
    for r in rows:
        key = (int(r['file']), int(r['set']))
        if key not in sets:
            sets[key] = pixel_blocks(load_sets(get_file(mm, toc[key[0]]))[key[1]]['meta'])[2]
        w, h, b8, px = sets[key][int(r['block'])]
        out[r['name']] = (w, h, bytes(px[:(w // 2) * h]))
    return out


def run(cmd):
    print('$', ' '.join(cmd), flush=True)
    if subprocess.run(cmd, cwd=HERE).returncode:
        sys.exit(f'failed: {cmd[1]}')


def write_bc7(path, rgba):
    """Per-process temp name: gears installed in parallel (--groups) can share a part name (same content) - the loser
    of the rename just skips."""
    lv, flags = bc7pack.levels_of(np.ascontiguousarray(rgba.astype(np.uint8)))
    enc, failed, _ = bc7pack.encode_levels(lv)
    if failed:
        return False
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'wb') as f:
        f.write(bc7pack.pack_file(enc, rgba.shape[1], rgba.shape[0], flags))
    try:
        os.replace(tmp, path)
    except OSError:
        os.remove(tmp)
        return False
    return True


def cmd_install(a):
    d = os.path.abspath(a.dir)
    meta = json.load(open(os.path.join(d, 'meta.json')))
    groups = sorted({(m['group'], m['hero_dir']) for m in meta.values()})
    if a.groups:
        groups = [g for g in groups if g[0] in a.groups.split(',')]
    total = []
    for group, hero_dir in groups:
        total.append(install_group(a, d, group, os.path.join(ROOT, hero_dir)))
    print('total pack files written:', sum(total))


def install_group(a, d, group, hd):
    gw = os.path.join(ROOT, 'ai', 'prod_work', group)
    work = os.path.join(gw, 'work')
    os.makedirs(work, exist_ok=True)
    run([sys.executable, 'compose_set.py', '--render', d, '--res', os.path.join(d, 'res', 'v2'), '--work', work,
         '--name', group, '--out-scale', '8', '--no-head'])
    reds = [f[:-8] for f in os.listdir(work) if f.endswith('_red.png')]
    only = ','.join(f"{r.rsplit('_', 1)[0]}:{int(r.rsplit('_', 1)[1])}" for r in reds)
    run([sys.executable, 'batch_redraw.py', 'slice', '--heroes', f'prod_work/{group}', '--hero-dir', hd, '--scale', '8',
         '--exact-mask', '--ring', '0', '--uv-compensate', '--only', only])
    lay = json.load(open(os.path.join(hd, 'layout.json')))
    inner = frame_interior([(v, hd) for v in lay.values()], lambda h, k: os.path.join(h, 'parts'))
    raw = block_bytes(os.path.join(hd, 'index.csv'))
    parts = os.path.join(gw, 'parts')
    done, skipped = [], 0
    for f in sorted(os.listdir(parts)):
        if not f.endswith('.png'):
            continue
        name = f[:-4]
        blk, pal = name.split('-')
        rgba = np.asarray(Image.open(os.path.join(parts, f)).convert('RGBA')).astype(np.int16)
        rgba, _ = fill_interior(rgba, None, S, rgba[..., 3] == 0, inner.get((blk, pal)))
        targets = [(name, rgba)]
        if name in raw:
            w, h, b = raw[name]
            if h > 1:
                alias = '%x' % (zlib.crc32(b[:(w // 2) * (h - 1)]) & 0xffffffff)
                targets.append((f'{alias}-{pal}', rgba[:(h - 1) * S]))
        for tn, img in targets:
            path = os.path.join(PACK, tn + '.bc7')
            if os.path.exists(path) or os.path.exists(os.path.join(PACK, tn + '.png')):
                skipped += 1
                continue
            if a.dry or write_bc7(path, img):
                done.append(tn)
    if not a.dry:
        with open(os.path.join(d, 'installed.txt'), 'a', encoding='utf-8') as f:
            f.writelines(n + '\n' for n in done)
    print(f'{group}: {len(done)} pack files written (parts + h-1 aliases), {skipped} names already there'
          + (' (dry)' if a.dry else ''))
    return len(done)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    j = sub.add_parser('jobs')
    j.add_argument('--hero', required=True, help='name, or name:file,name:file,... for several gears')
    j.add_argument('--file', type=int, default=0, help='disc 1 file number (only for the first extraction)')
    j.add_argument('--group', default='')
    j.add_argument('--out', default='')
    i = sub.add_parser('install')
    i.add_argument('--dir', required=True)
    i.add_argument('--groups', default='', help='g_<name>,... only these groups (parallel runs: one process each)')
    i.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    cmd_jobs(a) if a.cmd == 'jobs' else cmd_install(a)


if __name__ == '__main__':
    main()
