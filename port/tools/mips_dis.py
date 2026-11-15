"""Tiny MIPS R3000 disassembler for reading a few dozen instructions of a PS-X EXE or overlay (read only).

python tools/mips_dis.py <file> <load address hex> <from hex> <count> [header bytes, default 0x800 for an EXE]
"""
import struct
import sys

REG = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
       's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']
I_OPS = {8: 'addi', 9: 'addiu', 10: 'slti', 11: 'sltiu', 12: 'andi', 13: 'ori', 14: 'xori',
         32: 'lb', 33: 'lh', 35: 'lw', 36: 'lbu', 37: 'lhu', 40: 'sb', 41: 'sh', 43: 'sw'}
R_OPS = {0: 'sll', 2: 'srl', 3: 'sra', 4: 'sllv', 6: 'srlv', 7: 'srav', 8: 'jr', 9: 'jalr', 16: 'mfhi', 18: 'mflo',
         24: 'mult', 25: 'multu', 26: 'div', 27: 'divu', 32: 'add', 33: 'addu', 34: 'sub', 35: 'subu', 36: 'and',
         37: 'or', 38: 'xor', 39: 'nor', 42: 'slt', 43: 'sltu'}


def dis(word, pc):
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    sh, fn = (word >> 6) & 31, word & 63
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if word == 0:
        return 'nop'
    if op == 0:
        name = R_OPS.get(fn, f'r?{fn}')
        if fn in (0, 2, 3):
            return f'{name} {REG[rd]},{REG[rt]},{sh}'
        if fn == 8:
            return f'jr {REG[rs]}'
        if fn in (16, 18):
            return f'{name} {REG[rd]}'
        if fn in (24, 25, 26, 27):
            return f'{name} {REG[rs]},{REG[rt]}'
        return f'{name} {REG[rd]},{REG[rs]},{REG[rt]}'
    if op in (2, 3):
        return f'{"j" if op == 2 else "jal"} {(pc & 0xF0000000) | ((word & 0x3FFFFFF) << 2):08x}'
    if op in (4, 5, 6, 7):
        name = {4: 'beq', 5: 'bne', 6: 'blez', 7: 'bgtz'}[op]
        return f'{name} {REG[rs]},{REG[rt]},{pc + 4 + simm * 4:08x}'
    if op == 1:
        return f'{"bltz" if rt == 0 else "bgez" if rt == 1 else "regimm"} {REG[rs]},{pc + 4 + simm * 4:08x}'
    if op == 15:
        return f'lui {REG[rt]},0x{imm:04x}'
    if op in I_OPS:
        name = I_OPS[op]
        if op >= 32:
            return f'{name} {REG[rt]},{simm}({REG[rs]})'
        return f'{name} {REG[rt]},{REG[rs]},{simm if op in (8, 9, 10, 11) else hex(imm)}'
    return f'.word {word:08x}'


def main():
    data = open(sys.argv[1], 'rb').read()
    load = int(sys.argv[2], 16)
    start = int(sys.argv[3], 16)
    count = int(sys.argv[4])
    header = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x800
    for i in range(count):
        pc = start + 4 * i
        off = header + pc - load
        word = struct.unpack_from('<I', data, off)[0]
        print(f'{pc:08x}: {word:08x}  {dis(word, pc)}')


if __name__ == '__main__':
    main()
