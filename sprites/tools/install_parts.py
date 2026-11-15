"""Install replacement parts (<tex>-<clut>.png) into the HD pack; same rules as install_and_shoot.ps1 without the game run.

  python install_parts.py --parts ai/fei_prod/parts [--only names.txt]
A pack file that we did not install ourselves is backed up once before it is overwritten.
"""
import argparse
import os
import re
import shutil

PACK = r'<RETROARCH_DRIVE>\RetroArch\system\Xenogears (USA)-texture-replacements'  # SSD since 29.10 (core option HD Texture Folder = System)
BK = r'<DATA_DRIVE>\XenogearsHD_CD1+CD2\backup_replaced_by_sprites'
LOG = os.path.join(BK, '_installed_sprite_parts.txt')
NAME = re.compile(r'^[0-9a-f]{1,8}-[0-9a-f]{1,8}\.png$')  # Beetle writes the CRCs without leading zeros
EXCLUDE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai', 'prod', 'exclude_parts.txt')


def _exclude_lines():
    if not os.path.exists(EXCLUDE):
        return set()
    return {ln.split('#')[0].strip() for ln in open(EXCLUDE)} - {''}


def excluded():
    """Pack names never installed (effect textures in hero sets, see ai/prod/exclude_parts.txt)."""
    return {x for x in _exclude_lines() if not x.startswith('group:')}


def excluded_groups():
    """Production groups never installed at all (garbled sprite pages, lines 'group:<name>')."""
    return {x[6:] for x in _exclude_lines() if x.startswith('group:')}


def group_of(path):
    """ai/prod_work/<group>/stage|parts -> <group> (None for parts folders outside the production work tree)."""
    p = os.path.normpath(os.path.abspath(path)).split(os.sep)
    return p[p.index('prod_work') + 1] if 'prod_work' in p[:-1] else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', required=True)
    ap.add_argument('--only', default='', help='file with part names to install (default: all)')
    a = ap.parse_args()
    g = group_of(a.parts)
    if g in excluded_groups():
        print('installed 0 skipped all: group', g, 'is excluded (ai/prod/exclude_parts.txt)')
        return
    own = set(open(LOG).read().split()) if os.path.exists(LOG) else set()
    only = set(open(a.only).read().split()) if a.only else None
    skip = excluded()
    n = skipped = 0
    with open(LOG, 'a') as log:
        for f in sorted(os.listdir(a.parts)):
            if not NAME.match(f) or (only is not None and f not in only) or f in skip:
                skipped += 1
                continue
            dst = os.path.join(PACK, f)
            if os.path.exists(dst) and f not in own and not os.path.exists(os.path.join(BK, f)):
                shutil.copy2(dst, BK)
            shutil.copyfile(os.path.join(a.parts, f), dst)
            if f not in own:
                log.write(f + '\n')
                own.add(f)
            n += 1
    print('installed', n, 'skipped', skipped)


if __name__ == '__main__':
    main()
