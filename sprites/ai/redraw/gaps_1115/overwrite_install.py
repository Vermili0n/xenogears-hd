r"""Overwrite pack files from a stage folder, with a backup (16.11.2026; pink_install.py's steps for any staged job).

  python ai\redraw\gaps_1115\overwrite_install.py <inst dir> --check     what would be written, nothing changed
  python ai\redraw\gaps_1115\overwrite_install.py <inst dir> --install   backup, overwrite both packs, verify byte for byte
  python ai\redraw\gaps_1115\overwrite_install.py <inst dir> --undo      the backup copied back into both packs, verified
  (a 3rd argument --stage=<dir> takes the files from there instead of <inst>\stage: prep_overwrite.py's folders)
Only with the user's word for that job (16.11 approved: inst_balthasar_b - Balthasar, board B; Roni's sheet (seed 11);
m_507b56107a, m_9b2c042653).
Names: <inst>\overwrite.txt (install_pod.py finish()), files <inst>\stage\<name>.bc7. Before anything is written, every
pack file (RetroArch pack and the mod's pack) is copied to <inst>\backup\<pack>\ and checked by SHA-256;
backup\manifest.json keeps the hashes (before, after). The job's new names (<inst>\new.txt) are copied too, only where
neither pack has them (install_files), logged in <inst>\installed.txt. Undo: --undo (backup back + new names deleted).
"""
import hashlib
import json
import os
import shutil
import sys

from gcommon import MOD_PACK, PACK, install_files

PACKS = {'retroarch': PACK, 'mod': MOD_PACK}


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def lines(path):
    return [n.strip() for n in open(path) if n.strip()] if os.path.exists(path) else []


def main():
    inst, mode = os.path.abspath(sys.argv[1]), sys.argv[2]
    st = os.path.join(inst, 'stage')
    for arg in sys.argv[3:]:
        if arg.startswith('--stage='):
            st = os.path.abspath(arg.split('=', 1)[1])
    names = [n + '.bc7' for n in lines(os.path.join(inst, 'overwrite.txt'))]
    new = lines(os.path.join(inst, 'new.txt'))
    bdir = os.path.join(inst, 'backup')
    man_path = os.path.join(bdir, 'manifest.json')
    missing = [n for n in names if not os.path.exists(os.path.join(st, n))]
    if missing and mode != '--undo':
        sys.exit(f'staged files missing: {missing[:5]}')
    if mode == '--undo':
        man = json.load(open(man_path))
        for key, root in PACKS.items():
            for n in names:
                shutil.copyfile(os.path.join(bdir, key, n), os.path.join(root, n))
                if sha(os.path.join(root, n)) != man[key][n]['before']:
                    sys.exit(f'{key} {n}: undo verify failed')
        for n in lines(os.path.join(inst, 'installed.txt')):
            for root in PACKS.values():
                if os.path.exists(os.path.join(root, n)):
                    os.remove(os.path.join(root, n))
        print(f'{len(names)} names restored in both packs, verified; new names removed')
        return
    for key, root in PACKS.items():
        absent = [n for n in names if not os.path.exists(os.path.join(root, n))]
        if absent:
            sys.exit(f'{key}: not in the pack (this tool only overwrites): {absent[:5]}')
    if mode == '--check':
        print(f'{len(names)} overwrites, {len(new)} new names; all staged, all overwrites present in both packs')
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
            shutil.copyfile(os.path.join(st, n), os.path.join(root, n))
            man[key][n]['after'] = sha(os.path.join(st, n))
    json.dump(man, open(man_path, 'w'), indent=0)
    done = install_files(st, new, os.path.join(inst, 'installed.txt'))
    bad = [(k, n) for k, root in PACKS.items() for n in names + done
           if open(os.path.join(root, n), 'rb').read() != open(os.path.join(st, n), 'rb').read()]
    if bad:
        sys.exit(f'verify failed: {bad[:5]}')
    with open(os.path.join(inst, 'overwritten.txt'), 'w') as f:
        f.writelines(n + '\n' for n in names)
    print(f'{len(names)} files overwritten + {len(done)} new in both packs, byte for byte equal to the stage; '
          f'undo: overwrite_install.py {inst} --undo')


if __name__ == '__main__':
    main()
