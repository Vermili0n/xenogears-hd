r"""Overwrite a gear's pack files with the pink-fringe fix (gear_pink.py fix), with a backup (15.11.2026).

  python ai\redraw\gaps_1115\pink_install.py <gear> --check      what would be written, nothing changed
  python ai\redraw\gaps_1115\pink_install.py <gear> --install    backup, overwrite both packs, verify byte for byte
  python ai\redraw\gaps_1115\pink_install.py <gear> --undo       the backup copied back into both packs, verified
Only with the user's word for that gear (16.11: gear452 approved; the others wait).
The names: pinkfix\<gear>\files_to_overwrite.txt. Before anything is written, every pack file (RetroArch pack and the
mod's pack) is copied to pinkfix\<gear>\backup\<pack>\ and checked by SHA-256; backup\manifest.json keeps the hashes
(before, after). Undo = --undo (or copy backup\retroarch\* and backup\mod\* back by hand).
"""
import hashlib
import json
import os
import shutil
import sys

from gcommon import HERE, MOD_PACK, PACK

PACKS = {'retroarch': PACK, 'mod': MOD_PACK}


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def main():
    g, mode = sys.argv[1], sys.argv[2]
    d = os.path.join(HERE, 'pinkfix', g)
    names = [n.strip() for n in open(os.path.join(d, 'files_to_overwrite.txt')) if n.strip()]
    bdir = os.path.join(d, 'backup')
    man_path = os.path.join(bdir, 'manifest.json')
    missing = [n for n in names if not os.path.exists(os.path.join(d, n))]
    if missing:
        sys.exit(f'fixed files missing in {d}: {missing[:5]}')
    for key, root in PACKS.items():
        absent = [n for n in names if not os.path.exists(os.path.join(root, n))]
        if absent:
            sys.exit(f'{key}: not in the pack (this tool only overwrites): {absent[:5]}')
    if mode == '--check':
        print(f'{g}: {len(names)} names, all fixed files present, all in both packs')
        return
    if mode == '--undo':
        man = json.load(open(man_path))
        for key, root in PACKS.items():
            for n in names:
                shutil.copyfile(os.path.join(bdir, key, n), os.path.join(root, n))
                if sha(os.path.join(root, n)) != man[key][n]['before']:
                    sys.exit(f'{key} {n}: undo verify failed')
        print(f'{g}: {len(names)} names restored in both packs, verified')
        return
    if os.path.exists(man_path):
        sys.exit(f'{man_path} exists: installed before (undo first, or check by hand)')
    man = {}
    for key, root in PACKS.items():
        os.makedirs(os.path.join(bdir, key), exist_ok=True)
        man[key] = {}
        for n in names:
            src, dst = os.path.join(root, n), os.path.join(bdir, key, n)
            shutil.copyfile(src, dst)
            h = sha(src)
            if sha(dst) != h:
                sys.exit(f'backup verify failed: {key} {n}')
            man[key][n] = {'before': h, 'size_before': os.path.getsize(src)}
    json.dump(man, open(man_path, 'w'), indent=0)
    print(f'backup: {len(names)} x {len(PACKS)} files -> {bdir} (manifest.json)')
    for key, root in PACKS.items():
        for n in names:
            new = os.path.join(d, n)
            shutil.copyfile(new, os.path.join(root, n))
            man[key][n]['after'] = sha(new)
    json.dump(man, open(man_path, 'w'), indent=0)
    bad = [(k, n) for k, root in PACKS.items() for n in names
           if open(os.path.join(root, n), 'rb').read() != open(os.path.join(d, n), 'rb').read()]
    if bad:
        sys.exit(f'verify failed: {bad[:5]}')
    with open(os.path.join(d, 'installed.txt'), 'w') as f:
        f.writelines(n + '\n' for n in names)
    print(f'{g}: {len(names)} files overwritten in both packs, byte for byte equal to the fix; undo: pink_install.py {g} --undo')


if __name__ == '__main__':
    main()
