# Building the port

This describes how the port in `port/` was built on the author's machine (Windows 10, x64). It has been built on
that one machine only. A build from this repository on another machine has **not been verified**; the steps below
are the ones the author used, written out.

## What you need

| Tool | Version used | Notes |
|---|---|---|
| Windows | 10 / 11, 64-bit | the bridge and the batch files are Windows-only |
| Godot | 4.7.2 stable (win64, standard build, not .NET) | the editor/runtime binary is not in the repository |
| MSVC | Visual Studio Build Tools 2026 (18.4), MSVC 19.50, Windows SDK 10.0.26100 | C++20 |
| CMake | 4.2.3 (the one shipped with the Build Tools); `bridge/CMakeLists.txt` asks for 3.25+ | generator "Visual Studio 18 2026" |
| Git | any recent | for the two clones and `git am` |
| Python | 3.x | only for `tools/` (checks, the mod folder); not needed to build or run |

Older MSVC / Visual Studio generators were not tried.

## Sources that are not in this repository

Both go inside the `port/` folder, where `bridge/CMakeLists.txt` expects them (both paths are git-ignored):

1. **Weltall** (the open game core, MIT) - <https://github.com/Roman215/Weltall>, tag `v1.0.3`,
   commit `03452af61707b574c310cad2ba057d3577d10a30`, cloned into `port/weltall/`.
   The port's own changes to it are in `port/patches/weltall/` (four patches, applied with `git am`).
2. **godot-cpp** - <https://github.com/godotengine/godot-cpp>, tag `godot-4.5-stable`
   (commit `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77`), cloned into `port/bridge/godot-cpp/`.
   The extension is built against the 4.5 API and loads in Godot 4.7.2 (`compatibility_minimum = "4.5"`).

```
cd port
git clone https://github.com/Roman215/Weltall.git weltall
cd weltall
git checkout -b xeno-local v1.0.3
git rev-parse HEAD                      # must print 03452af61707b574c310cad2ba057d3577d10a30
git am ..\patches\weltall\*.patch       # needs git user.name / user.email set
cd ..\bridge
git clone --depth 1 --branch godot-4.5-stable https://github.com/godotengine/godot-cpp.git godot-cpp
```

What the patches do (all are off unless the bridge turns them on):

- `0002` - field message windows laid out as the Russian translation's program lays them out (`bRussianWindows`).
- `0003` - a watcher hook for the story sweep tool (tests/support code).
- `0004` - the sound session can start from a disc the host has identified itself (needed to run the translation
  from one image).
- `0005` - a host-supplied "disc not found" line under the disc prompt, in the disc's own text codes.

There is no `0001` in the folder: the author's first local commit only split four over-long string literals in
Weltall's own test files (`Tests/WeltallCore/WorldMap/WorldMap{Frame,Tick}OracleTests.cpp`, MSVC error C2026). The
bridge does not compile those files. If you want to build Weltall's test suite with MSVC, run
`python ..\tools\split_long_literals.py <file> ...` on them first. Whether `0002`-`0005` apply cleanly to a bare
`v1.0.3` without that first commit has **not been verified** (they touch other files, so they are expected to).

## Building the bridge

From PowerShell (in Git Bash `CL=/MP` turns into a path; use PowerShell or cmd):

```
cd port\bridge
$env:CL = '/MP'
cmake -S . -B build -G "Visual Studio 18 2026"
cmake --build build --config Release
```

The CMake from the Build Tools lives under
`<Build Tools>\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\` and is not on `PATH` by default.

Outputs:

- `port/game/bin/xeno_bridge.dll` - the GDExtension the Godot project loads (`game/xeno.gdextension`).
  `-DXENO_BIN=<folder>` writes it elsewhere (the author used this to rebuild while the game was running).
- `port/bridge/build/Release/*.exe` - headless tools: `session_smoke`, `pack_sweep`, `world_sweep`, `arena_sweep`,
  `sound_smoke`, `text_sweep`, `sprite_parts_dump`, `story_walk`, `story_states`, `sprite_coverage`, `movie_dump`
  and `xeno_check` (the start-up disc check the mod's batch file runs).

The core is compiled the way Weltall's own `Tests/CMakeLists.txt` compiles it (`/EHs-c- /GR- /W4 /WX`), but with
godot-cpp's static CRT; `/GR-` is kept off the godot-cpp side, which needs RTTI. The DLL and `xeno_check.exe` link
the CRT statically and import only `KERNEL32` (checked with `dumpbin /dependents` on the author's build).

## Godot

Put the Godot 4.7.2 binaries into `port/tools/godot/`:

```
port/tools/godot/Godot_v4.7.2-stable_win64.exe
port/tools/godot/Godot_v4.7.2-stable_win64_console.exe
port/tools/godot/_sc_            (an empty file: self-contained mode, editor data stays beside the binary)
```

Import the project once (headless), then run:

```
port\tools\godot\Godot_v4.7.2-stable_win64_console.exe --headless --import --path port\game
port\play.cmd
```

On the author's machine `--headless --import` exits with an access violation (code 139) after it has written
`game/.godot/extension_list.cfg`; the game starts normally afterwards. The cause was not investigated.

## Disc images (yours)

No game data is in this repository or in the releases. You need an image of your own disc.

- **USA disc 1** (BIN+CUE or CHD): by default `play.cmd` looks in `port/weltall/Games/` (ignored by Weltall's git).
  With `games=<folder>` it looks elsewhere. ISO/IMG are read too, but the movies then have no sound.
- **Russian fan translation, disc 1**: the default `lang=ru` expects `port/games_ru/xenogears_rus_xz.CUE`
  (`rus=<image>` for another place). Without it the USA text plays (a warning is logged).
- `lang=auto` finds the discs in the games folder by their content (the translation's disc 1 first, then USA).
- **Disc 2** of the same release: in the same folder (or the translation's folder); the game finds it by content when
  the story asks for it.

`xeno_check.exe check <root>` prints which images it recognises (the image sizes and SHA-1 the author checked
against are in `port/mod/README.txt`).

## The HD pack

The game runs without it (original PlayStation textures). To use it:

- extract the pack so that the pictures are in `port/pack/` (the default `pack=` is `pack` under `root=`), or
- pass `pack=<folder>` to the game, for example RetroArch's `system/Xenogears (USA)-texture-replacements`.

Pictures found by content (see `docs/HOW_IT_WORKS.md`) come from two files; the table is asked first:

- `port/data/sprite_alias_table.csv` - in this repository, read by default (`alias_table=<file>` for another one).
  Hashes and pack file names only. It was filled from the author's runs and answers there as the index does.
- `sprite_alias_index.bin` - the content index. **Not published**: it holds the original texels of the game's sprites.
  If you build it yourself with `tools/sprite_alias_index.py` (it needs the sprite pipeline's extracted parts, game
  data - set `XENO_EXTRACTED` and `XENO_DUMPS`), put it into `port/out/alias/` or pass `alias_index=<file>`.

`alias=0` turns both off. `alias_record=<file>` writes every lookup by content as a line of the table (picture `?`
where nothing was found; with the index, the picture it found). `tools/sprite_alias_table.py` merges such files into
the table; `tools/alias_table_runs.py` runs the headless sweeps the table was filled and measured with
(`XENO_ALIAS_TABLE`, `XENO_ALIAS_RECORD`, `XENO_ALIAS` for the headless tools).

Paths are relative to `root=` (default: the `port/` folder). See the header of `game/main.gd` for every argument.

## The ready-to-run mod folder

`python tools\make_dist.py <out folder>` builds the folder the release archive was made from: Godot, the DLL,
`xeno_check.exe`, the project without its `.godot` cache, the batch file and notes from `mod/`, licences (it reads
`weltall/LICENSE` and `bridge/godot-cpp/LICENSE.md`, and runs `tools/godot_licenses.gd` in Godot for Godot's own
third-party list). Environment:

- `XENO_PACK=<pack folder>` (default `port/pack`) - copied with `robocopy /MIR`;
- `XENO_OPENING_VIDEO=<mp4>` and `FFMPEG=<ffmpeg.exe>` - only if you have an HD video of the opening; without it
  (and without `out/movies/usa.disc1/13.ogv`) the `movies` folder is left out and the game shows its own movie;
- `data/sprite_alias_table.csv` is copied into the folder's `data/`; `out/alias/sprite_alias_index.bin` is copied
  too if you built it (it is not needed).

The script refuses to finish if the folder contains a disc image, a memory card, a save or a state.

The environment variables above replaced paths of the author's machine when the repository was prepared; since that
change `make_dist.py` has only been byte-compiled, not run.
