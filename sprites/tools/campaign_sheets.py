"""Overview sheets of finished campaign grids for the user: pod/report/campaign/<group>_<n>.png (16 grids per sheet)."""
import glob
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    font = ImageFont.truetype('arialbd.ttf', 22)
    outs = sorted(glob.glob(os.path.join(ROOT, 'ai', 'campaign', '*', 'out', 'g*.png')))
    jobname = lambda p: os.path.basename(os.path.dirname(os.path.dirname(p)))  # noqa: E731
    groups = {'heroes': [], 'characters': [], 'gears': []}
    for p in outs:
        j = jobname(p)
        groups['heroes' if j.startswith('h_') else 'characters' if j.startswith('c_') else 'gears'].append(p)
    od = os.path.join(ROOT, 'pod', 'report', 'campaign')
    os.makedirs(od, exist_ok=True)
    S, cols = 430, 4
    for g, lst in groups.items():
        for part in range(0, len(lst), 16):
            chunk = lst[part:part + 16]
            sh = Image.new('RGB', (cols * S, -(-len(chunk) // cols) * (S + 30)), (30, 30, 30))
            d = ImageDraw.Draw(sh)
            for k, p in enumerate(chunk):
                im = Image.open(p).convert('RGB').resize((S - 6, S - 6))
                x, y = (k % cols) * S, (k // cols) * (S + 30)
                sh.paste(im, (x + 3, y + 28))
                d.text((x + 4, y + 2), f'{jobname(p)} {os.path.basename(p)[:-4]}'[:36], fill=(255, 230, 0), font=font)
            sh.save(os.path.join(od, f'{g}_{part // 16 + 1}.png'))
    print({k: len(v) for k, v in groups.items()})


if __name__ == '__main__':
    main()
