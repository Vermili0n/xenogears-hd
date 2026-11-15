# The pack's picture format (.bc7) and its converter

The HD pack holds one file per picture, named `<hash>-<palette>.bc7`: a 32-byte header (`XBC7`, version, width,
height, mip levels, alpha flags, raw size, flags) followed by zlib-packed BC7 blocks of every mip level. The format
was made for a patched Beetle PSX HW core (4x less video memory than RGBA); **the stock RetroArch core does not read
it** — it reads PNG files of the same names. The port in this repository reads both, and a `.png` wins over a `.bc7`
of the same name.

## Files

- `xbc7.cpp` — the encoder/decoder library. BC7 is lossy, and the game's shaders need exact values (transparent
  = exactly zero, the blend bit = alpha exactly 255), so every block is encoded, decoded back and checked; a block
  that breaks the rules gets an encoding that keeps them by construction. See the comment at the top of the file.
- `third_party/` — bc7enc and bc7decomp by Richard Geldreich (MIT or public domain, see `third_party/LICENSE`).
- `bc7_to_png.py` — a pack picture to a PNG you can look at and edit.
- `bc7pack.py` — a folder of PNG files to `.bc7` (optional: the port is happy with PNG).

## Building the library (Windows, MSVC; checked 16.11.2026)

From a "x64 Native Tools" prompt, in this folder:

    cl /nologo /O2 /LD /EHsc xbc7.cpp third_party\bc7enc.cpp third_party\bc7decomp.cpp /Fe:xbc7.dll

Python needs `numpy` and `Pillow`.

## Looking at a picture and replacing it

    python bc7_to_png.py <pack>\54cb8504-84598680.bc7 --out work

Edit `work\54cb8504-84598680.png` and put it into the pack folder beside the `.bc7`: the port shows the PNG.
Alpha in the PNG: 0 = transparent, 255 = opaque, anything between = a texel the game blends (the PlayStation's
semi-transparency bit). Keep the size a whole multiple of the original picture's size.

How to learn which file a thing on the screen comes from: press F6 in the game — `frame.txt` of the frame report
names the pack file of every sprite piece and every interface primitive (see `docs/HOW_IT_WORKS.md`).
