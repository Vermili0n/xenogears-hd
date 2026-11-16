"""The table of pictures found by content (data/sprite_alias_table.csv, FSession::SetAliasTable) from the bridge's
recordings (alias_record=<csv> in the game, XENO_ALIAS_RECORD=<csv> on a headless tool; tools/alias_table_runs.py record):
every line whose picture was found, once (a lookup is its kind's class - an upload, or a region's texels - its size, hash
and palette), the lines with "?" left out. Two recordings giving one lookup two pictures stop it.

  python tools/sprite_alias_table.py <out.csv> <recorded.csv> [...] [--pack=<folder or .zip>] [--keep=<table.csv>]

--pack: each picture must be in that pack (a folder of .bc7/.png, or the published zip holding pack/<name>.bc7);
--keep: the lines of an existing table are kept (hand-written ones too) and the recordings added to them.
The table holds hashes and the pack's file names only: none of the game's texels.
"""
import os
import sys
import zipfile

HEADER = """\
# Xenogears HD: pictures of the HD pack found by content, as hashes only (none of the game's texels).
# The bridge asks this table where the pack has no picture under the name the game draws by (a part the game alters a
# little before upload, a pilot sprite Weltall draws small in a gear), before the content index (which is not published).
# A line: kind,width,height,hash,palette,picture,added
#   kind      upload: <hash>-<palette> is the name the pack lacks (F6's frame.txt lists it, with the upload's size);
#             region-rect, region-piece, port-rect, port-piece: hash is the CRC-32 of the region's texels through its
#             palette (port/bridge/src/xeno_session.h, SetAliasTable)
#   width, height   the size in texels;  palette   the CRC-32 of the palette, as in the pack's file names
#   picture   the pack's file (no .bc7/.png) drawn there
#   added     texels the game draws that the picture's original lacks, "u:v" separated by spaces (drawn from VRAM under it)
# A new line: play with alias_record=<file> on the game's command line. Every lookup the table did not answer is
# written there with picture "?". Put the name of a pack file in place of "?" and add the line here.
"""
KINDS = ('upload', 'region-rect', 'region-piece', 'port-rect', 'port-piece')


def parse(line):
    """(key, fields) of a table line, None for a comment, a blank or a "?" line; raises ValueError on a bad one."""
    text = line.split('#', 1)[0].strip()
    if not text:
        return None
    fields = [f.strip() for f in text.split(',')]
    if len(fields) == 6:
        fields.append('')
    if len(fields) != 7 or fields[0] not in KINDS:
        raise ValueError(line)
    if fields[5] == '?':
        return None
    wide, high, hashed, palette = int(fields[1]), int(fields[2]), int(fields[3], 16), int(fields[4], 16)
    upload, colours = (int(part, 16) for part in fields[5].split('-'))
    fields[3], fields[4], fields[5] = f'{hashed:x}', f'{palette:x}', f'{upload:x}-{colours:x}'
    return ('upload' if fields[0] == 'upload' else 'texels', wide, high, hashed, palette), fields


def read(path, rows, source):
    for number, line in enumerate(open(path, encoding='utf-8-sig'), 1):
        parsed = parse(line)
        if parsed is None:
            continue
        key, fields = parsed
        if key in rows and rows[key][0][5] != fields[5]:
            sys.exit(f'{path}:{number}: {key} gives {fields[5]}, {rows[key][1]} gave {rows[key][0][5]}')
        rows.setdefault(key, (fields, f'{source}:{number}'))


def main():
    out = sys.argv[1]
    sources = [a for a in sys.argv[2:] if not a.startswith('--')]
    pack = next((a.split('=', 1)[1] for a in sys.argv[2:] if a.startswith('--pack=')), None)
    keep = next((a.split('=', 1)[1] for a in sys.argv[2:] if a.startswith('--keep=')), None)
    rows = {}
    if keep:
        read(keep, rows, keep)
    for path in sources:
        read(path, rows, path)
    if pack:
        if pack.lower().endswith('.zip'):
            with zipfile.ZipFile(pack) as archive:
                names = {os.path.splitext(os.path.basename(n))[0] for n in archive.namelist() if n.lower().endswith(('.bc7', '.png'))}
        else:
            names = {os.path.splitext(n)[0] for n in os.listdir(pack) if n.lower().endswith(('.bc7', '.png'))}
        absent = sorted({fields[5] for fields, _ in rows.values() if fields[5] not in names})
        if absent:
            sys.exit(f'{len(absent)} pictures not in {pack}: {absent[:10]}')
    order = sorted(rows.values(), key=lambda r: (KINDS.index(r[0][0]), r[0][4], int(r[0][1]), int(r[0][2]), r[0][3]))
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(HEADER)
        for fields, _ in order:
            f.write(','.join(fields) + '\n')
    by = {k: sum(1 for fields, _ in order if fields[0] == k) for k in KINDS}
    print(f'{out}: {len(order)} lines ({", ".join(f"{k} {n}" for k, n in by.items())}), {os.path.getsize(out)} bytes')


if __name__ == '__main__':
    main()
