"""The mod folder for another PC, built from the development tree by one command:

    python tools\\make_dist.py [out folder]          (default: dist\\XenogearsHD)

What goes in (nothing of it into git: dist/ is ignored):
  Play.cmd, ПРОЧТИ.txt, README.txt (the same in English), Games\\<notes>
              from mod\\ (the batch kept ASCII and CRLF, the texts UTF-8 with a BOM, CRLF)
  engine\\    Godot 4.7.2 (tools\\godot, its _sc_ marker: the editor's import keeps its data beside it) and xeno_check.exe
  game\\      the Godot project without its .godot cache (the batch imports it on the first run) and bin\\xeno_bridge.dll
  data\\      out\\alias\\sprite_alias_index.bin (the pack's pictures found by content)
  movies\\    out\\movies (HD replacements of the game's movies, tools\\make_dist.py makes 13.ogv when it is missing)
  pack\\      the HD pack, robocopy /MIR from XENO_PACK (default: pack\\ beside game\\; read only), log in out\\dist_logs\\pack_robocopy.log
Environment: XENO_PACK=<the HD pack folder>, XENO_OPENING_VIDEO=<the HD opening .mp4> (unset and no out\\movies\\usa.disc1\\13.ogv:
movies\\ is left out), FFMPEG=<ffmpeg.exe> (default: ffmpeg from PATH).
  saves\\, states\\, reports\\ (F6's frame reports) empty;  LICENSES\\ Weltall, Godot (and its third parties), godot-cpp, bc7decomp
Refuses to finish if the folder holds a disc image, a memory card, a save, a state or a frame report (the user's own never go in).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GODOT = ROOT / "tools" / "godot"
GODOT_EXE = "Godot_v4.7.2-stable_win64.exe"
GODOT_CONSOLE = "Godot_v4.7.2-stable_win64_console.exe"
PACK = Path(os.environ.get("XENO_PACK", str(ROOT / "pack")))
OPENING = Path(os.environ["XENO_OPENING_VIDEO"]) if os.environ.get("XENO_OPENING_VIDEO") else None
# The opening's HD video as the game plays it: the 4:3 picture of the movie (its 320 x 224 at 1028 x 720, the video's
# pillarbox cropped: ffmpeg cropdetect, checked against the core's pictures), every frame kept, Theora, no sound (the
# game's own sound plays), every frame a key frame: this ffmpeg's libtheora writes inter frames that neither Godot's Theora
# player nor ffmpeg decode cleanly (ffmpeg: "error in unpack_block_qpis"; Godot: block garbage that spreads until the
# next key frame), whatever the size, quality or speed level; key frames alone decode clean (0 errors), 362 MB.
OPENING_COMMAND = [os.environ.get("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(OPENING), "-an",
                   "-fps_mode", "passthrough", "-vf", "crop=1028:720:126:0", "-c:v", "libtheora", "-q:v", "8", "-g", "1"]
GAME_FILES = ["project.godot", "main.gd", "main.gd.uid", "main.tscn", "xeno.gdextension", "xeno.gdextension.uid"]
FORBIDDEN = {".bin", ".cue", ".iso", ".img", ".chd", ".ecm", ".pbp", ".mdf", ".mds", ".nrg", ".cdi", ".srm", ".mcr", ".mcd",
             ".state", ".sav", ".7z", ".zip", ".rar"}


def text_file(source: Path, target: Path, bom: bool, ascii_only: bool = False) -> None:
    text = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    if ascii_only:
        text.encode("ascii")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def size_of(path: Path) -> tuple:
    if path.is_file():
        return path.stat().st_size, 1
    total = files = 0
    for folder, _, names in os.walk(path):
        for name in names:
            total += os.path.getsize(os.path.join(folder, name))
            files += 1
    return total, files


def main() -> None:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "XenogearsHD"
    logs = ROOT / "out" / "dist_logs"
    logs.mkdir(parents=True, exist_ok=True)
    for kept in ("saves", "states", "reports"):
        if (out / kept).exists() and any((out / kept).iterdir()):
            sys.exit(f"{out / kept} holds files (someone played from this folder?): move them away first")
    # What a run of the folder made (the import cache, the logs, Godot's editor data) never ships.
    for made in (out / "game" / ".godot", out / "logs", out / "engine" / "editor_data"):
        if made.exists():
            shutil.rmtree(made)

    text_file(ROOT / "mod" / "Play.cmd", out / "Play.cmd", bom=False, ascii_only=True)
    text_file(ROOT / "mod" / "ПРОЧТИ.txt", out / "ПРОЧТИ.txt", bom=True)
    text_file(ROOT / "mod" / "README.txt", out / "README.txt", bom=True)
    for note in (ROOT / "mod" / "Games").iterdir():
        text_file(note, out / "Games" / note.name, bom=True)

    for name in (GODOT_EXE, GODOT_CONSOLE):
        copy(GODOT / name, out / "engine" / name)
    (out / "engine" / "_sc_").write_bytes(b"")
    copy(ROOT / "bridge" / "build" / "Release" / "xeno_check.exe", out / "engine" / "xeno_check.exe")

    game = out / "game"
    if game.exists():
        shutil.rmtree(game)
    for name in GAME_FILES:
        copy(ROOT / "game" / name, game / name)
    shutil.copytree(ROOT / "game" / "shaders", game / "shaders")
    copy(ROOT / "game" / "bin" / "xeno_bridge.dll", game / "bin" / "xeno_bridge.dll")

    copy(ROOT / "out" / "alias" / "sprite_alias_index.bin", out / "data" / "sprite_alias_index.bin")

    opening = ROOT / "out" / "movies" / "usa.disc1" / "13.ogv"
    if not opening.exists() and OPENING is None:
        print("no HD opening video (out\\movies\\usa.disc1\\13.ogv missing, XENO_OPENING_VIDEO not set): movies\\ left out")
    else:
        build_movies(opening, out)

    # The pack: robocopy (/MIR: the folder made the source's copy, only what differs copied), its log beside the others.
    if not PACK.is_dir():
        sys.exit(f"no HD pack at {PACK}: set XENO_PACK=<the pack folder>")
    result = subprocess.run(["robocopy", str(PACK), str(out / "pack"), "/MIR", "/COPY:DAT", "/DCOPY:T", "/R:1", "/W:1", "/MT:8",
                             "/NFL", "/NDL", "/NP", "/LOG:" + str(logs / "pack_robocopy.log")])
    if result.returncode >= 8:
        sys.exit(f"robocopy failed ({result.returncode}): see {logs / 'pack_robocopy.log'}")
    finish(out)


def build_movies(opening: Path, out: Path) -> None:
    if not opening.exists():
        opening.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(OPENING_COMMAND + [str(opening)], check=True)
    # The Russian translation's same movie (its frames are the original's with subtitles drawn in) plays the same video,
    # at the same timing: a sidecar naming it, no second copy of the file. The user's choice: HD without the subtitles.
    timing = [line for line in opening.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
              if line.startswith(("offset=", "rate="))]
    russian = ROOT / "out" / "movies" / "rus.disc1" / "13.txt"
    russian.parent.mkdir(parents=True, exist_ok=True)
    russian.write_text("\n".join(
        ["# The Russian translation's disc 1, movie 13 (the opening): the video of the original's movie 13, its timing.",
         "video=../usa.disc1/13.ogv"] + timing) + "\n", encoding="utf-8")
    if (out / "movies").exists():
        shutil.rmtree(out / "movies")
    shutil.copytree(ROOT / "out" / "movies", out / "movies")


def finish(out: Path) -> None:
    for kept in ("saves", "states", "reports"):
        (out / kept).mkdir(exist_ok=True)

    licenses = out / "LICENSES"
    licenses.mkdir(exist_ok=True)
    copy(ROOT / "weltall" / "LICENSE", licenses / "Weltall_LICENSE.txt")
    copy(ROOT / "bridge" / "godot-cpp" / "LICENSE.md", licenses / "godot-cpp_LICENSE.txt")
    source = (ROOT / "bridge" / "third_party" / "bc7decomp" / "bc7decomp.cpp").read_text(encoding="utf-8")
    notice = (ROOT / "bridge" / "third_party" / "bc7decomp" / "SOURCE.txt").read_text(encoding="utf-8")
    # Its licence is the comment that closes the file ("This software is available under 2 licenses ...").
    tail = source[source.rfind("/*", 0, source.index("This software is available under 2 licenses")):].strip()
    (licenses / "bc7decomp_LICENSE.txt").write_text(notice + "\n" + tail + "\n", encoding="utf-8")
    subprocess.run([str(GODOT / GODOT_CONSOLE), "--headless", "--script", str(ROOT / "tools" / "godot_licenses.gd"), "--", str(licenses)],
                   check=True, capture_output=True)
    (licenses / "README.txt").write_text(
        "What this folder is made of, and the licence each comes with:\n"
        "  Weltall_LICENSE.txt       WeltallCore, the game's engine (github.com/Roman215/Weltall, v1.0.3 + local changes), MIT\n"
        "  Godot_LICENSE.txt         Godot Engine 4.7.2 (engine\\), MIT; Godot_THIRDPARTY.txt its third-party components\n"
        "  godot-cpp_LICENSE.txt     godot-cpp (tag godot-4.5-stable), linked into game\\bin\\xeno_bridge.dll, MIT\n"
        "  bc7decomp_LICENSE.txt     bc7decomp by Richard Geldreich, Jr. (bc7enc_rdo), in xeno_bridge.dll, MIT or public domain\n"
        "Not included: the game's disc images (Xenogears (c) Square), which each player supplies from his own disc.\n"
        "The HD texture pack (pack\\) and the HD opening video (movies\\) are the user's own material, for personal use.\n",
        encoding="utf-8")

    bad = []
    for folder, _, names in os.walk(out):
        for name in names:
            path = os.path.join(folder, name)
            if Path(name).suffix.lower() in FORBIDDEN:
                # The alias index is a .bin of its own (magic XALI), not a disc image.
                with open(path, "rb") as file:
                    if file.read(4) == b"XALI":
                        continue
                bad.append(path)
    if bad:
        sys.exit("disc images, saves or states in the folder: " + ", ".join(bad[:10]))

    total = 0
    print(f"{out}")
    for entry in sorted(out.iterdir(), key=lambda p: (p.is_file(), p.name)):
        size, files = size_of(entry)
        total += size
        print(f"  {entry.name}{'' if entry.is_file() else chr(92)}  {size:,} bytes" + ("" if entry.is_file() else f", {files} files"))
        if entry.is_dir() and entry.name != "pack":
            for child in sorted(entry.iterdir(), key=lambda p: (p.is_file(), p.name)):
                child_size, child_files = size_of(child)
                print(f"    {child.name}{'' if child.is_file() else chr(92)}  {child_size:,} bytes" + ("" if child.is_file() else f", {child_files} files"))
    print(f"total {total:,} bytes ({total / 2**30:.2f} GiB); no disc image, memory card, save or state in it")


if __name__ == "__main__":
    main()
