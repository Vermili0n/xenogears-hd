r"""Bart 430_0:70, the head close-up of seed 11 with the eyepatch moved to the other eye (14.11.2026, the user's remark:
"the frame is excellent but the patch is on the wrong eye").

  python ai\redraw\zero_block\bart_eye\paint_bart.py
The sprite has the patch on the far eye (the right one in the picture) and the open eye nearer the middle; the render
has them the other way round. As tools/eyepatch_paint_jobs.py does: the patch and the open eye are painted roughly by
hand at their places on the render, and the LoRA only refines the masked area (pod/repaint_pod.py, strength < 1).
Writes base.png (painted), mask.png (white = redraw), jobs.json, run.sh and preview.png beside this file.
"""
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
JOB = os.path.dirname(HERE)
NAME = 'h_bart__430_0_070__head'
SEEDS = [7, 11, 23, 31]
STRENGTHS = [0.55, 0.68]
CAP = ('close-up of the head: redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the '
       'second image, same pose and silhouette, flat magenta background, he wears a black eyepatch over one eye exactly '
       'where the sprite shows the dark patch, his open eye is blue')
NEG = 'goggles, visor, sunglasses, mask, both eyes covered, red eyes, green eyes, brown eyes'
PATCH = (44, 44, 50)
LINE = (20, 14, 12)
# The old patch (512 canvas): its dark texels inside this outline become skin.
OLD_PATCH = [(244, 228), (244, 200), (258, 188), (272, 178), (284, 174), (300, 176), (301, 228)]
# The new patch over the far eye, joined to the headband above it.
NEW_PATCH = [(299, 172), (326, 170), (328, 196), (322, 211), (308, 213), (299, 202)]
MASK = [(238, 232), (238, 196), (254, 180), (270, 168), (296, 164), (332, 164), (334, 216), (310, 222), (304, 232)]


def main():
    base = Image.open(os.path.join(JOB, 'res_11', 'v4', NAME + '.png')).convert('RGB')
    skin = base.getpixel((272, 232))
    shade = tuple(int(c * 0.82) for c in skin)
    old = Image.new('L', base.size, 0)
    ImageDraw.Draw(old).polygon(OLD_PATCH, fill=255)
    px, om = base.load(), old.load()
    for y in range(170, 230):
        for x in range(240, 304):
            r, g, b = px[x, y]
            # the patch's grey (not the hair's yellow, not the skin): dark and colourless
            if om[x, y] and max(r, g, b) < 110 and max(r, g, b) - min(r, g, b) < 40:
                px[x, y] = skin
    d = ImageDraw.Draw(base)
    # the open eye: brow, upper lid, white, blue iris, pupil
    d.line([(260, 187), (274, 182), (290, 183)], fill=LINE, width=3)
    d.polygon([(263, 199), (270, 193), (282, 192), (291, 197), (284, 204), (270, 205)], fill=(245, 245, 245))
    d.line([(262, 199), (270, 192), (283, 191), (292, 197)], fill=LINE, width=3)
    d.ellipse([272, 192, 284, 205], fill=(52, 84, 170))
    d.ellipse([276, 196, 281, 202], fill=(14, 20, 50))
    d.line([(268, 207), (284, 206)], fill=shade, width=2)
    # the patch over the far eye
    d.polygon(NEW_PATCH, fill=PATCH, outline=LINE)
    base.save(os.path.join(HERE, 'base.png'))
    mask = Image.new('L', base.size, 0)
    ImageDraw.Draw(mask).polygon(MASK, fill=255)
    mask.save(os.path.join(HERE, 'mask.png'))
    jobs = [{'name': NAME, 'control': f'../control/{NAME}.png', 'ref': '../boards/bart.png', 'prompt': CAP, 'base': 'base.png',
             'mask': 'mask.png', 'neg': NEG}]
    json.dump(jobs, open(os.path.join(HERE, 'jobs.json'), 'w'), indent=1)
    run = ['#!/usr/bin/env bash', '# Every seed at every strength. Resumable: finished files are skipped.', 'cd /workspace']
    for st in STRENGTHS:
        tag = str(st).replace('.', '')
        run += ['for s in ' + ' '.join(str(s) for s in SEEDS) + '; do',
                f'  HF_HOME=/workspace/hf python repaint_pod.py --jobs redraw/zero_block/bart_eye/jobs.json'
                f' --out redraw/zero_block/bart_eye/res_{tag}_$s --seed $s --strength {st} --lora lora/xeno_klein_v4.safetensors',
                'done']
    run += ['echo RENDER_DONE', '']
    open(os.path.join(HERE, 'run.sh'), 'w', encoding='utf-8', newline='\n').write('\n'.join(run))
    box = (200, 110, 392, 270)
    orig = Image.open(os.path.join(JOB, 'res_11', 'v4', NAME + '.png')).convert('RGB')
    tint = Image.composite(Image.new('RGB', base.size, (255, 255, 255)), base, mask.point(lambda v: v // 3))
    sheet = Image.new('RGB', (192 * 3 * 3, 160 * 3))
    for k, im in enumerate((orig, base, tint)):
        sheet.paste(im.crop(box).resize((192 * 3, 160 * 3), Image.LANCZOS), (192 * 3 * k, 0))
    sheet.save(os.path.join(HERE, 'preview.png'))
    print('skin', skin, 'jobs', len(jobs), 'runs', len(SEEDS) * len(STRENGTHS))


if __name__ == '__main__':
    main()
