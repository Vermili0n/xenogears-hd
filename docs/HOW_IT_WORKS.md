# How the port works

Three layers, each in its own folder of `port/`:

```
Weltall core (C++, MIT, not in this repo)   the game itself: field, battle, world map, arena, menus, movies, sound
        |   frames as data (polygons, sprite quads, 2D draw lists, VRAM), PCM sound
bridge  (port/bridge, C++, GDExtension)    turns a core frame into flat vertex/index buffers, finds HD pictures
        |   ArrayMesh data, texture names, info() dictionary
shell   (port/game, Godot 4.7.2, GDScript) draws, lights, plays sound, reads input, loads the HD pictures
```

## The core

Weltall (<https://github.com/Roman215/Weltall>, v1.0.3) runs the game from the disc image and hands out each frame as
data instead of drawing it: the camera (GTE matrices), every placed model with its per-frame vertex colours, sprite
pieces of characters (`Quads`: matrix, corners, UV, texture page, CLUT), particles, the 2D layer (`FDrawList` in
320 x 224 screen pixels, with PS1 blend modes) and the whole VRAM (1024 x 512). Sound is pulled as PCM
(`FGameSoundSystem::Render`). The port does not change game logic; its four patches to Weltall only add switches the
bridge needs (see BUILD.md).

## The bridge (`bridge/src`)

- `xeno_session.*` - the core's frames -> plain buffers, without Godot headers. The world is built in view space
  (the Godot camera stays at the origin and the core moves the world): scene polygons, model vertices with their
  animation (MIMe) and joints, sprite pieces, particles. The battle, the world map and the gear arena are drawn in
  the PS1 painter's order ("as is"); the field uses a depth buffer.
- `xeno_core.*` - the `XenoCore` class GDScript talks to: `open`, `step(buttons)`, `info()`, `fill_world`,
  `fill_screen`, `vram`, save states, cheats, `frame_report`.
- `xeno_discs.*`, `xeno_translation.*` - find disc images by content (Weltall's library scan; the Russian fan
  translation is recognised by a hash of its boot program's code) and adapt the core to the translation: its
  narrow Cyrillic letter widths are read from its own program code, and 77 map archives whose header claims one byte
  more than the stream holds are mended in memory. The translation's text and font are read from its disc as they
  are. What this repository holds about the translation: the character-code table of `tools/rus_text.py` (which
  code is which Cyrillic letter, for reading text dumps) and, in `xeno_session.cpp`, the port's own line
  "Диск не найден." ("Disc not found.") written in the translation's character codes.
- `xeno_check.cpp` - the start-up check of the mod's batch file (which images are there, in which language the game
  will run).
- The other `.cpp` files are headless tools for measuring: map sweeps, sound to WAV, sprite coverage, story walks.

## The shell (`game/main.gd`)

One scene, one script. It steps the core once per game frame (tempo from `VblanksPerFrame`), fills the meshes,
draws the 2D layer on a canvas blended in 8-bit PS1 colour arithmetic (checked against Weltall's reference blending,
`tools/blend_check.py`), adds a sun with shadow maps, ambient light and SSAO on the field (F2 toggles), and feeds the
core's PCM into an `AudioStreamGenerator` with about four vblanks of buffer. The whole VRAM is one texture; 4/8/15-bit
pages and CLUTs are decoded in the shader (`game/shaders/vram.gdshaderinc`).

Keys: F2 light, F3 HD pack, F5 save state, F9 load newest state, F6 frame report, F7 brighten dark places,
F8 battle flashes (as in the game / weak / off), F1 cheat panel, Tab fast-forward, F11 full screen. Every command-line argument is listed at the top of `main.gd`.

## How an HD picture is found

The HD pack is a Beetle-PSX-HD-style texture replacement pack: one file per VRAM upload, named
`<crc32 of the upload's 16-bit words>-<crc32 of its 16-colour palette>` (`.bc7` - a small header plus zlib-packed
BC7 blocks - or `.png`; PNG wins when both exist). The core already computes these names
(`BeetleTextureParts`, `BeetleTextureFileName`), so the port looks up exactly the names the emulator would.

- **Scenery** (models, ground): for every texture page + CLUT pair that has pictures, the bridge composes a 1024 x 1024
  RGBA page: the original texels scaled 4x, with every upload that has a pack file laid over it. Polygons then sample
  that page. Reason: many polygons span several uploads, so "one file per polygon" missed most of them.
- **Sprites and the 2D layer**: one picture per piece. First the upload's own name; for 4-bit sprites, if that
  fails, the name of the "drawn rectangle" (the words the piece is drawn from, hashed like an upload); a piece lying
  across several uploads is cut and each part takes its own picture. A piece wider than its picture repeats the
  picture's edge texel instead of falling back to VRAM.
- **By content**: when no name matches, two sources are asked, in this order.
  1. The table `data/sprite_alias_table.csv` (`SetAliasTable`, published): one line per substitution - what the game
     draws, as hashes (an upload's Beetle name, or the CRC-32 of a rectangle's or piece's texels through its palette),
     its size and palette, the pack picture to draw, and the few texels the game draws that the picture's original
     lacks. It holds no texels of the game. It was recorded from the index on the author's runs (every field map from a
     new game and from one story point, about a hundred of his saves through the whole game, every frame of the party's
     sprites), so it only knows what was met there.
  2. The index `sprite_alias_index.bin` (`SetAliasIndex`, not published: it holds the original texels): the texels of
     the upload (or rectangle, or piece) are compared with the original texels behind every pack picture of the same
     size and palette. A candidate is accepted when the texels opaque in both have the same colour within 8/255 per
     channel and at most max(2, 5 %) texels are opaque in only one of them.

  This catches pieces the game alters slightly before upload and Weltall's own stand-in pilot sprites. Texels the game
  draws but the original lacked are drawn from VRAM under the picture. `alias_record=<file>` writes every lookup as a
  table line (`?` where nothing was found), so a line can be added by hand.
- **Loading**: pictures load on worker threads. Scenery pages show the original texels until they are ready. Sprite and
  2D pictures new in a frame are loaded with priority and the frame waits for them for up to about 17 ms
  ("lazy sync", as the author's emulator setting did), so animation frames do not flash low-resolution.

What the pack does not have is drawn from the original VRAM texels (scaled), never left blank.

## F6: the frame report

F6 (in any program, cutscenes included) pauses the game and writes a folder into `reports/` (mod) or
`out/frame_reports/` (development tree):

- `shot.png` - the frame as shown; `shot_plain.png` - the same frame without the pack and the light;
- `frame.txt` - settings, the core's `info()`, open message windows, the party; then the bridge's report: every
  piece drawn **not** from the pack, grouped (sprite pieces, 2D, model textures, the rest), with its pack name,
  size, VRAM place, why it was not found (no file, still loading, page without pictures, lookup miss) and who drew it
  (actor, sprite set and frame, model); at the end the list of names the pack lacks; then every primitive of the
  frame (draw order, depth, corners, UVs);
- `state.state` and `inputs.txt` - the last quiet save state and the buttons since, so `script_file=inputs.txt`
  replays the way to that frame headless or in the window.

Limits: the replay loads the state as the field returning from a battle, so things counted from the map's entry tick
(rotating save-point signs, map animations) may differ; turbo and cheats used after the state are not replayed.

## The working rule: fix a class, not a scene

Every defect report was traced to a rule that holds for all scenes (the data of the core, the emulator's behaviour,
the pack's naming), and fixed as that rule, then measured over all maps / the whole story walk, not by eye on one
scene. Examples: sprite pieces drawn on their full cell with UVs to the last texel (from the pack author's own model
of how the game draws a frame); per-piece depth steps so earlier pieces stay on top as on the PS1; flat details lying
on a wall or floor (pictures, carpets, signs) pushed 0.1 % towards the eye when they lie on a polygon drawn earlier
(the PS1 orders them by its ordering table, the port by a depth buffer). Changes were checked with
`tools/regress.py` (pixel comparisons against reference shots, a sweep of all 730 field maps, a live 20 s run for
sound underruns).

## Known open places

Taken from the author's working notes at the end of the playthrough. "Not verified" means the author did not see it
in the game.

- **Battle panel black block** (one warehouse battle): the black quads are flat polygons of the battle scene itself
  in the core's data, drawn in their PS1 order; not compared with an emulator by eye, not changed.
- **Battle flashes** (F8, `flash=2|1|0`): the full-screen flash of a blow or a Deathblow is the battle frame's fade layer,
  one untextured tile over the screen that adds its colour, started by the effect's script. The bridge draws such a
  layer with all of its colour, a third or none (Weltall's own rule for its battle flashes setting, `DrawnFadeShare`);
  the battle's own fades and every darkening stay. Measured: with `flash=2` the picture equals the build before it
  pixel for pixel; the rule acts in battle only.
- **Dark scenes**: the port's unlit frame matches the core's picture; the game itself is that dark. F7 adds an
  optional brightening curve (off / weak / stronger). Night scenes with the added sun light still cast sun shadows.
- **Two reported scenes were not reproduced** from the nearest saves: partly low-resolution Bart in a red-lit cockpit
  cutscene, and odd shadows of a motorcycle in a night desert. Both need an F6 report taken on the spot.
- **Pack gaps left open**: a story character's texture that does not come from the map files; a gear set where the
  model drew a pilot instead of the gear on 6-7 frames; a set where the HD redraw dressed a character; pink fringe on
  13 gears (prepared, not applied by the author's choice); the item-list font of gear battles and the gauge of foot
  battles; one field particle; three battle sets painted in two palettes; further "0 x 0 piece" cases.
  Several recently added sets (newly painted NPCs, a few battle sets) were checked only on preview sheets - not
  verified in the game.
- **Not drawn in the gear arena**: the blur of the pause picture, the menu's motion trails, frame blending between
  passes; the gear's shadow square darkens its lower half (the battle and arena scenes are blended in linear light).
- **Seams**: thin light lines between scenery polygons/pages are visible with the HD pack.
- **Light indoors** mostly darkens: interiors have their lighting painted into the textures.
- **USA disc 2** was never tried (the playthrough used the Russian translation's two discs; the USA disc 1 far less).
  Only movie 13 (the opening) has an HD replacement.
- **Platforms**: tested on one PC. Direct3D 12 and OpenGL 3.3 start (Godot falls back when Vulkan is missing), but
  their picture was not compared. `--headless --import` exits with code 139 after a successful import (not
  investigated).
