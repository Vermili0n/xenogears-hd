"""Splits string literals too long for MSVC (C2026, 16380 chars a piece) into adjacent literals.

The compiler joins adjacent literals, so the string the program sees is byte for byte the same; the script
checks that by joining the pieces back before writing. Splits only after a space inside a literal.

Usage: python split_long_literals.py <file.cpp> [...]
"""
import re
import sys

LIMIT = 16000
LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def split_literal(body):
    pieces = []
    while len(body) > LIMIT:
        cut = body.rfind(" ", 0, LIMIT) + 1
        if cut <= 0:
            raise ValueError("no space to split at")
        pieces.append(body[:cut])
        body = body[cut:]
    pieces.append(body)
    return pieces


def fix(path):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    changed = 0

    def repl(m):
        nonlocal changed
        body = m.group(1)
        if len(body) <= LIMIT:
            return m.group(0)
        pieces = split_literal(body)
        assert "".join(pieces) == body
        changed += 1
        return '"' + '" "'.join(pieces) + '"'

    new = LITERAL.sub(repl, text)
    # The same text once adjacent literals are joined, as the compiler joins them.
    assert re.sub(r'" "(?=[0-9a-f])', "", new) == text or changed == 0
    if changed:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    print(f"{path}: {changed} literal(s) split")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        fix(p)
