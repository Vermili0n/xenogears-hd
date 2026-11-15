"""for_chatgpt/STATUS.txt: per character - which reference files exist and what is still needed.

  python refs_status.py
approved.txt in a character folder = the user accepted its references (written after their OK).
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'for_chatgpt')
ORDER = ['fei', 'elly', 'bart', 'citan', 'billy', 'rico', 'emeralda', 'chuchu', 'maria']


def main():
    lines = ['Статус эталонов (обновляется автоматически). Порядок работы с папкой: см. PROMPT.txt внутри.', '']
    names = ORDER + sorted(n for n in os.listdir(D) if os.path.isdir(os.path.join(D, n)) and n not in ORDER)
    for n in names:
        d = os.path.join(D, n)
        if not os.path.isdir(d):
            continue
        has = lambda f: os.path.exists(os.path.join(d, f))  # noqa: E731
        if has('SPRITEONLY.txt'):
            st = 'по спрайту, без ChatGPT'
        elif has('FEI.txt'):
            st = 'по эталону Фея (ChatGPT не нужен)'
        elif has('NOART.txt') and not has('1_portrait.png'):
            st = 'без арта: рисуем как массовку (ChatGPT не нужен)'
        elif has('NOMATCH.txt'):
            st = 'спрайт в игре не найден - пропусти'
        elif has('NOSPRITE.txt'):
            st = 'пропуск: спрайта нет, эталон не нужен'
        elif has('HOLD.txt'):
            st = 'ПОДОЖДИ: спрайт под вопросом (_CHECK.txt)'
        elif has('approved.txt'):
            st = 'ГОТОВО (эталоны приняты)'
        elif has('chatgpt_sheet.png') and has('chatgpt_face.png'):
            st = 'эталоны есть - жду проверки'
        elif not has('1_portrait.png'):
            st = 'НУЖЕН АРТ: положи 1_portrait.png, потом ChatGPT по PROMPT.txt'
        elif not has('PROMPT.txt'):
            st = 'пакет не собран'
        else:
            st = 'можно делать в ChatGPT (PROMPT.txt)'
        lines.append(f'{n:10s} {st}')
    open(os.path.join(D, 'STATUS.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
