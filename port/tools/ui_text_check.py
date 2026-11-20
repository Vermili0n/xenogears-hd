"""Every Russian line of the shell has its English: python tools/ui_text_check.py
Reads game/main.gd and bridge/src/xeno_check.cpp, finds each string literal with Cyrillic outside comments and checks it
has an English pair:
- main.gd: the literal is a key of UI_EN (the dictionary main.gd's _t reads), with an English value;
- xeno_check.cpp: the literal (adjacent literals joined, as the compiler joins them) is the first of an FLine pair,
  {"<Russian>", "<English>"}, the English right after it.
An English value with Cyrillic is a miss too, except the language button's own line, which names both languages.
Prints each miss (file, line, text) and the counts; exit code 1 if there is any miss, else 0."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDSCRIPT = os.path.join(ROOT, 'game', 'main.gd')
CPP = os.path.join(ROOT, 'bridge', 'src', 'xeno_check.cpp')
CYRILLIC = re.compile('[Ѐ-ӿ]')
# English values meant to hold Cyrillic: the panel's language button says "Language / Язык" in both languages.
BILINGUAL = ('Язык',)


def gd_tokens(text):
    """main.gd's string literals and punctuation outside comments: [(kind, value, line)], kind 's' a literal, 'p' a mark."""
    tokens = []
    at, line = 0, 1
    while at < len(text):
        c = text[at]
        if c == '\n':
            line += 1
            at += 1
        elif c == '#':
            while at < len(text) and text[at] != '\n':
                at += 1
        elif text.startswith('"""', at):
            end = text.index('"""', at + 3)
            tokens.append(('s', text[at + 3:end], line))
            line += text.count('\n', at, end + 3)
            at = end + 3
        elif c in '"\'':
            value, start, at = [], line, at + 1
            while text[at] != c:
                if text[at] == '\\':
                    value.append({'n': '\n', 't': '\t', '"': '"', "'": "'", '\\': '\\'}.get(text[at + 1], '\\' + text[at + 1]))
                    at += 2
                    continue
                value.append(text[at])
                at += 1
            at += 1
            tokens.append(('s', ''.join(value), start))
        else:
            if c in ':,{}[]()':
                tokens.append(('p', c, line))
            at += 1
    return tokens


def cpp_tokens(text):
    """xeno_check.cpp's string literals (adjacent ones joined) and punctuation outside comments and character literals."""
    tokens = []
    at, line = 0, 1
    while at < len(text):
        c = text[at]
        if c == '\n':
            line += 1
            at += 1
        elif text.startswith('//', at):
            while at < len(text) and text[at] != '\n':
                at += 1
        elif text.startswith('/*', at):
            end = text.index('*/', at + 2)
            line += text.count('\n', at, end)
            at = end + 2
        elif c == "'":
            at = text.index("'", at + 3 if text[at + 1] == '\\' else at + 2) + 1
        elif c == '"':
            value, start, at = [], line, at + 1
            while text[at] != '"':
                if text[at] == '\\':
                    value.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\', 'r': '\r'}.get(text[at + 1], '\\' + text[at + 1]))
                    at += 2
                    continue
                value.append(text[at])
                at += 1
            at += 1
            if tokens and tokens[-1][0] == 's' and tokens[-1][3]:
                # Joined to the literal just before it (only whitespace between them).
                tokens[-1] = ('s', tokens[-1][1] + ''.join(value), tokens[-1][2], True)
            else:
                tokens.append(('s', ''.join(value), start, True))
            continue
        else:
            if c in ':,{}[]();':
                tokens.append(('p', c, line, False))
            at += 1
        # Anything but whitespace after a literal ends its joining.
        if tokens and tokens[-1][0] == 's' and not c.isspace():
            tokens[-1] = tokens[-1][:3] + (False,)
    return [token[:3] for token in tokens]


def english_has_cyrillic(english):
    for allowed in BILINGUAL:
        english = english.replace(allowed, '')
    return bool(CYRILLIC.search(english))


def check_gdscript(misses):
    text = open(GDSCRIPT, encoding='utf-8').read()
    tokens = gd_tokens(text)
    # UI_EN's pairs: its literals as "key" : "value" from its opening brace to the brace that closes it.
    start = text.index('const UI_EN := {')
    first_line = text.count('\n', 0, start) + 1
    pairs, in_table, depth, keys_at = {}, set(), 0, set()
    index = next(i for i, token in enumerate(tokens) if token[0] == 'p' and token[1] == '{' and token[2] >= first_line)
    for i in range(index, len(tokens)):
        kind, value, line = tokens[i]
        if kind == 'p' and value == '{':
            depth += 1
        elif kind == 'p' and value == '}':
            depth -= 1
            if depth == 0:
                break
        in_table.add(i)
        if kind == 's' and tokens[i + 1][1] == ':' and tokens[i + 2][0] == 's':
            if value in pairs:
                misses.append((GDSCRIPT, line, 'UI_EN has this key twice', value))
            pairs[value] = tokens[i + 2][1]
            keys_at.add(i)
            in_table.add(i + 2)
    count = 0
    for i, (kind, value, line) in enumerate(tokens):
        if kind != 's' or not CYRILLIC.search(value):
            continue
        count += i not in in_table
        if i in in_table:
            if i not in keys_at and english_has_cyrillic(value):
                misses.append((GDSCRIPT, line, 'Cyrillic in an English value of UI_EN', value))
        elif value not in pairs:
            misses.append((GDSCRIPT, line, 'no English in UI_EN', value))
    unused = [key for key in pairs if not any(t[0] == 's' and t[1] == key for i, t in enumerate(tokens) if i not in in_table)]
    return count, len(pairs), unused


def check_cpp(misses):
    tokens = cpp_tokens(open(CPP, encoding='utf-8').read())
    count = 0
    for i, (kind, value, line) in enumerate(tokens):
        if kind != 's' or not CYRILLIC.search(value):
            continue
        if i >= 2 and tokens[i - 1][1] == ',' and tokens[i - 2][0] == 's' and CYRILLIC.search(tokens[i - 2][1]):
            # The English of a pair whose Russian is just before it.
            if english_has_cyrillic(value):
                misses.append((CPP, line, 'its English has Cyrillic', value))
            continue
        count += 1
        if not (tokens[i - 1][1] == '{' and tokens[i + 1][1] == ',' and tokens[i + 2][0] == 's' and tokens[i + 3][1] == '}'):
            misses.append((CPP, line, 'not a {"<Russian>", "<English>"} pair', value))
    return count


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    misses = []
    gd_count, gd_pairs, unused = check_gdscript(misses)
    cpp_count = check_cpp(misses)
    for path, line, why, value in misses:
        print('%s:%d: %s: %r' % (os.path.relpath(path, ROOT), line, why, value))
    for key in unused:
        print('note: UI_EN key not used anywhere in main.gd: %r' % key)
    print('main.gd: %d Russian literals outside UI_EN, %d pairs in UI_EN; xeno_check.cpp: %d Russian literals; misses %d' % (
        gd_count, gd_pairs, cpp_count, len(misses)))
    sys.exit(1 if misses else 0)


if __name__ == '__main__':
    main()
