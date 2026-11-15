"""Semi-automatic ChatGPT session: the user only drags a picture, pastes, presses Enter and downloads.

  for_chatgpt\\СТАРТ.cmd   (= python tools\\gpt_helper.py)
For every character still waiting (status 'можно делать'): builds collage.png, selects it in Explorer, puts the
prompt into the clipboard, waits for the downloaded result in ~/Downloads and files it as chatgpt_sheet.png, then the
same for chatgpt_face.png. Keys in this window: S = skip character, R = redo current step, Q = quit.
"""
import os
import subprocess
import sys
import time

import msvcrt

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gpt_collage import collage  # noqa: E402

D = os.path.join(ROOT, 'for_chatgpt')
DL = os.path.join(os.path.expanduser('~'), 'Downloads')
ORDER = ['citan', 'maria', 'rico', 'emeralda', 'chuchu', 'alice', 'dan', 'timothy', 'sigurd_harcourt', 'kahran_ramsus',
         'karellen', 'myyah_hawwa', 'grahf', 'id', 'jessie_black', 'hammer_xenogears', 'zephyr', 'shakhan', 'maison',
         'dominia_yizkor', 'kelvena', 'seraphita', 'tolone']
SKIP_MARKS = ('approved.txt', 'NOSPRITE.txt', 'FEI.txt', 'NOMATCH.txt', 'NOART.txt', 'HOLD.txt', 'SPRITEONLY.txt')
EXTRA = {
    'sigurd_young': ' This is the same man as a young officer: he has NO eyepatch, both eyes are visible (as in panel A).',
    'sigurd_harcourt': ' He wears a dark eyepatch over his right eye (as in panel A and the sprite in panel C) - keep the eyepatch in every view.',
    'chuchu': ' This character is a small round fluffy creature, not a human: keep its body shape from panel C.',
}

SHEET = ("The attached picture is a reference board with panels labelled A to E. "
         "A: official art of a character from a 90s game (defines the face and hair). {b}"
         "C: the in-game sprite of the same character from several angles (defines the outfit, its colors and the body shape). "
         "D and E: a sheet and a face close-up of ANOTHER character of the same game - copy only their art style "
         "(90s anime look, line weight, cel shading, colors, level of detail, plain light grey background), not their design. "
         "Draw a character turnaround sheet of the character from A and C in exactly the style and layout of D: "
         "three full-body views side by side - front, side (profile) and back, neutral standing pose, the whole figure "
         "visible, plain light grey background. Strong likeness to A{b2}. If A and C disagree, C decides the outfit and "
         "its colors, A decides the face and hair. No text, no labels, no weapons, no extra accessories.{extra}")
FACE = ("Now draw a close-up of the same character's face and shoulders, front three-quarter view, in exactly the style "
        "and layout of panel E. Strong likeness to panel A{b2}. Plain light grey background, no text.")


def queue():
    names = sorted(n for n in os.listdir(D) if os.path.isdir(os.path.join(D, n)))
    names = [n for n in ORDER if n in names] + [n for n in names if n not in ORDER]
    out = []
    for n in names:
        d = os.path.join(D, n)
        has = lambda f: os.path.exists(os.path.join(d, f))  # noqa: E731
        if (has('1_portrait.png') and has('2_sprite_front_side_back.png') and not any(has(m) for m in SKIP_MARKS)
                and not (has('chatgpt_sheet.png') and has('chatgpt_face.png'))):
            out.append(n)
    return out


def clip(text):
    p = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
    p.communicate(text.encode('utf-16le'))


def key():
    if msvcrt.kbhit():
        return msvcrt.getwch().lower()
    return ''


def wait_download(since):
    """New finished image in Downloads -> path; or a key letter."""
    while True:
        k = key()
        if k in ('s', 'r', 'q', 'ы', 'к', 'й'):
            return {'ы': 's', 'к': 'r', 'й': 'q'}.get(k, k)
        for f in os.listdir(DL):
            p = os.path.join(DL, f)
            if (f.lower().endswith(('.png', '.webp', '.jpg', '.jpeg')) and os.path.getmtime(p) > since
                    and not f.endswith('.crdownload')):
                s1 = os.path.getsize(p)
                time.sleep(0.7)
                if os.path.exists(p) and os.path.getsize(p) == s1 and s1 > 10000:
                    return p
        time.sleep(0.5)


def save_as(src, dst):
    Image.open(src).convert('RGB').save(dst)
    os.remove(src)


def main():
    q = queue()
    print(f'Осталось персонажей: {len(q)}. Клавиши в этом окне: S - пропустить, R - переделать шаг, Q - выход.\n')
    for i, slug in enumerate(q, 1):
        d = os.path.join(D, slug)
        has_b = collage(slug)
        b = 'B: the in-game dialogue portrait of the same character (its face must match). ' if has_b else ''
        b2 = ' and B' if has_b else ''
        steps = [('chatgpt_sheet.png', SHEET.format(b=b, b2=b2, extra=EXTRA.get(slug, ''))),
                 ('chatgpt_face.png', FACE.format(b2=b2))]
        print(f'[{i}/{len(q)}] {slug}')
        subprocess.Popen(['explorer', '/select,', os.path.join(d, 'collage.png')])
        while True:
            todo = [(n, t) for n, t in steps if not os.path.exists(os.path.join(d, n))]
            if not todo:
                print('   готово')
                print()
                break
            name, text = todo[0]
            clip(text)
            if name == 'chatgpt_sheet.png':
                print('   1) В ChatGPT: НОВЫЙ чат (Ctrl+Shift+O), перетащи collage.png из открывшейся папки, Ctrl+V, Enter.')
            else:
                print('   2) В том же чате: Ctrl+V, Enter.')
            print('      Когда картинка готова - нажми «Скачать». Жду файл в Загрузках...')
            r = wait_download(time.time())
            if r == 'q':
                print('Выход. Запусти снова - продолжу с этого персонажа.')
                return
            if r == 's':
                print('   пропущен')
                print()
                break
            if r == 'r':
                print('   переделываем шаг')
                continue
            # a wide picture is the turnaround sheet, a square one is the face - whatever order they come in
            with Image.open(r) as im:
                wide = im.width > im.height * 1.2
            got = 'chatgpt_sheet.png' if wide else 'chatgpt_face.png'
            if os.path.exists(os.path.join(d, got)) and got != name:
                got = name
            save_as(r, os.path.join(d, got))
            print(f'   сохранено: {got}')
    print('Все персонажи пройдены. Напиши Claude: «эталоны готовы».')


if __name__ == '__main__':
    main()
