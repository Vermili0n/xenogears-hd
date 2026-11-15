"""Reads field map messages straight from a disc image, independently of the core (read only), and checks text dumps.

  python tools/rus_text.py message <image.bin> <map> <index>         -> the message's codes (hex) and a reading
  python tools/rus_text.py table <image.bin> <map>                   -> the map's table header and every message's size
  python tools/rus_text.py check <image.bin> <core dump .tsv>         -> every field message of text_sweep's dump against this reader
  python tools/rus_text.py window <image.bin> <map> <index> <hex>    -> a window's codes (from the game) against the disc

The disc layout: the game's own file index in the boot executable (tools/rus_files.py); map N = directory 4, file
0xB8 + 2N (1-based); the archive's header holds nine section sizes at 0x10C and offsets at 0x130, each section packed
with the game's LZSS (tools/lzss.py); section 7 is the message table: u16 last index, u16, u16 offsets, then a byte of
width and one of lines per message, then the strings, each ended by 00.

The reading is for people only (the game draws glyphs by code): the USA font's characters, Cyrillic for the Russian
font's own letters 93h-B6h as its glyph pictures show them, and Latin letters read as the Cyrillic they stand for where
the Russian font has no letter of its own (g = д, u = и, n = п, m = т, k = к, y = у, ...).
"""
import csv
import struct
import sys

import lzss
import psx_iso
import rus_files

MAP_DIRECTORY = 4
FIRST_MAP_FILE = 0xB8
SECTION_SIZES = 0x10C
SECTION_OFFSETS = 0x130
MESSAGES = 7

# The USA font's characters for one-byte codes (as Weltall's font.tsv and the glyph pictures show them).
USA = {0x10: ' ', 0x11: '+', 0x12: ',', 0x13: '-', 0x14: '.', 0x15: '/'}
USA.update({0x16 + i: str(i) for i in range(10)})
USA.update({0x20 + i: chr(ord('A') + i) for i in range(26)})
USA.update({0x3A: '[', 0x3B: ']', 0x3C: '='})
USA.update({0x3D + i: chr(ord('a') + i) for i in range(26)})
USA.update({0x57: '!', 0x58: '"', 0x59: '#', 0x5A: '%', 0x5B: '&', 0x5C: "'", 0x5D: '(', 0x5E: ')', 0x5F: ':', 0x60: '?'})
# The Russian font's own letters, read from its glyph pictures (out/rus/font_rus.png).
RUSSIAN_OWN = dict(zip(range(0x93, 0xB7), 'БГДЖИЙЛПУФЦЩШЫЭЮЯбвгжзйлмнфцчщшьыюэя'))
# Latin glyphs the Russian text types for Cyrillic letters that look alike.
LOOKALIKE = dict(zip('ABCEHKMOPTXaceopxyugnmkb34', 'АВСЕНКМОРТХасеорхуидпткьЗЧ'))


def map_file(img, exe_index, number):
    recs, dirs = exe_index
    start = dirs[MAP_DIRECTORY] - 1
    lba, size = recs[start + number - 1]
    return img.read(lba, size) if size > 0 else b''


def message_table(img, exe_index, map_number):
    archive = map_file(img, exe_index, FIRST_MAP_FILE + 2 * map_number)
    size = struct.unpack_from('<I', archive, SECTION_SIZES + 4 * MESSAGES)[0]
    offset = struct.unpack_from('<I', archive, SECTION_OFFSETS + 4 * MESSAGES)[0]
    stream = archive[offset:] + bytes(4096)
    # What the stream holds where the header asks more (77 maps of the Russian disc: one byte more than the stream's).
    return lzss.unpack_prefix(stream, min(size, struct.unpack_from('<I', stream, 0)[0]))


def messages(table):
    last = struct.unpack_from('<H', table, 0)[0]
    count = 0 if last == 0xFFFF else last + 1
    out = []
    for i in range(count):
        at = struct.unpack_from('<H', table, 4 + 2 * i)[0]
        if at >= len(table):
            out.append(None)
            continue
        out.append(table[at:at + message_size(table[at:])])
    return out


# The extended codes' operands (0F kind ...), by kind: as the kernel reads them (wait, speed, close: 1; table: 2; item: 0; ...).
EXTENDED_OPERANDS = [1, 1, 1, 2, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]


def message_size(codes):
    """How many bytes the message at the start of codes takes, its 00 included."""
    i = 0
    while i < len(codes) and codes[i] != 0:
        if codes[i] == 0x0F and i + 1 < len(codes):
            kind = codes[i + 1]
            i += 2 + (EXTENDED_OPERANDS[kind] if kind < len(EXTENDED_OPERANDS) else 0)
        elif codes[i] >= 0xFE:
            i += 2
        else:
            i += 1
    return min(i + 1, len(codes))


def reading(codes, russian=True):
    text = []
    i = 0
    while i < len(codes):
        c = codes[i]
        if c == 0:
            break
        if c == 1:
            text.append('\n')
        elif c == 2:
            text.append('{page}\n')
        elif c == 3:
            text.append('{more}')
        elif c == 0x0F and i + 1 < len(codes):
            kind = codes[i + 1]
            n = EXTENDED_OPERANDS[kind] if kind < len(EXTENDED_OPERANDS) else 0
            text.append('{0F ' + codes[i + 1:i + 2 + n].hex(' ').upper() + '}')
            i += 2 + n
            continue
        elif c >= 0xFE and i + 1 < len(codes):
            text.append('{%02X%02X}' % (c, codes[i + 1]))
            i += 2
            continue
        elif russian and c in RUSSIAN_OWN:
            text.append(RUSSIAN_OWN[c])
        elif c in USA:
            ch = USA[c]
            text.append(LOOKALIKE.get(ch, ch) if russian else ch)
        else:
            text.append('{%02X}' % c)
        i += 1
    return ''.join(text)


def open_disc(path):
    img = psx_iso.Image(path)
    return img, rus_files.read_index(rus_files.boot_exe(img))


def main():
    cmd = sys.argv[1]
    img, exe_index = open_disc(sys.argv[2])
    if cmd == 'message':
        table = message_table(img, exe_index, int(sys.argv[3]))
        codes = messages(table)[int(sys.argv[4])]
        print(codes.hex())
        print(reading(codes))
    elif cmd == 'table':
        table = message_table(img, exe_index, int(sys.argv[3]))
        print('bytes', len(table), 'header', table[:4].hex(), 'messages', len(messages(table)))
    elif cmd == 'window':
        table = message_table(img, exe_index, int(sys.argv[3]))
        codes = messages(table)[int(sys.argv[4])]
        game = bytes.fromhex(sys.argv[5])
        print('equal' if codes == game else 'DIFFERENT', len(codes), len(game))
        print(reading(codes))
    elif cmd == 'check':
        dump = {}
        for row in csv.DictReader(open(sys.argv[3], encoding='utf-8'), delimiter='\t'):
            if row['kind'] == 'field':
                dump.setdefault(int(row['map']), {})[int(row['number'])] = bytes.fromhex(row['codes'])
        equal = different = missing = maps = 0
        notes = []
        for m in range(730):
            try:
                mine = messages(message_table(img, exe_index, m))
            except Exception as error:  # a map the disc holds a placeholder for, or no table
                mine = []
                if m in dump:
                    notes.append(f'map {m}: mine unreadable ({error!r}), core {len(dump[m])}')
                continue
            core = dump.get(m, {})
            maps += 1
            if len(core) != len(mine):
                notes.append(f'map {m}: core {len(core)} messages, mine {len(mine)}')
            for i, codes in enumerate(mine):
                if codes is None:
                    continue
                if i not in core:
                    missing += 1
                elif core[i] == codes:
                    equal += 1
                else:
                    different += 1
                    notes.append(f'map {m} #{i}: different')
        print(f'maps {maps}: messages equal {equal}, different {different}, mine but not the core\'s {missing}')
        for note in notes[:60]:
            print(note)
        print(f'({len(notes)} notes)')


if __name__ == '__main__':
    main()
