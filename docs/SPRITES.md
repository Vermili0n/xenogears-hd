# The sprite pipeline (how the HD sprites of the pack were made)

`sprites/` holds the scripts of this pipeline as a research archive. It is **not** a tool that runs out of the box:
the scripts were written for one machine and one working folder, they expect data that is not published (anything
extracted from the game, the references, the trained model weights, the rented-GPU outputs), and paths, hosts and
key names in them were replaced by placeholders (`<XENO_SPRITES>`, `<POD_HOST>`, `<JUMP_HOST>`, `<SSH_KEY>`,
`<DATA_DRIVE>`, ...). What follows is reconstructed from the scripts' own descriptions and the author's notes;
numbers are the author's, not re-measured.

The pack replaces textures by name, as Beetle PSX HD does: `<crc32 of the uploaded VRAM words>-<crc32 of the
16-colour palette>`. This pipeline redrew the **2D sprites** (heroes, story characters, map NPCs, battle sets, field gears, some UI) and wrote them into the pack
under those names. Where the rest of the pack's pictures (scenery etc.) come from is not described here (not
verified).

## 1. Extraction (`sprites/tools`)

- Disc access and the game's file table: `xdisc.py`, `xfs.py` (hidden file table + LZSS; logic follows
  andreaukk/XenoTools, MIT), `isolist.py`, `toc_find.py`.
- Sprite sets: `xspr.py` parses the game's 2D sprite format (layout per rufaswan's Web2D_Games notes, see the licence
  remark in THIRD_PARTY.md); `extract_heroes.py`, `extract_npc.py`, `npc_maps.py` (map NPCs: map file N = data,
  N+1 = VRAM textures), `npc_tex.py`, `battle_extract.py`, `scan_all.py` (every disc file and every LZSS sub-file).
  Each set becomes a folder with its parts (`<rect>-<palette>.png`), a `layout.json` (which part goes where in
  which frame) and the places it is used.
- Names: `match_file.py`, `verify_hash.py`, `coverage.py` check that the computed names equal what the emulator
  dumps.
- `render_frames.py`, `assemble4x.py`, `preview_parts.py` assemble whole frames from parts exactly as the game does,
  so a redraw can be cut back into the same parts.

## 2. References and teacher redraws

- Per character an identity "board": a turnaround sheet and a face close-up, made with image-model help from the
  in-game portrait and checked by eye (`make_refs.py`, `char_package.py`, `gpt_helper.py`, `or_refs.py`;
  `wiki_chars.py` fetched character pages from the series wiki for reference).
- Keyframe grids: 16 sprite frames per 4 x 4 grid, smoothed (xBR) at 8x on a flat magenta background
  (`make_grids.py`), redrawn by a hosted image model with the board as reference (`gem_batch.py`, `gem_direct.py`,
  `or_batch.py`, `campaign_build.py`, `npc_batch.py`; prompts in `tools/prompts/`). Results were fitted back onto the
  original silhouettes (`prod_fit.py`, `gpt_fit.py`, `gpt_rigid.py`) and rejected when they did not match
  (`campaign_qa.py`).
- Early experiments, abandoned: local img2img with ControlNet (`ai_redraw.py`), Real-ESRGAN / xBR upscales
  (`esrgan_parts.py`, `upscale_parts.py`), ebsynth propagation between frames (`ebs_*.py`).

## 3. A local student model

The accepted teacher redraws became training triplets (sprite frame + identity board -> redraw;
`make_pairs_v2.py`, `make_pairs_v3.py`, `refit16.py`). An edit LoRA for FLUX.2 klein 4B was trained on rented GPUs
with ostris/ai-toolkit (`pod/train_pod*.sh`, masked loss in v4). Version 4 draws characters and NPCs; version 2 is
used for gears. The pod scripts (`pod/infer_pod.py`, `pod/setup_infer.sh`, watchers and sync scripts) render job
lists produced locally. The weights are not published.

## 4. Production, slicing and installation

- `render_prod.py`: per group (heroes, story characters, map NPCs, battle sets) a greedy cover of its parts - only
  frames that bring a part not drawn yet are rendered; heroes and story characters get a second 16x pass for the head.
- `prod_post.py`: renders -> composite at 8x (head pass pasted in) -> sliced into the set's parts with exact masks and
  the game's UV stretch compensated -> map NPC sheets projected onto every VRAM upload block of every map that uses
  them -> staging folder per group. Colour is pulled back to the sprite's palette (`color_fix.py`,
  `color_local.py`, `hair_fix.py`), magenta fringe removed (`defringe.py`, `fix_magenta.py`).
- Installation: `install_parts.py` (any pack file not written by the pipeline is backed up once before it is
  replaced), `merge_shared.py` (files several groups write), `redraw_finish.py` (PNG -> BC7, then seam fill).
- QA is done by eye on sheets: the original sprite is the reference (`qa_sheet.py`, `qa_zoom.py`, `qa_group.py`,
  `qa_backview.py`, `glasses_sheet.py`). Re-renders of single frames with a text hint: `redraw_pick.py` ->
  pod -> `fix_apply.py` -> `redraw_finish.py` (the Russian how-to `sprites/КАК_ПЕРЕРИСОВАТЬ.md` describes these
  steps; it is the author's working note, in Russian).

## 5. Classes of gaps found, and what closed them

Found while playing through the game in the port (F6 frame reports) and by sweeps. Each was fixed as a class.

| Class | What happened | Closed by |
|---|---|---|
| Altered uploads | The game changes a few texels of some parts before uploading (Elly's hair), so the name differs | copy of the HD under the altered name (`alias_dump_parts.py`); in the port, the content lookup |
| Palettes never drawn | A hero part shown in a palette the redraw was not made in | palette swaps (`hero_palette_swaps.py`, `pod/palette_swaps_*.py`) |
| Strip uploads | NPC sheets uploaded in full-width VRAM strips: neither block nor page names match | "drawn rectangle" names (`npc_rects.py`, `battle_rects.py`), page-aligned files (`npc_pages.py`) |
| Seams | The redraw is slightly thinner than the pixel silhouette: dark lines where parts meet | interior fill (`seam_fill.py`, `seam_fill_all.py`, `seam_fill_npc.py`) |
| Set copies | A map streams its own copy of a hero set (Elly on two forest maps) | `elly_copy_set.py`, `elly_copy_install.py` |
| Sets with own pixels | Field sets missed by `npc_maps.py` | `empty_sets.py`, `own_set.py`, `own_pixel_sets.py` |
| Frames on block 0 | A frame whose layout names block 0 (no head in the set) made the slicer treat it as empty, so its parts were never drawn | `ai/redraw/zero_block/` |
| Battle palettes | A battle set drawn under one palette; the game paints the same sheet with another palette for another enemy | recolour of the finished HD by each texel's palette index (`ai/redraw/battle_palettes/recolor_set.py`); 3 sets painted in two palettes left open |
| Streamed frames | A character's special move comes from a separate file with one block per frame, texel for texel equal to frames of an already drawn sheet set | re-cut of the drawn composites into the streamed layout (`ai/redraw/id_chi/`); `scan_streamed.py` finds candidates |
| First picture only | `npc_maps.py` took only the first picture of a sub-file element: 15 NPC sets with foreign parts | `ai/redraw/gaps_1115/npc_fixed.py` |
| 0 x 0 pieces | Pieces whose size is 0 x 0 on the disc were dropped at extraction (43 sets, 126 pieces); the game sets their size at run time and the rule was not found | partly (`gaps_1115/zero_pieces.py`); open |
| Twin sets | An NPC drawn from the same sheet as another set | copy (`gaps_1115/npc_twins.py`) |
| Non-sprite 2D | Compass (256 palettes + shadow), gear-battle panel (font, frame, gauge per palette state), target ring | drawn programmatically (`gaps_1115/compass_draw.py`, `hud_draw.py`, `ring_draw.py`) |
| Magenta fringe | Pink key colour left on gear wings | `gaps_1115/gear_pink.py`, `pink_install.py` (one gear; 13 more prepared, not applied) |
| Model mistakes | Faces drawn on back views, lost eyepatch / glasses, invented ponytail, clothes | hint re-renders (`fix_jobs.py` HINTS, `redraw_pick.py`), masked repaint for the eyepatch (`eyepatch_*_jobs.py`, `tools/eyepatch_fix/`) |
| Oversized textures | Textures with sides above 2048 px, which the author's emulator core capped anyway, cost decoding time and video memory | pre-shrink (`pack_shrink.py`) |

## What is not in `sprites/`

Not published, on purpose: everything extracted from the game (`extracted/`, sprite sheets, layouts and palettes,
VRAM dumps, save states, reference screenshots), the references and wiki pictures, the teacher redraws, the trained
weights, rented-GPU outputs and logs, job lists and installation lists (they are lists of the game's texture names
and layouts), the author's reports and diaries, and third-party tools (ebsynth sources, Real-ESRGAN, sd.cpp
binaries, model checkpoints).
