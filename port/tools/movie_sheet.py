"""The live shots of a movie run (main.gd at=<s>:snap) on one sheet, each with the movie frame and the video time the
log gave it; with the core's own picture beside (movie_dump f<frame>.ppm) when its folder is given.

    python tools\\movie_sheet.py <game log> <shots folder> <out.png> [movie_dump folder]
"""
import glob
import os
import re
import sys

from PIL import Image, ImageDraw


def main():
    log_path, shots, out = sys.argv[1], sys.argv[2], sys.argv[3]
    dump = sys.argv[4] if len(sys.argv) > 4 else ""
    log = open(log_path, encoding="utf-8", errors="replace").read()
    info = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(
        r"snap \S*/(live_\d+\.png) at [\d.]+ s: .*?movie \S+ \d+ frame (\d+), video ([\d.-]+) s", log)}
    files = sorted(glob.glob(os.path.join(shots, "*.png")))
    width, height = (640, 180) if dump else (320, 180)
    columns = 3 if dump else 5
    rows = (len(files) + columns - 1) // columns
    sheet = Image.new("RGB", (width * columns, (height + 14) * rows), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(files):
        name = os.path.basename(path)
        x, y = (i % columns) * width, (i // columns) * (height + 14)
        shot = Image.open(path).convert("RGB")
        frame, video = info.get(name, ("-", "-"))
        if dump:
            # The video's 4:3 picture as the window shows it (1028 wide, centred), beside the core's picture of that frame.
            left = (shot.width - shot.height * 1028 // 720) // 2
            sheet.paste(shot.crop((left, 0, shot.width - left, shot.height)).resize((257, 180)), (x, y + 14))
            core = os.path.join(dump, "f%05d.ppm" % int(frame)) if frame != "-" else ""
            if core and os.path.exists(core):
                sheet.paste(Image.open(core).convert("RGB").resize((257, 180)), (x + 262, y + 14))
        else:
            sheet.paste(shot.resize((width, height)), (x, y + 14))
        draw.text((x + 3, y + 1), "%s s  frame %s  video %s s" % (name[5:8] + "." + name[8:11], frame, video), fill=(255, 255, 0))
    sheet.save(out)
    print("%d shots, %d with a movie frame" % (len(files), len([f for f in files if os.path.basename(f) in info])))


if __name__ == "__main__":
    main()
