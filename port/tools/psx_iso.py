"""Minimal ISO9660 reader for raw MODE2/2352 PlayStation images (read only).

Used to compare the boot executables and files of two discs (USA and the Russian translation).
python tools/psx_iso.py <image.bin> [path ...]   -> lists the root, or writes each file's SHA-1 and size.
"""
import hashlib
import struct
import sys

SECTOR = 2352
DATA = 24  # MODE2 form 1: 12 sync + 4 header + 8 subheader


class Image:
    def __init__(self, path):
        self.f = open(path, 'rb')

    def sector(self, lba):
        self.f.seek(lba * SECTOR + DATA)
        return self.f.read(2048)

    def read(self, lba, size):
        out = bytearray()
        n = (size + 2047) // 2048
        for i in range(n):
            out += self.sector(lba + i)
        return bytes(out[:size])

    def root(self):
        pvd = self.sector(16)
        rec = pvd[156:156 + 34]
        return struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]

    def listdir(self, lba, size):
        data = self.read(lba, size)
        pos = 0
        out = []
        while pos < len(data):
            n = data[pos]
            if n == 0:
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = data[pos:pos + n]
            flba = struct.unpack_from('<I', rec, 2)[0]
            fsize = struct.unpack_from('<I', rec, 10)[0]
            flags = rec[25]
            name = rec[33:33 + rec[32]].decode('ascii', 'replace')
            if name not in ('\x00', '\x01'):
                out.append((name.split(';')[0], flba, fsize, bool(flags & 2)))
            pos += n
        return out

    def find(self, path):
        lba, size = self.root()
        for part in path.split('/'):
            for name, flba, fsize, isdir in self.listdir(lba, size):
                if name.upper() == part.upper():
                    lba, size = flba, fsize
                    break
            else:
                return None
        return lba, size

    def file(self, path):
        hit = self.find(path)
        return None if hit is None else self.read(*hit)


def main():
    img = Image(sys.argv[1])
    if len(sys.argv) == 2:
        for name, lba, size, isdir in img.listdir(*img.root()):
            print(f'{name:20s} lba={lba:7d} size={size:10d} {"dir" if isdir else ""}')
        return
    for path in sys.argv[2:]:
        data = img.file(path)
        if data is None:
            print(path, 'missing')
        else:
            print(path, len(data), hashlib.sha1(data).hexdigest())


if __name__ == '__main__':
    main()
