extends Node3D
## The game drawn from WeltallCore's frames: the scene in view space under a fixed camera (the core moves the world),
## the 2D layer over it at 320 x 224 scaled to the window's height, on the canvas, blended as the PS1 blends (_flat_shader).
## Textures: the user's Beetle texture pack where it has
## pictures (the scenery's pages with the pack's pictures laid in, sprites' and the 2D layer's pictures as they are),
## the PS1's VRAM elsewhere. Light: a sun with shadows (the characters' sprites cast theirs), ambient light, SSAO.
##
## Command line (after --): map=4 | boot=1 | card=<memory card image> slot=<N>  games=<folder> pack=<folder> hd=1 light=1
##   root=<folder> (what relative locations are under; by default the xeno_port folder: games weltall/Games, saves
##   out/saves/game, states out/states, alias_index out/alias/sprite_alias_index.bin, alias_table
##   data/sprite_alias_table.csv, movies out/movies)
##   lang=ru|en|auto (auto: the discs in the games folder found by content, the Russian translation's disc 1 first)
##   rus=<image> (lang=ru: the translation's image, games_ru/xenogears_rus_xz.CUE)  alias_index=<file>  movies=<folder>
##   (disc 2 is taken by the bridge where the game asks for it, found by content: the translation's disc 2 in the folder
##   of rus= and then in games=, the USA's in games=; while it is missing a line over the game says where, _follow_disc)
##   sun=<energy> ambient=<energy>  dark=0|1|2 (F7's brightening of dark places: off, weak, stronger; else the player's
##   last choice, weak at first; scripted runs: weak unless given)
##   flash=2|1|0 (F8: the battle effects' full-screen flashes as in the game, weak, off; else the player's last choice, as
##   in the game at first; scripted runs: as in the game unless given)  flashlog=1 (for checks: a line whenever a battle
##   frame's fade layer changes)
##   ff=<frames> script=<frames:buttons,...> shot=<png> log=1  sound=0  quit_after=<seconds>  states=<folder>  notes=1
##   saves=<folder> (the game's own saves elsewhere than out/saves/game, for checks)
##   at=<seconds>:save|load|hold=<buttons>|snap,... (live play, for checks: F5 or F9 pressed, buttons held from then on,
##   the window's shot into shot_dir=<folder>, by default out/shots/live)
##   hdsync=0 (the pack's own pictures drawn from VRAM until loaded, as before), hdlog=<csv> (the HD loading, per frame and picture)
##   alias=0 (no pictures found by content for uploads the pack has no name of: the table data/sprite_alias_table.csv,
##   then the index out/alias/sprite_alias_index.bin)  alias_table=<csv>  alias_record=<csv> (each lookup by content
##   written as a line of the table, the picture found or "?")
##   state=<file> map=<N> (that map entered from the state's point of the story, for checks)
##   world=0 / layer=0 (the 2D layer alone / the frame without it); the blend checks' layer_runs=, flat_f=, clear=,
##   checks=, as_blend= (tools/blend_check.py)
## A new game is map=4; ff=8000 plays the opening through with Cross to Fei's room (map 14). boot=1 starts the console as
## a player does: the kernel's notice, the opening movie, the title (New Game from there).
## Every screen is drawn from the core's frames: the field, the battle, the world map (its 216-line screen: the camera's
## height follows info.scene_lines), the gear arena (Battling: its frame in the world map's form on 218 lines), the menus
## (over the field's or the world map's last picture), the movies (the Movie program's and the field's), the boot notice,
## the field's picture of the screen, a chapter's card. For checks a script's @arena=<from>.<kind>.<gear>.<gear>.<wins>.<level>
## has the running field ask for the arena with those six bytes (as the field's FE BF does; map=15 as Weltall's audit);
## @movie=<number>.<end frame> has it ask for that movie of the disc in the drive full screen (as FE 60 does).
## The pack's pictures load on worker threads: the scenery's pages are drawn from VRAM (the original's texels) until one
## is ready and switch to it once it is uploaded (uploads take at most TEXTURE_BUDGET_USEC of a rendered frame); the
## pack's own pictures (sprites, the 2D layer) are loaded on the frame that first draws them (hd_sync).
## The live game (no script, no shot) is heard unless sound=0; quit_after=<s> ends it after that long and prints one line
## (seconds, game frames, sound frames pushed, generator underruns). Scripted runs keep the sound unheard (deterministic).
## A script plays exactly one game frame per Godot frame, then saves the shot and quits; buttons are names joined
## by "+" (up, down, left, right, cross, circle, square, triangle, start, select, l1, r1, l2, r2) or "none", "~" after
## them taps them every other frame. A step can
## also be an action between frames: @save (F5), @load (F9), @snap (a shot now: <shot>_<n>.png, after the pictures load).
## F5 saves a state into out/states (states=<folder> elsewhere), F9 loads the newest there; the game's own saves (the
## File screen, the title's Continue) are kept in out/saves/game.
## F6 (a script's @report, at= report) makes a report of the frame shown at any moment, cutscenes too: a folder in
## out/frame_reports (reports=<folder> elsewhere) with the shot, the shot without the pack and the light, frame.txt (what is
## drawn not from the pack, every primitive), state.state and inputs.txt (script_file=<inputs.txt> plays that state's way
## to the frame again); _frame_report says how.
## Cheats (for running through the game quickly; off unless asked for): F1 opens the cheat panel (the game paused: the
## party's levels, HP/EP and deathblows, money, items, gears, random battles, turbo), Tab held runs the game at 4 times its pace where
## Weltall's own fast-forward runs (a battle, the field, the world map), F4 wins the battle being fought. On the command
## line: encounters=0 (random battles off), turbo=<2|4> (always that pace, live play); in a script @cheat=<cheat> (as
## core.cheat: money:N, exp:fei:N, level:fei:K, fill:party, deathblows:fei|party, gears, item:<list>:<id>:<count>, win, encounters:0) and
## @panel / @panel=<tab> (the panel shown or hidden, for shots); in at=: turbo<N>, panel.

const PAD := {
	"select": 0, "l3": 1, "r3": 2, "start": 3, "up": 4, "right": 5, "down": 6, "left": 7, "l2": 8, "r2": 9,
	"l1": 10, "r1": 11, "triangle": 12, "circle": 13, "cross": 14, "square": 15,
}
const KEYS := {
	KEY_UP: "up", KEY_DOWN: "down", KEY_LEFT: "left", KEY_RIGHT: "right",
	KEY_X: "cross", KEY_Z: "circle", KEY_A: "square", KEY_S: "triangle",
	KEY_ENTER: "start", KEY_BACKSPACE: "select", KEY_Q: "l1", KEY_W: "r1", KEY_E: "l2", KEY_R: "r2",
}
const JOY := {
	JOY_BUTTON_A: "cross", JOY_BUTTON_B: "circle", JOY_BUTTON_X: "square", JOY_BUTTON_Y: "triangle",
	JOY_BUTTON_START: "start", JOY_BUTTON_BACK: "select", JOY_BUTTON_LEFT_SHOULDER: "l1", JOY_BUTTON_RIGHT_SHOULDER: "r1",
	JOY_BUTTON_LEFT_STICK: "l3", JOY_BUTTON_RIGHT_STICK: "r3",
	JOY_BUTTON_DPAD_UP: "up", JOY_BUTTON_DPAD_DOWN: "down", JOY_BUTTON_DPAD_LEFT: "left", JOY_BUTTON_DPAD_RIGHT: "right",
}
## The HD pack's folder, under root= unless absolute; pack=<folder> on the command line for another place (for example
## RetroArch's system/Xenogears (USA)-texture-replacements). Missing or empty: the game runs without HD and says so.
const PACK := "pack"
## The Russian translation's disc 1, a copy of the player's own in a folder git ignores (lang=ru, the default).
const RUSSIAN_DISC := "games_ru/xenogears_rus_xz.CUE"
## A gamepad Godot's database does not know reports its buttons as they are numbered on the pad. The user's Microntek /
## DragonRise USB Joystick (USB 0079:0006) is PlayStation-shaped: buttons 1-4 triangle, circle, cross, square, then L1, R1,
## L2, R2, Select, Start (SDL's gamecontrollerdb maps that kind so). Its pad and stick come as directions either way.
const RAW_PAD := {0: "triangle", 1: "circle", 2: "cross", 3: "square", 4: "l1", 5: "r1", 6: "l2", 7: "r2", 8: "select", 9: "start"}
const RAW_DIRECTIONS := {JOY_BUTTON_DPAD_UP: "up", JOY_BUTTON_DPAD_DOWN: "down", JOY_BUTTON_DPAD_LEFT: "left", JOY_BUTTON_DPAD_RIGHT: "right"}
# render_mode and alpha per blend mode (xeno_session.h EBlend): opaque, B/2+F/2, B+F, B-F, B+F/4.
const BLENDS := [
	["", ""],
	["blend_mix, depth_draw_never", "ALPHA = semi ? 0.5 : 1.0;"],
	["blend_add, depth_draw_never", "ALPHA = 1.0;"],
	["blend_sub, depth_draw_never", "ALPHA = 1.0;"],
	["blend_add, depth_draw_never", "ALPHA = semi ? 0.25 : 1.0;"],
]
## The shaders' kind of a pack picture's point (after their kinds uniform) where its primitive is semi-transparent: 1
## blends, 0.5 plain, 0 not drawn. Each point takes the kind of the original texel it shows (FSession::TexelKinds: 1
## blends, 0.5 plain, 0 transparent; white, no kinds noted: all blend). A transparent texel has none: the GPU never draws
## it. But a picture drawn larger than the original draws its shapes' rims past their texels' edges, over transparent
## texels (measured: up to two texels out): such a point shows the drawn texel nearest to it (distance from the point to
## the texel's square, among the primitive's own texels within two), and is drawn as that one is. None that near: the point
## shows nothing the primitive draws (another shape's rim reaching in), and is not drawn, as the GPU draws nothing there.
## Before, such points were all plain (as Weltall's renderer draws a picture without kinds over a transparent texel,
## TextureReplacements.ush): the rim of a blending shape stayed opaque, black where the shape faded out (colour 0, add).
const PICTURE_KINDS := """
float picture_kind(vec2 at, vec4 bounds) {
	ivec2 size = textureSize(kinds, 0);
	vec2 p = at * vec2(size);
	ivec2 under = clamp(ivec2(floor(p)), ivec2(0), size - 1);
	float kind = texelFetch(kinds, under, 0).r;
	if (kind > 0.25) {
		return kind;
	}
	ivec2 lowest = ivec2(0);
	ivec2 highest = size - 1;
	if (bounds.z >= 0.0) {
		lowest = clamp(ivec2(floor(min(bounds.xy, bounds.zw) * vec2(size) + 0.001)), ivec2(0), size - 1);
		highest = clamp(ivec2(ceil(max(bounds.xy, bounds.zw) * vec2(size) - 0.001)) - 1, lowest, size - 1);
	}
	vec2 f = p - vec2(under);
	float nearest = 1e9;
	kind = 0.0;
	for (int y = -2; y <= 2; y++) {
		for (int x = -2; x <= 2; x++) {
			ivec2 cell = under + ivec2(x, y);
			if (any(lessThan(cell, lowest)) || any(greaterThan(cell, highest))) {
				continue;
			}
			float k = texelFetch(kinds, cell, 0).r;
			if (k < 0.25) {
				continue;
			}
			vec2 d = max(max(vec2(float(x), float(y)) - f, f - vec2(float(x + 1), float(y + 1))), vec2(0.0));
			float d2 = dot(d, d);
			if (d2 < nearest) {
				nearest = d2;
				kind = k;
			}
		}
	}
	return kind;
}
"""
## Which way the sunlight travels, in the game's world axes (y down): about 40 degrees up; with the game's usual camera,
## from the top left of the screen, so shadows fall to the lower right.
const SUN_TRAVELS := Vector3(0.9, 0.85, -0.5)
## The time of a rendered frame (its game frames, its build, its uploads) within which loaded pictures go up to the GPU:
## uploads start only while the frame so far is within it, and stop once it is spent (the first may run past it: a page
## with its mipmaps takes up to ~40 ms). Far under the sound's lead (4 vertical blanks, 67 ms), so loading never starves
## the sound; a frame that stepped and built the game uploads nothing, the frames between game frames do.
const TEXTURE_BUDGET_USEC := 4000
## The frame's VRAMs (xeno_session.h EVramSource): the scene's, the 2D layer's own (a menu's, the notice's), the overlay's.
const VRAM_SOURCES := 3

var core := XenoCore.new()
var world_mesh := ArrayMesh.new()
## The 2D layer: drawn on the canvas over the finished 3D picture (Godot's 2D target: 8 bits a channel, values as
## displayed, every blend clamped), one canvas mesh per run, in the list's order (_flat_shader says why).
var flat_layer: CanvasLayer
var flat_meshes: Array = []
## The field's screen wave (core.screen_wave): the 3D picture drawn again through the wave's grid, under the 2D layer.
var wave_node: MeshInstance2D
var wave_mesh := ArrayMesh.new()
## Per run: the node drawing it, and a second over it for a subtracting run (its texels that do not blend).
var flat_nodes: Array = []
var flat_warm: Array = []
## For the blend checks (tools/blend_check.py): layer_runs=<k> draws only the 2D layer's first k runs; flat_f=<k> draws
## run k alone, its blending pixels as their F, opaque (the rest discarded); clear=<r>,<g>,<b> (0-255) the clear colour.
var layer_runs := -1
var flat_f := -1
var clear_override := Color(-1, -1, -1)
var last_runs: Array = []
## checks=<k>+<k>...: after the shot, for each of those runs four more of the same frame (<shot>_r<k>_B/R/Fb/Fw.png):
## the runs before it, the runs up to it, it alone as F over black and over white (tools/blend_check.py reads them).
var check_runs: Array = []
## as_blend=<from>:<to> (checks only): runs of one blend mode drawn in another, for a mode the game has not drawn yet.
var blend_remap := [-1, -1]
var world_node: MeshInstance3D
var camera: Camera3D
var environment: Environment
var sun: DirectionalLight3D
var vram_texture: ImageTexture
## Each VRAM source's texture (the scene's is vram_texture) and the stamp of what was uploaded into it.
var vram_textures: Array = []
var vram_stamps: Array = []
## Pictures loading on worker threads: key -> [job, task, scene generation when asked]; keys whose picture could not be read.
var loading := {}
var failed := {}
var uploads_total := 0
var upload_usec_longest := 0
## The pack's own pictures (sprites' pieces, the 2D layer's, particles': not the "page:" textures of the scenery) are
## loaded on the frame that first draws them, as the user's core does with its HD caching "Lazy (synchronous)"
## (beetle_src/rhi/rhi_tt.c, get_hd_texture_index: every unbound combo of a draw dispatched to the IO pool, then the bind
## waits for its own; HD_TEXTURE_CACHE.md, "Pooled Lazy-sync"): all of a frame's new ones are built at once on the
## workers ahead of the scenery's pages, the frame waits for them (live play: while its process stays within a quarter of
## the sound's lead, process_started) and is built again with them. hdsync=0 draws VRAM's texels until they are ready
## (the earlier rule, for comparisons). A picture once loaded stays for the session (textures is never thinned for them).
var hd_sync := true
## alias=0: no pictures found by content (FSession::SetAliasIndex, SetAliasTable) - only the pack's own names, for comparisons.
## alias_index=<file>: the index elsewhere (the mod folder's data\). alias_table=<csv>: the table of what the index found,
## hashes only (data/sprite_alias_table.csv, asked first; a build without the index has only it). alias_record=<csv>:
## each lookup by content written as a line of the table (SetAliasRecord; off unless given).
const ALIAS_INDEX := "out/alias/sprite_alias_index.bin"
const ALIAS_TABLE := "data/sprite_alias_table.csv"
var alias_on := true
var alias_index := ""
var alias_table := ""
var alias_record := ""
## What finds pictures by content in this run (_read_pack), for the frame report's settings line.
var alias_found := "none"
## root=<folder>: what relative locations on the command line are under (by default the xeno_port folder, _from_root).
var root_folder := ""
## A script, a shot or a timed run: nobody to read a message in the window (_fail_in_window quits instead).
var unattended := false
## The game could not start and says why in the window (_fail_in_window); closing it ends the process with code 2.
var failed_to_start := false
## The pack's folder was missing or empty: the original's pictures, said once the game runs.
var pack_missing := false
## The movies' replacements (_follow_movie): movies=<folder>, in it <disc>/<NN>.ogv as the bridge names the movie
## (info.movie_source, e.g. usa.disc1; info.movie_number, the movie's number in its disc's movie group, two digits) and
## beside it <NN>.txt, the video's time for the movie's frames ("offset=<s>", "rate=<x>": video time = offset + rate x
## (frame - 1) / 15; "video=<file>", from the sidecar's folder, where the movie plays another movie's video and has no
## .ogv of its own). The video is drawn in the movie picture's place, scaled to it (the video is the picture's 320 x 224
## at its own aspect); everything else stays the game's: its sound (the SPU's CD input), when the movie starts, ends or
## is skipped, the 2D layer over a field's movie. No file for a movie: the core's MDEC picture, as before.
const MOVIES := "out/movies"
var movies_folder := ""
var movie_video: VideoStreamPlayer
## The movie showing ("<source>/<NN>", "" none) and whether its replacement plays (its key then), the replacement's line,
## the movie frame shown last and when it changed (usec), and the measured drift (|video - line|, seconds) for the log.
var movie_key := ""
var movie_target := ""
var movie_replaced := false
var movie_offset := 0.0
var movie_rate := 1.0
var movie_frame_seen := 0
var movie_frame_at := 0
var movie_drift_worst := 0.0
var movie_drift_sum := 0.0
var movie_drift_count := 0
var movie_seeks := 0
var movie_catch_ups := 0
## Video time is held to the core's movie frame within this (2 frames of a 30 fps video): ahead, the video waits;
## behind, it plays faster until it is back (_sync_movie); more than MOVIE_SEEK_BEHIND behind, it seeks.
const MOVIE_TOLERANCE := 2.0 / 30.0
const MOVIE_SEEK_BEHIND := 3.0
## hdlog=<csv> (for checks): a line per built frame (its pictures waiting, sprite pieces from VRAM, loads), and at the end
## <csv>.keys.csv: each picture's key, kind, when it was first wanted and when it was ready (game frames and ms).
var hd_log: FileAccess
var hd_wanted_at := {}
var hd_ready_at := {}
var hd_sync_usec_longest := 0
var hd_sync_loaded := 0
## When the live _process began (usec): a frame waits for its new pictures only while the process stays within a quarter
## of the sound's lead (the rest is the frame's own work and its drawing), so a burst of new pictures (a map's first frames)
## never starves the sound; the pictures past that load on the workers and the frame draws VRAM's texels for them meanwhile.
var process_started := 0
var hd_sync_deferred := 0
## The shaders' warm-up (_warm_up): its mesh, and the rendered frames left before the game starts.
const WARM_FRAMES := 3
var warm_instance: MeshInstance3D
var warm_frames := 0
## gap_ms=<n> (for checks): process gaps longer than this are printed too, not only those longer than the sound's lead.
var gap_report_usec := 0
## The last live _process: its game frames and build, its uploads (usec), for the stall lines.
var last_build_usec := 0
var last_upload_usec := 0
## The screen the 2D layer is laid on (320 x 224, or 320 x 240 for the Movie program and the notice).
var screen_size := Vector2i(320, 224)
## The movie picture and the field's picture of the screen last taken into their textures.
var movie_shown := -1
var cover_taken := 0
var lit := true
var hd := true
var blob := true
## F7, the shell's brightening of dark places (the game's own picture is that dark: its night textures and colours, measured
## out/fix_1115/C): over the whole game picture (the 3D scene and the game's 2D layer; not the shell's own lines), a curve
## of the brightest channel, y + s * y * (1 - y)^8, the colour kept: the shadows rise (24/255 -> 40 at "слабо", 57 at
## "сильнее"; 77 -> 84 / 90), from the middle up nothing to see (128 -> 129 / 129), white and black stay. Levels off / weak / stronger; weak unless the
## player chose another (kept in user://settings.cfg, only when F7 is pressed). dark=0|1|2 on the command line overrides it;
## runs with a script, a shot or quit_after take dark= or "weak", never the player's saved choice.
const DARK_STRENGTHS := [0.0, 1.5, 3.0]
const DARK_NAMES := ["выкл", "слабо", "сильнее"]
const SETTINGS_FILE := "user://settings.cfg"
var dark_level := 1
var dark_layer: CanvasLayer
## F8, the battle effects' flashes: the whole screen brightened for a few frames as an attack or an Ether lands. Measured
## (out/flash): the battle frame's fade layer, an untextured tile over the whole screen adding a colour (white or near it,
## mode 1 add or 3 add a quarter), started by an effect's script (FBattleShowFade::bFromEffect). The bridge draws its colour
## whole, at a share or not at all (FSession::SetBattleFlashes: the rule Weltall's own setting EBattleFlashes uses);
## every other fade (the battle's start, an escape, an event, any darkening, fades outside battle) stays as the game draws
## it. Levels: 2 as in the game (the default), 1 weak, 0 off; kept in user://settings.cfg when F8 is pressed, flash= on the
## command line overrides it; runs with a script, a shot or quit_after take flash= or 2, never the player's saved choice.
const FLASH_NAMES := ["выкл", "слабо", "как в игре"]
var flash_level := 2
var flash_log := false
var last_fade := PackedInt32Array()
## buttonlog=<file> (for checks): each scripted game frame's buttons, written at the end as a script
## (_script_of) - the same frames replayed by any build of the shell, with @snap where wanted.
var button_log := ""
var buttons_run := PackedInt32Array()
var pack_path := PACK
var pack_read := false
var shaders := {}
var materials := {}
var textures := {}
var page_loads := -1
## Live play: vertical blanks due and not yet run in a frame (the core's FTickClock counts them from real time).
var vblanks_due := 0
var script_steps: Array = []
var shot_path := ""
## shot_now=1: the shot as the frame stands, without waiting for the pictures still loading.
var shot_now := false
var save_state_path := ""
## Where F5 saves states and F9 loads the newest of them.
var states_folder := ""
## F6's frame reports (_frame_report): reports=<folder>, by default out/frame_reports; one being made (the game stands).
var reports_folder := ""
var reporting := false
## The disc played, as the report names it (the translation's image, or the games folder's USA disc).
var disc_played := ""
## F6 goes back to the newest state the bridge took at a quiet moment (where F5 could save) once this many game frames
## had run since the last (core.set_rolling_state). Every frame: measured live (map 316, 20 s, 564 captures) a capture
## takes 11 us on average, 54 us at most, a try where the game is not quiet under 5 us - nothing beside a 33 ms frame,
## and the state is then the last quiet frame before a cutscene.
const ROLLING_EVERY := 1
## The shell's own short notes (F5, F9): a label over everything, hidden when its time is up. Shown in live play, or with notes=1.
var note: Label
var note_until := 0
## The layer of the shell's own lines (the notes, the disc's line): hidden while F6 takes its shots (_frame_report), so a
## report's pictures hold the game's picture alone.
var shell_layer: CanvasLayer
var notes_shown := true
## A disc the game waits on that the bridge has not found (info.disc_wanted): a line under the notes saying which image
## to put where, for as long as it is missing (_follow_disc); the disc it was about.
var disc_note: Label
var disc_noted := 0
## A scripted @snap: shots taken so far, and one being taken (the script waits for it).
var snaps := 0
var snapping := false
var log_frames := false
var frames_run := 0
## The heard sound (live play): the generator, its playback, its ring's room when empty, how far ahead the sound is made.
var want_sound := false
var sound_player: AudioStreamPlayer
var sound_playback: AudioStreamGeneratorPlayback
var sound_room := 0
var sound_lead := 0
var sound_pushed := 0
## Underruns of the playbacks before this one (a state loaded starts the playback anew).
var skips_before := 0
## quit_after: the live run's length, when it began (usec), game frames stepped in it, the longest wait between two
## _process calls (usec).
var quit_after := 0.0
## at=: the live run's timed presses of F5 / F9, [usec after the start, action], soonest first.
var live_actions: Array = []
## at=<s>:hold=<buttons> (for checks): buttons held in live play as if pressed.
var live_hold := 0
var live_started := 0
var live_frames := 0
## at=<s>:snap (live play, for checks): where the window's shots go (shot_dir=, by default out/shots/live).
var live_shot_dir := ""
## The program, map and screen last drawn ("program/map/screen"), printed when they change.
var last_place := ""
## The live shots being encoded on workers: waited for before quitting (an unwaited task at exit crashes the engine).
var live_shot_tasks: Array = []
## pads=0: the gamepads are not read (live checks).
var pads_read := true
## At the end of the live run's first second: [usec, game frames, sound frames pushed, underruns].
var first_second: Array = []
var longest_gap := 0
var last_process := 0
## The cheat panel (F1): its layer, whether it is open (the game stands), its controls by name.
var cheat_layer: CanvasLayer
var cheat_open := false
var cheat_ui := {}
## Turbo: turbo=<N> (or at= turbo<N>) always runs N times the game's pace, Tab held TURBO_KEY_RATE; the rate the bridge has.
const TURBO_KEY_RATE := 4
var turbo_always := 1
var turbo_rate := 1
## The inventory's lists as the bridge numbers them (FSession::CheatItems).
const ITEM_LISTS := ["Предметы", "Оружие", "Аксессуары", "Оружие гиров", "Части гиров"]


func _ready() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		args[pair[0]] = pair[1] if pair.size() > 1 else "1"
	unattended = args.has("script") or args.has("script_file") or args.has("shot") or args.has("quit_after") or args.has("story_shots")
	# Every relative location on the command line is under one root: root=<folder>, by default the xeno_port folder (the
	# development tree); the mod folder's batch gives its own (games, pack, saves, states, alias_index, movies under it).
	if args.has("root"):
		root_folder = String(args["root"]).replace("\\", "/").rstrip("/")
	var games := _from_root(args.get("games", "weltall/Games"))
	# The game's text: lang=ru (the default) plays the Russian translation's disc 1 (rus=<.cue/.bin>; its own text, font,
	# pictures and sound), lang=en the USA disc as it is; lang=auto finds the discs in the games folder by their content
	# (core.survey_discs: whatever the files are called): the translation's disc 1 if it is there, else USA disc 1.
	var lang: String = args.get("lang", "ru")
	var translation := ""
	if lang == "auto":
		var survey: Dictionary = core.survey_discs(games)
		print("xeno: discs in ", games, ": ", survey)
		translation = survey.get("russian_disc_1", "")
		if translation.is_empty() and String(survey.get("usa_disc_1", "")).is_empty():
			_fail_in_window("В папке с образами нет диска 1 Xenogears: ни русского перевода, ни американского (USA).\n%s\n\nПоложите туда образ (BIN+CUE или CHD) и запустите игру снова. Подробнее — в ПРОЧТИ.txt." % games.replace("/", "\\"))
			return
	elif lang == "ru":
		translation = _from_root(args.get("rus", RUSSIAN_DISC))
		if not FileAccess.file_exists(translation):
			push_warning("xeno: no Russian disc at " + translation + ": the USA text plays")
			translation = ""
	var error := core.open(games, translation)
	print("xeno: language ", core.language())
	disc_played = translation if not translation.is_empty() else "USA disc 1 in " + games
	hd = args.get("hd", "1") == "1"
	lit = args.get("light", "1") == "1"
	blob = args.get("blob", "1") == "1"
	pack_path = _from_root(args.get("pack", PACK))
	alias_on = args.get("alias", "1") != "0"
	alias_index = _from_root(args.get("alias_index", ALIAS_INDEX))
	alias_table = _from_root(args.get("alias_table", ALIAS_TABLE))
	alias_record = _from_root(args["alias_record"]) if args.has("alias_record") else ""
	movies_folder = _from_root(args.get("movies", MOVIES))
	if error.is_empty() and hd:
		# No pack (its folder missing or unreadable): the game plays with the original's pictures, and says so.
		var pack_error := _read_pack()
		if not pack_error.is_empty():
			push_warning("xeno: " + pack_error + ": the original's pictures")
			hd = false
			pack_missing = true
	core.set_options(hd, blob or not lit, lit)
	if error.is_empty():
		# The game's own saves (the File screen's, the title's Continue), never the user's memory card copies.
		# saves=<folder> (for checks): another store than the player's.
		var saves_error := core.set_save_folder(_from_root(args.get("saves", "out/saves/game")))
		if not saves_error.is_empty():
			push_error("xeno: saves: " + saves_error)
	states_folder = _from_root(args.get("states", "out/states"))
	reports_folder = _from_root(args.get("reports", "out/frame_reports"))
	# F6's state to go back to: taken at quiet moments as the game plays (scripts too: their @report has one).
	# rolling=<N> (for checks): another spacing, 0 none.
	core.set_rolling_state(int(args.get("rolling", str(ROLLING_EVERY))))
	# Pictures are drawn once the display has loaded them; until then the original's texels from VRAM.
	core.set_lazy_textures(true)
	for source in VRAM_SOURCES:
		var blank := Image.create_empty(1024, core.vram_rows(), false, Image.FORMAT_RG8)
		vram_textures.append(ImageTexture.create_from_image(blank))
		vram_stamps.append(-1)
	vram_texture = vram_textures[0]
	if error.is_empty() and args.get("boot", "0") == "1":
		# The console powered on: the kernel's notice, the opening movie, the title.
		error = core.power_on()
	elif error.is_empty() and args.has("card"):
		# A save of a memory card image: card=<file> lists them, card=<file> slot=N goes on from one.
		var slot := int(args.get("slot", "-1"))
		error = core.load_card(_from_root(args["card"]), slot)
		if slot < 0:
			print(error)
			set_process(false)
			get_tree().quit()
			return
	elif error.is_empty() and args.has("state"):
		# A save state the game made (F5): state=<file>, relative to the xeno_port folder.
		error = core.load_state(_from_root(args["state"]))
		# state=<file> map=<N> (for checks): that map entered from the loaded game's point of the story.
		if error.is_empty() and args.has("map"):
			error = core.enter_field_keeping(int(args["map"]))
	elif error.is_empty():
		error = core.enter_field(int(args.get("map", "4")))
	if not error.is_empty():
		push_error("xeno: " + error)
		_fail_in_window("Игра не запустилась: " + error)
		return
	# encounters=0: random battles off from the start (Weltall's own setting, kept over F9 and the title).
	if args.get("encounters", "1") == "0":
		_cheat("encounters:0")
	turbo_always = clampi(int(args.get("turbo", "1")), 1, 8)
	# Fast-forward without drawing, Cross pressed every other frame: a new game (map 4) reaches its first control.
	for frame in int(args.get("ff", "0")):
		error = core.step(1 << PAD.cross if frame % 2 == 0 else 0, 128, 128, false)
		if not error.is_empty():
			push_error("xeno: fast-forward frame %d: %s" % [frame, error])
			break
	print("xeno: after fast-forward: ", core.info())
	shot_path = args.get("shot", "")
	shot_now = args.get("shot_now", "0") == "1"
	# With a script: savestate=<file> saves the game as F5 does once the script has run (for checks).
	save_state_path = _from_root(args["savestate"]) if args.has("savestate") else ""
	log_frames = args.has("log")
	hd_sync = args.get("hdsync", "1") != "0"
	if args.has("hdlog"):
		hd_log = FileAccess.open(_from_root(args["hdlog"]), FileAccess.WRITE)
		hd_log.store_line("usec,game_frame,pass,waiting,sprite_pieces,sprite_hd,sprite_partial,sprite_vram,sprite_waiting,screen_textured,screen_hd,screen_waiting,loading_pages,loading_pictures,sync_loaded,sync_usec")
	# script_file=<file>: the script read from a file (an F6 report's inputs.txt), its lines joined by commas.
	var script_text: String = args.get("script", "")
	if args.has("script_file"):
		script_text = FileAccess.get_file_as_string(_from_root(args["script_file"])).strip_edges().replace("\r", "").replace("\n", ",")
	for step in script_text.split(",", false):
		if step.begins_with("@"):
			script_steps.append([0, 0, step.substr(1)])
			continue
		var part := step.split(":")
		script_steps.append([int(part[0]), _buttons_of(part[1] if part.size() > 1 else "none")])
	# story_shots=<folder> (for checks): every save state of the folder in name order (story_only=<text>: those whose names
	# hold it) loaded in turn, story_frames=N frames played with no buttons, then a shot <shot_dir>/<state's name>.png
	# once its pictures have loaded.
	if args.has("story_shots"):
		var folder := _from_root(args["story_shots"])
		var out_dir := _from_root(args.get("shot_dir", "out/shots/task7/story"))
		DirAccess.make_dir_recursive_absolute(out_dir)
		var names := DirAccess.get_files_at(folder)
		names.sort()
		var only: String = args.get("story_only", "")
		for name in names:
			if not name.ends_with(".state") or (not only.is_empty() and not name.contains(only)):
				continue
			script_steps.append([0, 0, "state=" + folder.path_join(name)])
			script_steps.append([int(args.get("story_frames", "120")), 0])
			script_steps.append([0, 0, "snapto=" + out_dir.path_join(name.get_basename() + ".png")])
		if shot_path.is_empty():
			shot_path = out_dir.path_join("_end.png")

	camera = Camera3D.new()
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.near = 0.02
	camera.far = 400.0
	add_child(camera)
	environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(1, 1, 1)
	environment.ambient_light_energy = float(args.get("ambient", "0.55"))
	environment.ssao_enabled = lit
	environment.ssao_radius = 0.35
	environment.ssao_intensity = 1.6
	sun = DirectionalLight3D.new()
	sun.light_energy = float(args.get("sun", "0.75"))
	sun.shadow_enabled = true
	sun.shadow_bias = 0.03
	sun.shadow_normal_bias = 1.0
	sun.directional_shadow_max_distance = 40.0
	sun.visible = lit
	add_child(sun)
	_show_title()
	_log_pads()
	Input.joy_connection_changed.connect(_log_pads)
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)

	var world := MeshInstance3D.new()
	world.mesh = world_mesh
	# world=0 (for checks): the 2D layer alone, over the clear colour.
	world.visible = args.get("world", "1") == "1"
	add_child(world)
	world_node = world
	flat_layer = CanvasLayer.new()
	flat_layer.layer = 1
	# layer=0 (for checks): the frame without its 2D layer.
	flat_layer.visible = args.get("layer", "1") == "1"
	layer_runs = int(args.get("layer_runs", "-1"))
	if args.has("as_blend"):
		var modes: PackedStringArray = String(args["as_blend"]).split(":")
		blend_remap = [int(modes[0]), int(modes[1])]
	for run in String(args.get("checks", "")).split("+", false):
		check_runs.append(int(run))
	flat_f = int(args.get("flat_f", "-1"))
	if args.has("clear"):
		var rgb: PackedStringArray = String(args["clear"]).split(",")
		clear_override = Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	add_child(flat_layer)
	# F7's brightening of dark places: over the game's 3D picture and its 2D layer, under the cheat panel and the notes.
	var dark_from := "default"
	if args.has("dark"):
		dark_level = clampi(int(args["dark"]), 0, DARK_STRENGTHS.size() - 1)
		dark_from = "dark="
	elif not unattended:
		var settings := ConfigFile.new()
		if settings.load(SETTINGS_FILE) == OK:
			dark_level = clampi(int(settings.get_value("display", "dark", dark_level)), 0, DARK_STRENGTHS.size() - 1)
			dark_from = SETTINGS_FILE
	print("xeno: dark places brightened %d (%s, from %s)" % [dark_level, DARK_NAMES[dark_level], dark_from])
	dark_layer = CanvasLayer.new()
	dark_layer.layer = 2
	var dark_rect := ColorRect.new()
	dark_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	dark_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var dark_material := ShaderMaterial.new()
	dark_material.shader = _dark_shader()
	dark_rect.material = dark_material
	dark_layer.add_child(dark_rect)
	add_child(dark_layer)
	_apply_dark()
	# F8's battle flashes (the bridge draws them, FSession::SetBattleFlashes).
	var flash_from := "default"
	if args.has("flash"):
		flash_level = clampi(int(args["flash"]), 0, FLASH_NAMES.size() - 1)
		flash_from = "flash="
	elif not unattended:
		var kept := ConfigFile.new()
		if kept.load(SETTINGS_FILE) == OK:
			flash_level = clampi(int(kept.get_value("display", "flash", flash_level)), 0, FLASH_NAMES.size() - 1)
			flash_from = SETTINGS_FILE
	core.set_battle_flashes(flash_level)
	flash_log = args.get("flashlog", "0") == "1"
	button_log = _from_root(args["buttonlog"]) if args.has("buttonlog") else ""
	print("xeno: battle flashes %d (%s, from %s)" % [flash_level, FLASH_NAMES[flash_level], flash_from])
	# The screen wave's layer: over the 3D picture, under the 2D layer (the wave takes the scene alone, FieldSceneRendering.cpp).
	var wave_layer := CanvasLayer.new()
	wave_layer.layer = 0
	wave_node = MeshInstance2D.new()
	wave_node.mesh = wave_mesh
	var wave_material := ShaderMaterial.new()
	wave_material.shader = _wave_shader()
	wave_node.material = wave_material
	wave_node.visible = false
	wave_layer.add_child(wave_node)
	add_child(wave_layer)
	quit_after = float(args.get("quit_after", "0"))
	live_shot_dir = _from_root(args.get("shot_dir", "out/shots/live"))
	for timed in String(args.get("at", "")).split(",", false):
		var pair := timed.split(":")
		live_actions.append([int(float(pair[0]) * 1e6), pair[1] if pair.size() > 1 else ""])
	gap_report_usec = int(float(args.get("gap_ms", "0")) * 1000.0)
	want_sound = script_steps.is_empty() and shot_path.is_empty() and args.get("sound", "1") != "0"
	# pads=0 (live checks): the gamepads are not read (a stray press would skip a movie being measured).
	pads_read = args.get("pads", "1") != "0"
	notes_shown = (script_steps.is_empty() and shot_path.is_empty()) or args.get("notes", "0") == "1"
	var layer := CanvasLayer.new()
	layer.layer = 100
	add_child(layer)
	shell_layer = layer
	note = Label.new()
	note.position = Vector2(16, 12)
	note.add_theme_font_size_override("font_size", 22)
	note.add_theme_color_override("font_color", Color(1, 1, 0.85))
	note.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	note.add_theme_constant_override("outline_size", 6)
	note.visible = false
	layer.add_child(note)
	disc_note = note.duplicate()
	disc_note.position = Vector2(16, 48)
	layer.add_child(disc_note)
	_build_cheat_panel()
	_warm_up()


## Every shader the drawing can use (each layer, source and blend mode) drawn once before the game's clock and sound
## start: Godot compiles a shader's pipelines the first time it draws it, which stalled the first frames of a map or a
## battle by up to a quarter of a second. One triangle each in front of the camera, every pixel discarded (blank VRAM,
## a transparent picture), shadows cast; WARM_FRAMES rendered frames, then it goes.
func _warm_up() -> void:
	textures["warm:"] = ImageTexture.create_from_image(Image.create_empty(1, 1, false, Image.FORMAT_RGBA8))
	var mesh := ArrayMesh.new()
	var made: Array = []
	for layer in ["world", "battle"]:
		for texture in ["", "warm:"]:
			for blend in BLENDS.size():
				var arrays := []
				arrays.resize(Mesh.ARRAY_MAX)
				arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-0.1, -0.1, -1.0), Vector3(0.1, -0.1, -1.0), Vector3(0.0, 0.1, -1.0)])
				arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3(0, 0, 1), Vector3(0, 0, 1), Vector3(0, 0, 1)])
				arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color(0.5, 0.5, 0.5), Color(0.5, 0.5, 0.5), Color(0.5, 0.5, 0.5)])
				arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
				# Page (0, 0) 4-bit of blank VRAM: every texel transparent; a battle's order 0.5; no texel range, no drawing area.
				var c0 := PackedFloat32Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
				var c1 := PackedFloat32Array([0, 0, 0, 0.5, 0, 0, 0, 0.5, 0, 0, 0, 0.5])
				var c2 := PackedFloat32Array([-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
				arrays[Mesh.ARRAY_CUSTOM0] = c0
				arrays[Mesh.ARRAY_CUSTOM1] = c1
				arrays[Mesh.ARRAY_CUSTOM2] = c2
				arrays[Mesh.ARRAY_CUSTOM3] = c2
				var format := (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT) | (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT) \
					| (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM2_SHIFT) | (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM3_SHIFT)
				mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, format)
				made.append(_material(layer, blend, texture, 0, 0))
	for surface in made.size():
		mesh.surface_set_material(surface, made[surface])
	warm_instance = MeshInstance3D.new()
	warm_instance.mesh = mesh
	add_child(warm_instance)
	# The 2D layer's shaders: a triangle each on the canvas, every pixel discarded the same way.
	var flat_mesh := ArrayMesh.new()
	var flat_arrays := []
	flat_arrays.resize(Mesh.ARRAY_MAX)
	flat_arrays[Mesh.ARRAY_VERTEX] = PackedVector2Array([Vector2(0, 0), Vector2(8, 0), Vector2(0, 8)])
	flat_arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color(0.5, 0.5, 0.5), Color(0.5, 0.5, 0.5), Color(0.5, 0.5, 0.5)])
	flat_arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
	flat_arrays[Mesh.ARRAY_CUSTOM0] = PackedFloat32Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
	flat_arrays[Mesh.ARRAY_CUSTOM1] = PackedFloat32Array([-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
	flat_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, flat_arrays, [], {}, (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT) \
		| (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT) | Mesh.ARRAY_FLAG_USE_2D_VERTICES)
	for texture in ["", "warm:"]:
		for blend in BLENDS.size():
			for part in (2 if blend == 3 else 1):
				var node := MeshInstance2D.new()
				node.mesh = flat_mesh
				node.material = _flat_material(blend, texture, -1, 0, part)
				flat_layer.add_child(node)
				flat_warm.append(node)
	warm_frames = WARM_FRAMES


## The live game heard, as Weltall's UGameSoundSubsystem plays it (Source/Weltall/Private/Audio/GameSoundSubsystem.cpp):
## one output for the whole game, the core's own 44,100 Hz stereo, made as the device takes it. Here the main thread
## makes it right after the frames it steps, keeping it core.sound_lead_frames() ahead of the device: the time of the
## longest stall the game's clock rides through (4 vertical blanks), so a stall the game takes in its stride the sound
## does too, and after a longer one both drop the same time and stay in step.
func _start_sound() -> void:
	sound_lead = core.sound_lead_frames()
	var generator := AudioStreamGenerator.new()
	generator.mix_rate_mode = AudioStreamGenerator.MIX_RATE_CUSTOM
	generator.mix_rate = core.sound_rate()
	# Godot rounds the ring up to a power of two: room for the lead and more.
	generator.buffer_length = float(sound_lead) / core.sound_rate()
	sound_player = AudioStreamPlayer.new()
	sound_player.stream = generator
	add_child(sound_player)
	sound_player.play()
	sound_playback = sound_player.get_stream_playback()
	sound_room = sound_playback.get_frames_available()
	var error := core.hear(sound_lead)
	if not error.is_empty():
		push_error("xeno: sound: " + error)
	_feed_sound()
	print("xeno: sound heard, %d Hz, made %d frames (%.1f ms) ahead, ring %d frames" % [core.sound_rate(), sound_lead, sound_lead * 1000.0 / core.sound_rate(), sound_room])


## The generator's underruns in this run, every playback's.
func _skips() -> int:
	return skips_before + (sound_playback.get_skips() if sound_playback != null else 0)


## The sound made up to its lead over what the device has taken.
func _feed_sound() -> void:
	if sound_playback == null:
		return
	var want := sound_lead - (sound_room - sound_playback.get_frames_available())
	if want > 0:
		sound_playback.push_buffer(core.render_sound(want))
		sound_pushed += want


func _process(delta: float) -> void:
	if note != null and note.visible and Time.get_ticks_msec() >= note_until:
		note.visible = false
	if warm_frames > 0:
		# The shaders are being compiled (_warm_up): the game has not started yet.
		warm_frames -= 1
		if warm_frames == 0:
			warm_instance.queue_free()
			warm_instance = null
			for node in flat_warm:
				node.queue_free()
			flat_warm.clear()
		return
	if not script_steps.is_empty() or not shot_path.is_empty():
		_play_script()
		return
	var now := Time.get_ticks_usec()
	if reporting:
		# F6's report is being made: the game stands as under the cheat panel (no frames, no time let through to its
		# clock, the sound paused where it is); the wait is not a stall of the game's.
		_sync_movie(true)
		last_process = now
		return
	process_started = now
	if live_started == 0:
		# The live game begins: its clock and its sound start together.
		live_started = now
		if want_sound:
			_start_sound()
		if pack_missing:
			_show_note("HD-текстур нет (папка pack): игра идёт с оригинальной графикой PlayStation")
			note_until = Time.get_ticks_msec() + 10000
	elif last_process > 0:
		longest_gap = maxi(longest_gap, now - last_process)
		# A wait longer than the sound's lead: the device ran out of sound (and the game's clock dropped the time).
		if sound_playback != null and ((now - last_process) * core.sound_rate() > sound_lead * 1000000 or (gap_report_usec > 0 and now - last_process > gap_report_usec)):
			print("xeno: stall %.1f ms before frame %d (the process before: frames and build %.1f ms, uploads %.1f ms)" % [(now - last_process) / 1000.0, frames_run, last_build_usec / 1000.0, last_upload_usec / 1000.0])
	last_process = now
	if not live_actions.is_empty() and now - live_started >= live_actions[0][0]:
		var action: String = live_actions.pop_front()[1]
		if action == "save":
			_save_state()
		elif action == "load":
			_load_latest_state()
		elif action == "panel":
			_toggle_cheat_panel()
		elif action == "report":
			_frame_report()
		elif action == "dark":
			# F7 pressed (for checks: the level kept for the next start).
			_next_dark()
		elif action == "flash":
			# F8 pressed (for checks: the level kept for the next start).
			_next_flash()
		elif action.begins_with("hold="):
			# Buttons held from now on as a player holds them (for checks of live play: a run, a walk); hold=none lets go.
			live_hold = _buttons_of(action.substr(5))
		elif action == "snap":
			# The window as it is now (live play, for checks): <shot_dir>/live_<ms>.png, with the movie's frame in the log.
			DirAccess.make_dir_recursive_absolute(live_shot_dir)
			var path := live_shot_dir.path_join("live_%06d.png" % ((now - live_started) / 1000))
			# Encoded on a worker: the sound's lead (67 ms) is shorter than a PNG of the window takes.
			var shot := get_viewport().get_texture().get_image()
			live_shot_tasks.append(WorkerThreadPool.add_task(func() -> void: shot.save_png(path), false, "xeno live shot"))
			var shown := core.info()
			print("xeno: snap %s at %.3f s: program %d, map %d, screen %d, movie %s %d frame %d, video %.3f s" % [path, (now - live_started) / 1e6, shown.get("program", -1),
				shown.get("map", -1), shown.get("screen", -1), shown.get("movie_source", ""), shown.get("movie_number", -1), shown.get("movie_shown_frame", 0),
				movie_video.stream_position if movie_replaced else -1.0])
		elif action.begins_with("turbo"):
			turbo_always = clampi(int(action.substr(5)), 1, 8)
			print("xeno: turbo %d at %.3f s, game frames %d, sound frames pushed %d, underruns %d" % [turbo_always, (now - live_started) / 1e6, live_frames, sound_pushed, _skips()])
	if cheat_open:
		# The cheat panel is open: the game stands (no frames, no sound made, the clock lets no time through: the playback
		# is paused and goes on from where it stood when the panel closes); only the pictures go on loading.
		_sync_movie(true)
		_pump_textures(TEXTURE_BUDGET_USEC, now)
		return
	_sync_movie(false)
	# Turbo (Tab held, or turbo=): the bridge runs the game that many times its pace where Weltall's fast-forward would.
	var turbo := maxi(turbo_always, TURBO_KEY_RATE if Input.is_physical_key_pressed(KEY_TAB) else 1)
	if turbo != turbo_rate:
		turbo_rate = turbo
		core.cheat("turbo:%d" % turbo)
	# Real time brings vertical blanks as Weltall's game screen counts them (FTickClock: after a stall at most 4 at once,
	# the rest dropped); a frame runs once it has its vertical blanks (GameLoopScreen.cpp, FGameLoopScreen::Update).
	vblanks_due += core.vblanks_due(delta)
	var pace := core.game_pace()
	var runs := core.program_runs()
	var stepped := false
	while is_processing() and vblanks_due >= core.vblanks_per_frame():
		vblanks_due -= core.vblanks_per_frame()
		_step(_held())
		live_frames += 1
		stepped = true
		# As Weltall's game screen: the extra frames of a fast-forward never spill into another program or a stretch
		# that runs at the game's own pace (GameLoopScreen.cpp, Update).
		if pace > 1 and (core.program_runs() != runs or core.game_pace() == 1):
			vblanks_due = 0
			break
	if stepped:
		_refresh()
	_feed_sound()
	last_build_usec = Time.get_ticks_usec() - now
	# Pictures loaded meanwhile go up to the GPU within the frame's budget; the next build draws them.
	_pump_textures(TEXTURE_BUDGET_USEC, now)
	var fed := Time.get_ticks_usec()
	if first_second.is_empty() and fed - live_started >= 1000000:
		# The first second (the map's pages are built in it: the frame stalls) apart, for the steady figures.
		first_second = [fed, live_frames, sound_pushed, _skips()]
	if quit_after > 0.0 and fed - live_started >= int(quit_after * 1e6):
		if first_second.is_empty():
			first_second = [live_started, 0, 0, 0]
		var rate: float = core.sound_rate()
		var seconds := (fed - live_started) / 1e6
		var skips := _skips()
		var steady: float = (fed - first_second[0]) / 1e6
		var steady_pushed: int = sound_pushed - first_second[2]
		print("xeno: quit_after %.3f s, game frames %d, sound frames pushed %d (rate x seconds %d, %+.2f %%), underruns %d; after the first second: %.3f s, game frames %d, pushed %d (rate x seconds %d, %+.2f %%), underruns %d; longest process gap %.1f ms; pictures uploaded %d (longest frame's uploads %.1f ms), still loading %d, failed %d; loaded on the frame drawing them %d (longest wait %.1f ms), left to the workers past the frame's time %d" % [
			seconds, live_frames, sound_pushed, int(rate * seconds), 100.0 * (sound_pushed / (rate * seconds) - 1.0), skips,
			steady, live_frames - first_second[1], steady_pushed, int(rate * steady), 100.0 * (steady_pushed / (rate * steady) - 1.0), skips - first_second[3],
			longest_gap / 1000.0, uploads_total, upload_usec_longest / 1000.0, loading.size(), failed.size(), hd_sync_loaded, hd_sync_usec_longest / 1000.0, hd_sync_deferred])
		print("xeno: rolling state (F6) ", core.rolling_stats())
		set_process(false)
		_finish_loading()
		get_tree().quit()


func _play_script() -> void:
	if snapping or reporting:
		return
	while not script_steps.is_empty() and script_steps[0].size() > 2:
		# An action between frames.
		var action: String = script_steps.pop_front()[2]
		match action:
			"save":
				_save_state()
			"load":
				_load_latest_state()
			"snap":
				snaps += 1
				_snap(shot_path.get_basename() + "_%d.png" % snaps)
				return
			"report":
				# F6 pressed (the script waits for the report).
				_frame_report()
				return
			_:
				if action.begins_with("state="):
					# Another save state over the game running, as F9 loads one.
					_load_state_file(_from_root(action.substr(6)))
				elif action.begins_with("snapto="):
					_snap(_from_root(action.substr(7)))
					return
				elif action.begins_with("cheat="):
					# A cheat as the panel does it (core.cheat), the panel's state printed after it.
					_cheat(action.substr(6))
				elif action.begins_with("arena="):
					# For checks: the running field asks for the Battling arena with FE BF's six bytes, dot-separated
					# (from.kind.gear.gear.wins.level), as Weltall's arena audit asks (core.ask_battling).
					var bytes := PackedInt32Array()
					for part in action.substr(6).split("."):
						bytes.append(int(part))
					print("xeno: arena asked %s: '%s'" % [action.substr(6), core.ask_battling(bytes)])
				elif action.begins_with("movie="):
					# For checks: the running field asks for a movie of the disc in the drive full screen, as FE 60 does:
					# @movie=<number>.<end frame> (core.ask_field_movie).
					var parts := action.substr(6).split(".")
					print("xeno: movie asked %s: '%s'" % [action.substr(6), core.ask_field_movie(int(parts[0]), int(parts[1]) if parts.size() > 1 else 1)])
				elif action.begins_with("map="):
					# For checks: that map entered from the running game's point of the story (as state= map= does at the start).
					var entered := core.enter_field_keeping(int(action.substr(4)))
					print("xeno: map %s entered: '%s'" % [action.substr(4), entered])
					_forget_game()
				elif action.begins_with("dark="):
					# F7's level for the shots after it (not kept): @dark=0|1|2.
					dark_level = clampi(int(action.substr(5)), 0, DARK_STRENGTHS.size() - 1)
					_apply_dark()
				elif action.begins_with("flash="):
					# F8's level for the frames after it (not kept): @flash=0|1|2.
					flash_level = clampi(int(action.substr(6)), 0, FLASH_NAMES.size() - 1)
					core.set_battle_flashes(flash_level)
					_show_title()
				elif action == "panel" or action.begins_with("panel="):
					# The cheat panel shown or hidden (for shots), on a tab: @panel=<0-2>.
					_toggle_cheat_panel(int(action.substr(6)) if action.begins_with("panel=") else -1)
				else:
					push_error("xeno: unknown script action @" + action)
	if script_steps.is_empty():
		_save_shot_and_quit()
		return
	var buttons: int = script_steps[0][1]
	if buttons & (1 << 16):
		buttons = buttons & 0xFFFF if script_steps[0][0] % 2 == 0 else 0
	_step(buttons)
	script_steps[0][0] -= 1
	if script_steps[0][0] <= 0:
		script_steps.pop_front()
		print("xeno: after step: ", core.info())
	_refresh()
	_pump_textures(TEXTURE_BUDGET_USEC, -1)


func _step(buttons: int) -> void:
	var error := core.step(buttons, 128, 128, false)
	frames_run += 1
	if not button_log.is_empty():
		buttons_run.append(buttons)
	if not error.is_empty():
		push_error("xeno: frame %d: %s" % [frames_run, error])
		set_process(false)
		# The game has stopped: nothing makes its sound any more.
		if sound_player != null:
			sound_player.stop()
			sound_playback = null
	elif log_frames:
		print("xeno: ", frames_run, " ", core.info())
	if flash_log:
		# flashlog=1 (for checks): the battle frame's fade layer [linked, mode, r, g, b, an effect's], a line when it changes.
		var info: Dictionary = core.info()
		var fade: PackedInt32Array = info.get("battle_fade", PackedInt32Array())
		if fade != last_fade:
			print("xeno: fade %d %s share %s program %d" % [frames_run, fade, info.get("battle_flash_share", 1.0), int(info.get("program", -1))])
			last_fade = fade


func _save_shot_and_quit() -> void:
	set_process(false)
	if not button_log.is_empty():
		var written := FileAccess.open(button_log, FileAccess.WRITE)
		if written != null:
			written.store_string(_script_of(buttons_run))
			written.close()
		print("xeno: buttonlog %s, %d frames" % [button_log, buttons_run.size()])
	# The shot shows the pack's pictures as the game would once they have loaded: the game waits (no frame steps) while
	# the frame is built again until no picture it asks for is still loading. shot_now=1 takes it at once instead.
	var waited := 0
	while not shot_now and waited < 1200:
		_pump_textures(1000000000)
		_refresh()
		_pump_textures(1000000000)
		if loading.is_empty() and int(core.info().waiting) == 0:
			break
		if loading.is_empty() and _only_failed_waiting():
			break
		waited += 1
		await get_tree().process_frame
	if waited > 0:
		print("xeno: shot waited %d frames for %d pictures (failed %d)" % [waited, uploads_total, failed.size()])
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(shot_path)
	if not save_state_path.is_empty():
		print("xeno: save state '", core.save_state(save_state_path), "'")
	print("xeno: shot ", shot_path, " ", core.info())
	# The field's open message windows as the core holds them (map, number in its table, codes), to check against the disc.
	for message in core.open_messages():
		print("xeno: message map %d index %d codes %s" % [message.map, message.index, PackedByteArray(message.codes).hex_encode()])
	# The 2D layer's runs as drawn: [blend, picture, VRAM source, unlit, drawing area, two passes] each.
	print("xeno: flat runs ", var_to_str(last_runs).replace("\n", " "))
	for run in check_runs:
		for variant in ["B", "R", "Fb", "Fw"]:
			layer_runs = run if variant == "B" else run + 1 if variant == "R" else -1
			flat_f = run if variant.begins_with("F") else -1
			world_node.visible = not variant.begins_with("F")
			clear_override = Color(0, 0, 0) if variant == "Fb" else Color(1, 1, 1) if variant == "Fw" else Color(-1, -1, -1)
			_refresh()
			await RenderingServer.frame_post_draw
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(shot_path.get_basename() + "_r%d_%s.png" % [run, variant])
		print("xeno: checked run ", run)
	_finish_loading()
	get_tree().quit()


## A shot of the frame as it stands, once the pictures it asks for have loaded (as the final shot waits); the script waits.
func _snap(path: String) -> void:
	snapping = true
	var waited := 0
	while not shot_now and waited < 1200:
		_pump_textures(1000000000)
		_refresh()
		_pump_textures(1000000000)
		if loading.is_empty() and (int(core.info().waiting) == 0 or _only_failed_waiting()):
			break
		waited += 1
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(path)
	print("xeno: snap ", path, " ", core.info())
	snapping = false


## Whether the pictures still drawn from VRAM are only those that could not be read (they will never load).
func _only_failed_waiting() -> bool:
	return not failed.is_empty() and loading.is_empty() and core.wanted_textures().size() == 0


## The pictures loaded on worker threads: those the bridge asked for start loading; those built go up to the GPU while the
## frame's budget lasts (at least one), and the bridge is told they are ready. A page built for a scene before the current
## one is dropped.
func _pump_textures(budget_usec: int, frame_started: int = -1) -> void:
	for key in core.wanted_textures():
		_start_picture(key)
	last_upload_usec = 0
	if loading.is_empty():
		return
	var started := Time.get_ticks_usec()
	# The frame's budget counts from its start (its game frames and build), or from now.
	var since := frame_started if frame_started >= 0 else started
	if started - since >= budget_usec:
		return
	var uploaded := 0
	for key in loading.keys():
		var entry: Array = loading[key]
		if not WorkerThreadPool.is_task_completed(entry[1]):
			continue
		WorkerThreadPool.wait_for_task_completion(entry[1])
		var image: Image = core.take_built(entry[0])
		loading.erase(key)
		if String(key).begins_with("page:") and entry[2] != page_loads:
			continue
		if image == null or image.has_meta("failed"):
			failed[key] = true
			continue
		textures[key] = ImageTexture.create_from_image(image)
		core.mark_texture_ready(key)
		_note_ready(key)
		uploaded += 1
		if Time.get_ticks_usec() - since >= budget_usec:
			break
	if uploaded > 0:
		uploads_total += uploaded
		last_upload_usec = Time.get_ticks_usec() - started
		upload_usec_longest = maxi(upload_usec_longest, last_upload_usec)


## A picture the bridge asked for starts building on a worker (unless it is loaded, loading or could not be read).
func _start_picture(key: String) -> void:
	if hd_log != null and not hd_wanted_at.has(key):
		hd_wanted_at[key] = [frames_run, Time.get_ticks_usec()]
	if textures.has(key) or loading.has(key) or failed.has(key):
		return
	var job := core.texture_job(key)
	# The pack's own pictures (small, waited for by the frame drawing them, hd_sync) go ahead of the scenery's pages.
	var task := WorkerThreadPool.add_task(core.build_job.bind(job), hd_sync and not key.begins_with("page:"), "xeno picture")
	loading[key] = [job, task, page_loads]


func _note_ready(key: String) -> void:
	if hd_log != null and not hd_ready_at.has(key):
		hd_ready_at[key] = [frames_run, Time.get_ticks_usec()]


## The pack's own pictures the frame just built asked for, loaded now (hd_sync): every one is dispatched to the workers,
## then each is waited for, uploaded and marked ready; the scenery's pages go on loading as before. True when any was
## loaded (the frame is then built again with them).
func _load_pictures_now() -> bool:
	var now: Array = []
	for key in core.wanted_textures():
		_start_picture(key)
		if not String(key).begins_with("page:") and loading.has(key):
			now.append(key)
	if now.is_empty():
		return false
	var started := Time.get_ticks_usec()
	# Live play waits within a quarter of the sound's lead from the process's start; scripted runs wait for all.
	var until := process_started + sound_lead * 250000 / core.sound_rate() if script_steps.is_empty() and sound_lead > 0 else 0
	var loaded := false
	for key in now:
		var entry: Array = loading[key]
		if until > 0 and Time.get_ticks_usec() >= until:
			# Past the frame's time: the rest go up as the workers finish them (_pump_textures), VRAM's texels meanwhile.
			hd_sync_deferred += 1
			continue
		WorkerThreadPool.wait_for_task_completion(entry[1])
		var image: Image = core.take_built(entry[0])
		loading.erase(key)
		if image == null or image.has_meta("failed"):
			failed[key] = true
			continue
		textures[key] = ImageTexture.create_from_image(image)
		core.mark_texture_ready(key)
		_note_ready(key)
		hd_sync_loaded += 1
		loaded = true
	var spent := Time.get_ticks_usec() - started
	hd_sync_usec_longest = maxi(hd_sync_usec_longest, spent)
	last_upload_usec += spent
	return loaded


func _log_hd(pass_number: int, loaded: int, spent: int) -> void:
	if hd_log == null:
		return
	var info := core.info()
	var pages := 0
	for key in loading.keys():
		pages += 1 if String(key).begins_with("page:") else 0
	hd_log.store_line("%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d" % [Time.get_ticks_usec(), frames_run, pass_number,
		int(info.get("waiting", 0)), int(info.get("sprite_pieces", 0)), int(info.get("sprite_hd", 0)), int(info.get("sprite_partial", 0)),
		int(info.get("sprite_vram", 0)), int(info.get("sprite_waiting", 0)), int(info.get("screen_textured", 0)), int(info.get("screen_hd", 0)),
		int(info.get("screen_waiting", 0)), pages, loading.size() - pages, loaded, spent])


func _close_hd_log() -> void:
	if hd_log == null:
		return
	var path := hd_log.get_path_absolute()
	hd_log.close()
	var keys := FileAccess.open(path + ".keys.csv", FileAccess.WRITE)
	keys.store_line("key,kind,wanted_frame,wanted_usec,ready_frame,ready_usec,frames,ms")
	for key in hd_wanted_at.keys():
		var wanted: Array = hd_wanted_at[key]
		var ready: Array = hd_ready_at.get(key, [-1, -1])
		var kind := "page" if String(key).begins_with("page:") else "picture"
		keys.store_line("%s,%s,%d,%d,%d,%d,%d,%.1f" % [key, kind, wanted[0], wanted[1], ready[0], ready[1], ready[0] - wanted[0] if ready[0] >= 0 else -1,
			(ready[1] - wanted[1]) / 1000.0 if ready[0] >= 0 else -1.0])
	keys.close()
	hd_log = null


## Every worker's picture finished (before quitting: they call into the core).
func _finish_loading() -> void:
	_close_hd_log()
	for task in live_shot_tasks:
		WorkerThreadPool.wait_for_task_completion(task)
	live_shot_tasks.clear()
	for key in loading.keys():
		WorkerThreadPool.wait_for_task_completion(loading[key][1])
		core.take_built(loading[key][0])
	loading.clear()


func _refresh() -> void:
	var info := core.info()
	var place := "%d/%d/%d" % [info.get("program", -1), info.get("map", -1), info.get("screen", -1)]
	if place != last_place:
		# Where the game is (program, map, screen) whenever it changes, with the game frame and the live run's time.
		last_place = place
		print("xeno: now program %s at game frame %d, %.3f s" % [place, frames_run, (Time.get_ticks_usec() - live_started) / 1e6 if live_started > 0 else 0.0])
	_follow_pictures(info)
	var started := Time.get_ticks_usec()
	# A battle is drawn as the PS1 draws it: unlit, in its frame's drawing order (the bridge says so, info.unlit).
	var unlit: bool = info.get("unlit", false)
	sun.visible = lit and not unlit
	environment.ssao_enabled = lit and not unlit
	var surfaces := core.fill_world(world_mesh)
	_log_hd(0, 0, 0)
	if hd_sync:
		# The pack's own pictures this frame asked for, loaded now; the frame built again with them.
		var loaded_before := hd_sync_loaded
		var sync_started := Time.get_ticks_usec()
		if _load_pictures_now():
			surfaces = core.fill_world(world_mesh)
			_log_hd(1, hd_sync_loaded - loaded_before, Time.get_ticks_usec() - sync_started)
	info = core.info()
	if info.map_loads != page_loads:
		# A new scene: its pages are other textures under the same keys (the bridge forgot them as ready itself).
		page_loads = info.map_loads
		for key in textures.keys():
			if String(key).begins_with("page:"):
				textures.erase(key)
		for key in materials.keys():
			if String(key).contains("page:"):
				materials.erase(key)
	for surface in surfaces.size():
		# The game's own picture (the field's panorama) is drawn as the battle's scene is: unlit, in its order (behind all).
		var flat: bool = unlit or surfaces[surface][3]
		world_mesh.surface_set_material(surface, _material("battle" if flat else "world", surfaces[surface][0], surfaces[surface][1], 0, surfaces[surface][2]))
	_show_wave(core.screen_wave())
	var runs := core.fill_flat(flat_meshes)
	if hd_sync and _load_pictures_now():
		runs = core.fill_flat(flat_meshes)
	info = core.info()
	if info.screen_size != screen_size:
		screen_size = info.screen_size
		for key in materials.keys():
			if String(key).begins_with("flat|"):
				materials[key].set_shader_parameter("screen", Vector2(screen_size))
	_show_flat(runs)
	# Each VRAM the surfaces sample, sent again only when it has changed.
	for source in VRAM_SOURCES:
		var stamp: int = core.vram_stamp(source)
		if stamp != 0 and stamp != vram_stamps[source]:
			vram_stamps[source] = stamp
			vram_textures[source].update(Image.create_from_data(1024, core.vram_rows(), false, Image.FORMAT_RG8, core.vram_of(source)))
	var spent := Time.get_ticks_usec() - started
	if spent > 30000:
		print("xeno: frame %d built in %d ms" % [frames_run, spent / 1000])
	# The camera's height is the screen's lines the scene is projected for: the field's and the battle's 224, the world map's 216.
	camera.fov = rad_to_deg(2.0 * atan(float(info.get("scene_lines", 224)) * 0.5 / float(info.projection_distance)))
	environment.background_color = info.background if clear_override.r < 0.0 else clear_override
	if lit:
		var view := core.view_transform()
		var travels := (view.basis * SUN_TRAVELS).normalized()
		var up := (view.basis * Vector3(0, 0, 1)).normalized()
		# A frame without a view (a map change's, a movie's: its matrix is zero) leaves the sun where it was.
		if not travels.is_zero_approx() and not up.is_zero_approx() and not travels.cross(up).is_zero_approx():
			sun.basis = Basis.looking_at(travels, up)


## The field's screen wave as Weltall's renderer draws it (Rendering/FieldSceneRendering.cpp, the wave pass): the scene
## drawn so far drawn again through the wave's wide grid, each cell's corners where the wave puts them showing the screen
## where the cell lies unwaved. Toward the window's left and right edges the sway eases off over two cells, so the grid
## meets them (Weltall's Eased); the cells tile the window, so nothing is cleared first.
func _show_wave(cells: PackedFloat32Array) -> void:
	wave_mesh.clear_surfaces()
	wave_node.visible = not cells.is_empty()
	if cells.is_empty():
		return
	var vertices := PackedVector2Array()
	var shown := PackedVector2Array()
	for cell in cells.size() / 16:
		for corner in [0, 1, 2, 1, 3, 2]:
			var at: int = cell * 16 + corner * 4
			vertices.append(Vector2(cells[at], cells[at + 1]))
			shown.append(Vector2(cells[at + 2], cells[at + 3]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = shown
	wave_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, Mesh.ARRAY_FLAG_USE_2D_VERTICES)


func _wave_shader() -> Shader:
	var shader := Shader.new()
	shader.code = """shader_type canvas_item;
render_mode unshaded, blend_disabled;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
// The 320 x 224 screen the corners are in pixels of.
uniform vec2 screen = vec2(320.0, 224.0);
varying vec2 shown_uv;

void vertex() {
	// The window in canvas pixels, the screen scaled to its height and centred (as the 2D layer places it).
	vec2 size = 2.0 / abs(vec2(SCREEN_MATRIX[0][0], SCREEN_MATRIX[1][1]));
	float scale = size.y / screen.y;
	vec2 shown = UV;
	float half_visible = size.x / scale * 0.5;
	float eased = clamp(min(shown.x - (screen.x * 0.5 - half_visible), (screen.x * 0.5 + half_visible) - shown.x) / 32.0, 0.0, 1.0);
	vec2 at = shown + (VERTEX - shown) * eased;
	VERTEX = vec2(size.x * 0.5 + (at.x - screen.x * 0.5) * scale, at.y * scale);
	shown_uv = vec2(size.x * 0.5 + (shown.x - screen.x * 0.5) * scale, shown.y * scale) / size;
}

void fragment() {
	COLOR = vec4(texture(screen_tex, shown_uv).rgb, 1.0);
}
"""
	return shader


## The pictures the core's frame shows beside VRAM and the pack: the movie's picture on screen, and the field's picture
## of the screen, which is the frame the window showed last when the field took it (FieldView.cpp, TakePicture).
func _follow_pictures(info: Dictionary) -> void:
	var taken: int = info.get("cover_taken", 0)
	if taken != cover_taken:
		cover_taken = taken
		if taken > 0:
			var shown := get_viewport().get_texture().get_image()
			if shown != null:
				_set_texture("cover:", core.take_screen_picture(shown, taken))
	var picture: int = info.get("movie_picture", 0)
	if picture != movie_shown:
		movie_shown = picture
		var movie := core.movie_image()
		if movie != null:
			_set_texture("movie:", movie)
	_follow_movie(info)
	_follow_disc(info)


## The game asks for a disc the bridge has not found (the story's "INSERT DISC 2", a save of the other disc): a line over
## the game says which image to put where, until the bridge finds it there (it looks every second, the player need not
## confirm first); then a note that the game goes on once the player confirms.
func _follow_disc(info: Dictionary) -> void:
	var wanted: int = info.get("disc_wanted", 0)
	if wanted == disc_noted:
		return
	if wanted == 0:
		disc_note.visible = false
		# Found, or no longer asked for (another game loaded).
		if int(info.get("discs_held", 0)) & (1 << (disc_noted - 1)):
			print("xeno: disc %d found" % disc_noted)
			_show_note("Диск %d найден — нажмите «подтвердить» (X), и игра пойдёт дальше" % disc_noted)
	else:
		var release := "русского перевода" if info.get("disc_wanted_kind", "") == "rus" else "(USA)"
		var folder: String = String(info.get("disc_wanted_folder", "")).replace("/", "\\")
		disc_note.text = "Нужен диск %d %s: положите его образ (BIN+CUE или CHD, имя любое) в папку\n%s — игра найдёт его сама" % [wanted, release, folder]
		print("xeno: disc %d wanted in %s" % [wanted, folder])
		disc_note.visible = notes_shown
	disc_noted = wanted


## The movie showing replaced by its video when movies/<source>/<NN>.ogv is there (MOVIES says how it is named and timed):
## the video's frame follows the core's movie frame (info.movie_shown_frame), so the core keeps deciding when the movie
## starts, ends, pauses (the cheat panel, a stall) or is skipped, and its sound is the game's. The video plays on by
## itself between pictures; where it runs ahead of the movie by more than MOVIE_TOLERANCE it waits, where it falls behind
## by more it plays faster until it is back (_sync_movie).
func _follow_movie(info: Dictionary) -> void:
	var number: int = info.get("movie_number", -1)
	var source: String = info.get("movie_source", "")
	var key := "" if number < 0 or source.is_empty() else "%s/%02d" % [source, number]
	if key != movie_target:
		_stop_movie_video()
		movie_target = key
		if not key.is_empty():
			_start_movie_video(key)
	if not movie_replaced:
		return
	var frame: int = info.get("movie_shown_frame", 0)
	if frame != movie_frame_seen:
		movie_frame_seen = frame
		movie_frame_at = Time.get_ticks_usec()
	_sync_movie(false)


## The replacement video held to the movie frame last shown (_follow_movie), every rendered frame of live play; stopped
## outright while the game stands (the cheat panel).
func _sync_movie(standing: bool) -> void:
	if not movie_replaced or movie_video == null:
		return
	if standing:
		movie_video.paused = true
		return
	if movie_frame_seen <= 0:
		# No picture of the movie yet: the video waits at its start.
		movie_video.paused = true
		return
	var now := Time.get_ticks_usec()
	# The movie's time: its frame's, plus the time that frame has shown (at most its 1/15 s).
	var movie_time := (movie_frame_seen - 1) / 15.0 + minf((now - movie_frame_at) / 1e6, 1.0 / 15.0)
	var target := movie_offset + movie_rate * movie_time
	var drift := movie_video.stream_position - target
	movie_drift_worst = maxf(movie_drift_worst, absf(drift))
	movie_drift_sum += absf(drift)
	movie_drift_count += 1
	movie_video.speed_scale = 1.0
	if drift > MOVIE_TOLERANCE:
		# Ahead (the game stood, or the video jumped after a stall): it waits for the movie.
		movie_video.paused = true
	elif drift < -MOVIE_SEEK_BEHIND:
		# Far behind (a movie entered past its start): a seek, which Godot's Theora player does slowly (100-200 ms on
		# this movie) and from the nearest key frame on (the encoding puts one every second): it is the exception.
		movie_video.stream_position = target
		movie_video.paused = false
		movie_seeks += 1
		print("xeno: movie %s: video sought to %.3f s (it was %.3f s behind)" % [movie_key, target, -drift])
	elif drift < -MOVIE_TOLERANCE:
		# Behind: it catches up by playing faster (decoding every frame, so its picture stays whole), at most 4 times.
		movie_video.speed_scale = clampf(1.0 - drift * 4.0, 1.0, 4.0)
		movie_video.paused = false
		movie_catch_ups += 1
	else:
		movie_video.paused = false


func _start_movie_video(key: String) -> void:
	var path := movies_folder.path_join(key + ".ogv")
	movie_offset = 0.0
	movie_rate = 1.0
	# The sidecar <NN>.txt: the video's timing, and "video=<file>" (from the sidecar's folder) where this movie plays
	# another movie's video (a translation's disc showing the video made for the original's same movie).
	var sidecar := FileAccess.get_file_as_string(path.get_basename() + ".txt")
	for line in sidecar.split("\n", false):
		var pair := line.strip_edges().split("=", true, 1)
		if pair.size() == 2 and pair[0] == "offset":
			movie_offset = float(pair[1])
		elif pair.size() == 2 and pair[0] == "rate":
			movie_rate = float(pair[1])
		elif pair.size() == 2 and pair[0] == "video" and not FileAccess.file_exists(path):
			path = path.get_base_dir().path_join(pair[1].strip_edges()).simplify_path()
	if not FileAccess.file_exists(path):
		print("xeno: movie %s: no replacement (%s), the game's picture" % [key, path])
		return
	var stream := VideoStreamTheora.new()
	stream.file = path
	if movie_video == null:
		movie_video = VideoStreamPlayer.new()
		# Drawn by the 2D layer in the movie picture's place (_show_flat), not by itself: transparent, out of the way.
		movie_video.modulate = Color(1, 1, 1, 0)
		movie_video.size = Vector2(2, 2)
		movie_video.volume_db = -80.0
		add_child(movie_video)
	movie_video.stream = stream
	movie_video.play()
	movie_key = key
	movie_replaced = true
	movie_frame_seen = 0
	movie_drift_worst = 0.0
	movie_drift_sum = 0.0
	movie_drift_count = 0
	movie_seeks = 0
	movie_catch_ups = 0
	textures["movie_video:"] = movie_video.get_video_texture()
	for material_key in materials.keys():
		if String(material_key).contains("movie_video:"):
			materials.erase(material_key)
	print("xeno: movie %s: replaced by %s (offset %.4f s, rate %.6f)" % [key, path, movie_offset, movie_rate])


func _stop_movie_video() -> void:
	if movie_replaced and movie_video != null:
		print("xeno: movie %s: video stopped at %.3f s (movie frame %d); drift |video - movie| mean %.1f ms, worst %.1f ms over %d checks; catching up %d checks, seeks %d" % [movie_key,
			movie_video.stream_position, movie_frame_seen, 1000.0 * movie_drift_sum / maxi(movie_drift_count, 1), 1000.0 * movie_drift_worst, movie_drift_count, movie_catch_ups, movie_seeks])
		movie_video.stop()
	textures.erase("movie_video:")
	movie_key = ""
	movie_replaced = false


## A texture the display makes itself, updated in place while its size holds.
func _set_texture(key: String, image: Image) -> void:
	if image == null:
		return
	var texture: ImageTexture = textures.get(key)
	if texture != null and texture.get_size() == Vector2(image.get_size()) and texture.get_format() == image.get_format():
		texture.update(image)
		return
	textures[key] = ImageTexture.create_from_image(image)
	for material_key in materials.keys():
		if String(material_key).contains(key):
			materials.erase(material_key)


## F2 the light, F3 the texture pack, F11 full screen: the looks compared in play. F1 the cheat panel, F4 the battle won.
func _unhandled_key_input(event: InputEvent) -> void:
	if not event.is_pressed() or event.is_echo():
		return
	var key := (event as InputEventKey).physical_keycode
	if key == KEY_F1 or (cheat_open and key == KEY_ESCAPE):
		_toggle_cheat_panel()
		get_viewport().set_input_as_handled()
		return
	if cheat_open and key != KEY_F11:
		# While the panel is open the game stands: F4, F5, F9 wait for it to close.
		return
	match key:
		KEY_F4:
			var error := _cheat("win")
			_show_note("Бой выигран (F4)" if error.is_empty() else "Победа (F4) сейчас недоступна: " + _cheat_why(error))
		KEY_F2:
			lit = not lit
			_apply_options()
		KEY_F3:
			hd = not hd
			if hd and not pack_read:
				_read_pack()
			_apply_options()
		KEY_F5:
			_save_state()
		KEY_F6:
			_frame_report()
		KEY_F7:
			_next_dark()
		KEY_F8:
			_next_flash()
		KEY_F9:
			_load_latest_state()
		KEY_F11:
			var full := DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if full else DisplayServer.WINDOW_MODE_FULLSCREEN)


## F5: the game now as a save state in the states folder (only where the player has control, as the core allows).
func _save_state() -> void:
	DirAccess.make_dir_recursive_absolute(states_folder)
	# Named by the time, to the millisecond: the newest sorts last.
	var stamp := Time.get_datetime_string_from_system().replace(":", "-") + "-%03d" % (Time.get_ticks_msec() % 1000)
	var path := states_folder.path_join(stamp + ".state")
	var error := core.save_state(path)
	print("xeno: F5 ", path if error.is_empty() else error, " ", core.info())
	if error.is_empty():
		_show_note("Сохранено: " + path.get_file())
	elif error.begins_with("not now"):
		_show_note("Не сохранено: сейчас нельзя (только когда герой в вашей власти)")
	else:
		_show_note("Не сохранено: " + error)


## F9: the newest save state in the states folder loaded over the game running, at any moment. The bridge starts the
## sound and the console afresh and forgets what it worked out from the old game (FSession::LoadState); here the
## display forgets its own: the VRAM uploads, the movie's and the screen's pictures, the vertical blanks due, the sound
## already queued for the device. The pages of the new scene load as a map change loads them (map_loads changes).
func _load_latest_state() -> void:
	var newest := ""
	var newest_time := -1
	var dir := DirAccess.open(states_folder)
	if dir != null:
		for name in dir.get_files():
			if not name.ends_with(".state"):
				continue
			var path := states_folder.path_join(name)
			var time := FileAccess.get_modified_time(path)
			if time > newest_time or (time == newest_time and path > newest):
				newest_time = time
				newest = path
	if newest.is_empty():
		_show_note("Не загружено: в " + states_folder + " нет сохранений (F5)")
		return
	_load_state_file(newest)


## A save state file loaded over the game running, as F9 loads the newest (the script's @state=<file>, the story shots).
func _load_state_file(newest: String) -> void:
	var load_started := Time.get_ticks_usec()
	var error := core.load_state(newest)
	var load_usec := Time.get_ticks_usec() - load_started
	print("xeno: F9 ", newest, " '", error, "' in %.1f ms " % (load_usec / 1000.0), core.info())
	if error in ["not a state", "a state of another version", "a damaged state", "a state of another disc"]:
		# The file was refused before anything was replaced: the game runs on as it was.
		_show_note("Не загружено: " + newest.get_file() + ": " + error)
		return
	# Otherwise the console was powered on afresh: with the state, or (it could not be entered) from the start.
	_forget_game()
	if not is_processing():
		# The game had stopped on a core error: the one loaded (or the console powered on afresh) runs.
		set_process(true)
		if want_sound and sound_player != null and sound_playback == null:
			sound_player.play()
			sound_playback = sound_player.get_stream_playback()
			sound_room = sound_playback.get_frames_available()
	if error.is_empty():
		_show_note("Загружено: " + newest.get_file())
	else:
		_show_note("Не загружено: " + newest.get_file() + ": " + error)
	_refresh()


## What the display drew from the game before a state was loaded: forgotten, so nothing of it shows or sounds again.
func _forget_game() -> void:
	_stop_movie_video()
	movie_target = ""
	for source in VRAM_SOURCES:
		vram_stamps[source] = -1
	cover_taken = 0
	movie_shown = -1
	for key in ["movie:", "cover:"]:
		textures.erase(key)
		for material_key in materials.keys():
			if String(material_key).contains(key):
				materials.erase(material_key)
	vblanks_due = 0
	if sound_playback != null:
		# The old game's sound still queued for the device is dropped (a playing generator's ring cannot be cleared: the
		# playback starts anew, empty); the new game's fills the lead again.
		skips_before += sound_playback.get_skips()
		sound_player.stop()
		sound_player.play()
		sound_playback = sound_player.get_stream_playback()
		sound_room = sound_playback.get_frames_available()
		_feed_sound()


## A short note of the shell's (F5, F9) over the picture for a few seconds.
func _show_note(text: String) -> void:
	print("xeno: note ", text)
	if not notes_shown:
		return
	note.text = text
	note.visible = true
	note_until = Time.get_ticks_msec() + 3000


## F6: a report of the frame shown, for a defect seen anywhere (a cutscene without control too) to be looked into without
## playing there again. A folder <reports>/<date-time to the ms>/:
## - shot.png: the window as the player sees it now (the frame rendered last; pictures still loading are not waited for,
##   frame.txt says how many);
## - shot_plain.png: the same frame without the pack and the light (F3, F2), both then set back as they were;
## - frame.txt: the time, the build, the disc, the settings, core.info(), the open message windows, the party; then the
##   bridge's text of the frame (core.frame_report: what is drawn not from the pack, every primitive);
## - state.state: the game now where F5 could save it, else the newest state the bridge took (core.set_rolling_state);
## - inputs.txt: the script that plays the way from that state to this frame (script_file=<it>: @state=, then each frame's
##   buttons).
## The game takes no step meanwhile (as under the cheat panel: no frames, no time let through, the sound paused).
func _frame_report() -> void:
	if reporting or failed_to_start:
		return
	reporting = true
	var started := Time.get_ticks_usec()
	var sound_was_paused := sound_player == null or sound_player.stream_paused
	if not sound_was_paused:
		sound_player.stream_paused = true
	var before: Dictionary = core.info()
	var frames_before := frames_run
	var stamp := Time.get_datetime_string_from_system().replace(":", "-") + "-%03d" % (Time.get_ticks_msec() % 1000)
	var folder := reports_folder.path_join(stamp)
	DirAccess.make_dir_recursive_absolute(folder)
	# The shell's own lines (a note such as the last report's "Отчёт о кадре: ...", the disc's line) are not the game's:
	# hidden for both shots and drawn again without them (the game stands meanwhile: same frame), shown again after.
	var shell_shown := shell_layer.visible and (note.visible or disc_note.visible)
	if shell_shown:
		shell_layer.visible = false
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw
	# The window as shown: the frame rendered last, as it is (its pictures still loading too).
	var shot := get_viewport().get_texture().get_image()
	var still_loading := loading.size()
	var shot_usec := Time.get_ticks_usec() - started
	# The bridge builds the frame again (no step) into text; then the state to go back to.
	var text_started := Time.get_ticks_usec()
	var frame_text := core.frame_report()
	var text_usec := Time.get_ticks_usec() - text_started
	var state_started := Time.get_ticks_usec()
	var state_path := folder.path_join("state.state")
	var state: Dictionary = core.write_report_state(state_path)
	var state_usec := Time.get_ticks_usec() - state_started
	# The pictures are encoded on workers (a PNG of the window takes ~0.3 s), waited for before quitting.
	var shot_file := folder.path_join("shot.png")
	live_shot_tasks.append(WorkerThreadPool.add_task(func() -> void: shot.save_png(shot_file), false, "xeno report shot"))
	# The same frame without the pack and the light: switched off as F3 and F2 do, drawn, the window taken, set back.
	var plain_started := Time.get_ticks_usec()
	var hd_was := hd
	var lit_was := lit
	var dark_was := dark_level
	var plain := shot
	if hd or lit or dark_level > 0:
		# The game's own picture: F7's brightening off too.
		hd = false
		lit = false
		dark_level = 0
		_apply_dark()
		_apply_options()
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw
		plain = get_viewport().get_texture().get_image()
		hd = hd_was
		lit = lit_was
		dark_level = dark_was
		_apply_dark()
		_apply_options()
	var plain_file := folder.path_join("shot_plain.png")
	live_shot_tasks.append(WorkerThreadPool.add_task(func() -> void: plain.save_png(plain_file), false, "xeno report plain shot"))
	var plain_usec := Time.get_ticks_usec() - plain_started
	if shell_shown:
		shell_layer.visible = true
	var after: Dictionary = core.info()
	# The game must not have moved: the same frames run, tick, place and pictures of its frame.
	var unchanged := frames_run == frames_before
	for key in ["program", "map", "tick", "leader_position", "leader_frame", "battle_step", "hud_hash", "menu_number", "movie_frame", "story"]:
		unchanged = unchanged and str(before.get(key)) == str(after.get(key))
	var inputs: PackedInt32Array = state.get("inputs", PackedInt32Array())
	var runs := _script_of(inputs)
	var source: String = state.get("source", "")
	var replay := ""
	if not source.is_empty():
		replay = "@state=" + _under_root(state_path) + ("," + runs if not runs.is_empty() else "")
		var inputs_file := FileAccess.open(folder.path_join("inputs.txt"), FileAccess.WRITE)
		inputs_file.store_string(replay + "\n")
		inputs_file.close()
	var lines := PackedStringArray()
	lines.append("Xenogears frame report %s" % stamp)
	lines.append("time: %s (game frames run in this session %d, live seconds %.3f)" % [Time.get_datetime_string_from_system(), frames_run, (Time.get_ticks_usec() - live_started) / 1e6 if live_started > 0 else 0.0])
	lines.append("build: %s" % _build_commit())
	lines.append("text: %s, disc: %s" % [core.language(), disc_played])
	# The disc in the drive (the second once the story or a save of it took it) and one the game waits on, if any.
	lines.append("drive: disc %d (%s, %s)%s" % [int(before.get("drive_disc", 0)), before.get("drive_disc_id", ""), String(before.get("drive_disc_file", "")).replace("/", "\\"),
		"; waiting on disc %d, not found in %s" % [int(before.get("disc_wanted", 0)), before.get("disc_wanted_folder", "")] if int(before.get("disc_wanted", 0)) > 0 else ""])
	lines.append("settings: hd %s (pack %s, %d pictures, by content %s), light %s, dark places brightened %d (%s, F7), battle flashes %d (%s, F8), turbo %d (Tab adds x%d), hd_sync %s" % [hd, pack_path, core.pack_pictures(), alias_found if alias_on else "off", lit,
		dark_level, DARK_NAMES[dark_level], flash_level, FLASH_NAMES[flash_level], turbo_rate, TURBO_KEY_RATE, hd_sync])
	lines.append("shot.png: the window as shown, %d x %d; pictures still loading %d, primitives drawn from VRAM while their picture loads %d (info.waiting)" % [shot.get_width(), shot.get_height(), still_loading, int(before.get("waiting", 0))])
	lines.append("shot_plain.png: %s" % ("the same frame with the pack, the light and the brightening of dark places off (F3, F2, F7), set back after" if hd_was or lit_was or dark_was > 0 else "the pack and the light were off already: the same picture"))
	if source.is_empty():
		lines.append("state.state: none written: %s" % state.get("error", ""))
	elif source == "now":
		lines.append("state.state: the game at this frame (the player has control: as F5 saves it); inputs.txt: the state alone")
	else:
		lines.append("state.state: the newest state taken before this frame (%s; now: %s); since it %d game frames, %d vertical blanks (%.2f s of game time), %.2f s of real time; frames the turbo ran %d, cheats asked for %d" % [source, state.get("error", ""), inputs.size(), int(state.get("vblanks", 0)), int(state.get("vblanks", 0)) * core.vblank_seconds(), float(state.get("seconds", 0.0)), int(state.get("turbo_frames", 0)), int(state.get("cheats", 0))])
		lines.append("inputs.txt: the way from it, as script= reads it: Godot --path game -- lang=%s \"script_file=%s\" (add ,@report or a shot= to look at the end); a state loads as the field comes back from a battle (its map entered again), so the replay may not land on the same frame" % [core.language(), _under_root(folder.path_join("inputs.txt"))])
	lines.append("the game during the report: %s (frames run %d -> %d; tick %s -> %s)" % ["unchanged" if unchanged else "CHANGED", frames_before, frames_run, before.get("tick"), after.get("tick")])
	lines.append("report took: shot %.1f ms, text %.1f ms, state %.1f ms, plain shot %.1f ms (the PNGs encoded on workers after); all %.1f ms" % [shot_usec / 1000.0, text_usec / 1000.0, state_usec / 1000.0, plain_usec / 1000.0, (Time.get_ticks_usec() - started) / 1000.0])
	lines.append("rolling state: %s" % core.rolling_stats())
	lines.append("")
	lines.append("== core.info()")
	var keys := before.keys()
	keys.sort()
	for key in keys:
		lines.append("%s: %s" % [key, before[key]])
	lines.append("")
	lines.append("== Message windows open (frontmost first)")
	for message in core.open_messages():
		lines.append("map %d index %d lines %d portrait %s codes %s" % [message.map, message.index, message.lines, message.portrait, PackedByteArray(message.codes).hex_encode()])
	lines.append("")
	lines.append("== The party")
	var party: Dictionary = core.cheat_state()
	lines.append("program %s, gold %s, random battles off %s, can edit %s, in battle %s" % [party.get("program"), party.get("gold"), party.get("encounters_off"), party.get("can_edit"), party.get("in_battle")])
	for hero in party.get("party", []):
		lines.append("%s (character %s): level %s, HP %s/%s, EP %s/%s, gear %s HP %s/%s, deathblows %s/%s" % [hero.name, hero.id, hero.level, hero.hp, hero.max_hp, hero.ep, hero.max_ep, hero.gear_name, hero.gear_hp, hero.gear_max_hp, hero.deathblows_learned, hero.deathblows_total])
	lines.append("")
	var file := FileAccess.open(folder.path_join("frame.txt"), FileAccess.WRITE)
	file.store_string("\n".join(lines) + "\n" + frame_text)
	file.close()
	if not sound_was_paused and sound_player != null:
		sound_player.stream_paused = false
	last_process = Time.get_ticks_usec()
	reporting = false
	print("xeno: F6 %s in %.1f ms (shot %.1f, text %.1f, state %.1f, plain %.1f): state %s, %d frames since it, game %s, still loading %d; %s" % [folder, (Time.get_ticks_usec() - started) / 1000.0, shot_usec / 1000.0, text_usec / 1000.0, state_usec / 1000.0, plain_usec / 1000.0, source if not source.is_empty() else "none (" + String(state.get("error", "")) + ")", inputs.size(), "unchanged" if unchanged else "CHANGED", still_loading, core.info()])
	_show_note("Отчёт о кадре: " + folder)


## Each frame's buttons as script= reads them: runs of the same buttons, "<frames>:<button>+<button>" or "<frames>:none";
## buttons tapped every other frame (pressed, let go, ...) as "<frames>:<buttons>~", which presses them on the run's
## first frame and every other one after it (_play_script).
func _script_of(inputs: PackedInt32Array) -> String:
	var runs := PackedStringArray()
	var at := 0
	while at < inputs.size():
		var pressed := inputs[at]
		var taps := 0
		while pressed != 0 and at + 2 * taps + 1 < inputs.size() and inputs[at + 2 * taps] == pressed and inputs[at + 2 * taps + 1] == 0:
			taps += 1
		var count := 1
		if taps >= 2:
			count = 2 * taps
		else:
			while at + count < inputs.size() and inputs[at + count] == pressed:
				count += 1
		var names := PackedStringArray()
		for name in PAD:
			if pressed & (1 << PAD[name]):
				names.append(name)
		runs.append("%d:%s%s" % [count, "+".join(names) if not names.is_empty() else "none", "~" if taps >= 2 else ""])
		at += count
	return ",".join(runs)


## A path under the root as the command line gives it (relative), else as it is.
func _under_root(path: String) -> String:
	var base := (root_folder if not root_folder.is_empty() else ProjectSettings.globalize_path("res://").path_join("..")).simplify_path()
	path = path.simplify_path()
	if path.begins_with(base + "/"):
		return path.substr(base.length() + 1)
	return path


## The commit the development tree is at (its .git, read as it lies), or why not known (the mod folder has none).
func _build_commit() -> String:
	var git := _from_root(".git")
	var head := FileAccess.get_file_as_string(git.path_join("HEAD")).strip_edges()
	if head.is_empty():
		return "not known (no .git under the root)"
	if not head.begins_with("ref: "):
		return head
	var ref := head.substr(5)
	var commit := FileAccess.get_file_as_string(git.path_join(ref)).strip_edges()
	if commit.is_empty():
		# A packed ref: its line in packed-refs.
		for line in FileAccess.get_file_as_string(git.path_join("packed-refs")).split("\n"):
			if line.ends_with(" " + ref):
				commit = line.get_slice(" ", 0)
	return "%s %s (the development tree's commit)" % [ref.get_file(), commit if not commit.is_empty() else "?"]


## A path given on the command line: as it is when absolute, else under the root (root=, by default the xeno_port folder).
func _from_root(path: String) -> String:
	path = path.replace("\\", "/")
	if path.is_absolute_path():
		return path
	var base := root_folder if not root_folder.is_empty() else ProjectSettings.globalize_path("res://").path_join("..")
	return base.path_join(path).simplify_path()


## The game could not start (no disc, an image the core refuses): said in the window, in plain words, until the player
## closes it (the process then ends with code 2, which the mod's batch knows as "said already"). Unattended runs (a
## script, a shot, quit_after) end at once with code 1, as before.
func _fail_in_window(text: String) -> void:
	push_error("xeno: " + text)
	set_process(false)
	if unattended:
		get_tree().quit(1)
		return
	get_tree().auto_accept_quit = false
	var layer := CanvasLayer.new()
	layer.layer = 100
	add_child(layer)
	var back := ColorRect.new()
	back.color = Color(0.05, 0.05, 0.08)
	back.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(back)
	var label := Label.new()
	label.text = text + "\n\n(Закройте это окно.)"
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.set_anchors_preset(Control.PRESET_FULL_RECT)
	label.offset_left = 48
	label.offset_top = 48
	label.offset_right = -48
	label.offset_bottom = -48
	label.add_theme_font_size_override("font_size", 24)
	layer.add_child(label)
	DisplayServer.window_set_title("Xenogears (Godot): игра не запустилась")
	failed_to_start = true


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and failed_to_start:
		get_tree().quit(2)


func _read_pack() -> String:
	var started := Time.get_ticks_msec()
	if not DirAccess.dir_exists_absolute(pack_path):
		pack_read = false
		return "no pack folder at " + pack_path
	var error := core.set_pack(pack_path)
	pack_read = error.is_empty() and core.pack_pictures() > 0
	if error.is_empty() and not pack_read:
		error = "no pictures in the pack folder " + pack_path
	# The pictures the pack holds under other names, found by content: the table (alias_table=, by default
	# data/sprite_alias_table.csv; hashes only, tools/sprite_alias_table.py), then the index (alias_index=, by default
	# out/alias, tools/sprite_alias_index.py; not published: it holds the game's texels); alias=0: off.
	var by_content := []
	if pack_read and alias_on:
		if FileAccess.file_exists(alias_table):
			var table: String = core.set_alias_table(alias_table)
			if not table.is_empty():
				push_warning("xeno: " + table)
			by_content.append("table %d lines" % core.alias_table_rows())
		if FileAccess.file_exists(alias_index):
			var alias: String = core.set_alias_index(alias_index)
			if alias.is_empty():
				by_content.append("index")
			else:
				push_warning("xeno: " + alias)
		if not alias_record.is_empty():
			var record: String = core.set_alias_record(alias_record)
			if not record.is_empty():
				push_warning("xeno: " + record)
	alias_found = ", ".join(by_content) if not by_content.is_empty() else "none"
	print("xeno: pack %d pictures in %d ms, pictures by content: %s" % [core.pack_pictures(), Time.get_ticks_msec() - started, alias_found])
	return error


## Light and pack switched: the shaders are made anew (whether they take light is in their code), the frame drawn again.
func _apply_options() -> void:
	core.set_options(hd, blob or not lit, lit)
	shaders.clear()
	materials.clear()
	var unlit: bool = core.info().get("unlit", false)
	sun.visible = lit and not unlit
	environment.ssao_enabled = lit and not unlit
	_show_title()
	_refresh()


func _show_title() -> void:
	DisplayServer.window_set_title("Xenogears (Godot)   текст: %s   F2 свет: %s   F3 HD: %s   F7 тёмное: %s   F8 вспышки: %s   F11 экран" % [core.language().to_upper(),
		"вкл" if lit else "выкл", "вкл" if hd else "выкл", DARK_NAMES[dark_level], FLASH_NAMES[flash_level]])


## F7's level onto its layer (off: the layer hidden, no screen copy made).
func _apply_dark() -> void:
	if dark_layer == null:
		return
	var rect: ColorRect = dark_layer.get_child(0)
	rect.visible = dark_level > 0
	(rect.material as ShaderMaterial).set_shader_parameter("strength", DARK_STRENGTHS[dark_level])
	_show_title()


## F7: the next level, kept for the next start.
func _next_dark() -> void:
	dark_level = (dark_level + 1) % DARK_STRENGTHS.size()
	_apply_dark()
	var settings := ConfigFile.new()
	settings.load(SETTINGS_FILE)
	settings.set_value("display", "dark", dark_level)
	var error := settings.save(SETTINGS_FILE)
	_show_note("Тёмные места светлее (F7): " + DARK_NAMES[dark_level] + ("" if error == OK else " (не запомнено: ошибка %d)" % error))


## F8: the battle flashes' next level (as in the game -> weak -> off -> as in the game), kept for the next start.
func _next_flash() -> void:
	flash_level = (flash_level + FLASH_NAMES.size() - 1) % FLASH_NAMES.size()
	core.set_battle_flashes(flash_level)
	_show_title()
	var settings := ConfigFile.new()
	settings.load(SETTINGS_FILE)
	settings.set_value("display", "flash", flash_level)
	var error := settings.save(SETTINGS_FILE)
	_show_note("Вспышки в бою (F8): " + FLASH_NAMES[flash_level] + ("" if error == OK else " (не запомнено: ошибка %d)" % error))


## The brightening of dark places over what is drawn under it (the screen's copy): the brightest channel y lifted to
## y + s * y * (1 - y)^8 and the colour scaled with it (its hue kept). The curve rises from 0 and reaches 1 at 1 and never
## falls (s up to 3: its slope 1 + s (1 - y)^7 (1 - 9y) stays above 0.48), so no colour passes white and black stays black.
func _dark_shader() -> Shader:
	var shader := Shader.new()
	shader.code = """shader_type canvas_item;
render_mode blend_disabled;
uniform sampler2D screen : hint_screen_texture, filter_nearest;
uniform float strength = 0.0;
void fragment() {
	vec3 c = texture(screen, SCREEN_UV).rgb;
	float y = max(c.r, max(c.g, c.b));
	float lifted = y + strength * y * pow(1.0 - y, 8.0);
	COLOR = vec4(y > 0.0 ? c * (lifted / y) : c, 1.0);
}
"""
	return shader


func _input(event: InputEvent) -> void:
	# Gamepads in the log (%APPDATA%/Godot/app_userdata/Xeno Port/logs): what each button and stick reports, to map them.
	if event is InputEventJoypadButton and event.pressed:
		print("xeno: pad %d button %d" % [event.device, event.button_index])
	elif event is InputEventJoypadMotion and absf(event.axis_value) > 0.5:
		print("xeno: pad %d axis %d %.2f" % [event.device, event.axis, event.axis_value])


func _log_pads(_device := 0, _connected := true) -> void:
	for device in Input.get_connected_joypads():
		print("xeno: pad %d: %s (%s) mapped=%s" % [device, Input.get_joy_name(device), Input.get_joy_guid(device), Input.is_joy_known(device)])


## The buttons held: keyboard, every gamepad's buttons, their left sticks as the directions.
func _held() -> int:
	var held := live_hold
	for key in KEYS:
		if Input.is_physical_key_pressed(key):
			held |= 1 << PAD[KEYS[key]]
	for device in (Input.get_connected_joypads() if pads_read else []):
		var buttons: Dictionary = JOY if Input.is_joy_known(device) else RAW_PAD.merged(RAW_DIRECTIONS)
		for button in buttons:
			if Input.is_joy_button_pressed(device, button):
				held |= 1 << PAD[buttons[button]]
		var stick := Vector2(Input.get_joy_axis(device, JOY_AXIS_LEFT_X), Input.get_joy_axis(device, JOY_AXIS_LEFT_Y))
		if stick.x < -0.5: held |= 1 << PAD.left
		if stick.x > 0.5: held |= 1 << PAD.right
		if stick.y < -0.5: held |= 1 << PAD.up
		if stick.y > 0.5: held |= 1 << PAD.down
		if Input.is_joy_known(device) and Input.get_joy_axis(device, JOY_AXIS_TRIGGER_LEFT) > 0.5: held |= 1 << PAD.l2
		if Input.is_joy_known(device) and Input.get_joy_axis(device, JOY_AXIS_TRIGGER_RIGHT) > 0.5: held |= 1 << PAD.r2
	return held


func _buttons_of(names: String) -> int:
	var held := 0
	# A trailing "~" (in a script): the buttons pressed every other frame, as a player taps them (bit 16 marks it).
	if names.ends_with("~"):
		held |= 1 << 16
		names = names.trim_suffix("~")
	for name in names.split("+", false):
		if PAD.has(name):
			held |= 1 << PAD[name]
	return held


## The 2D layer's runs on their canvas nodes, in order: each run's mesh with its material (blend mode, picture, VRAM,
## drawing area). A subtracting piece whose texels may not all blend (the bridge cut it to one primitive) takes two
## nodes, as Weltall's renderer draws it: its plain texels, then its blending ones subtracted. Nodes past the runs hide.
func _show_flat(runs: Array) -> void:
	if blend_remap[0] >= 0:
		for entry in runs:
			if entry[0] == blend_remap[0]:
				entry[0] = blend_remap[1]
	last_runs = runs
	# A movie's replacement video, once it shows a picture, drawn in the movie picture's place (_follow_movie).
	if movie_replaced:
		var video: Texture2D = textures.get("movie_video:")
		if video != null and video.get_width() > 0 and movie_video.stream_position > 0.0:
			for entry in runs:
				if entry[1] == "movie:":
					entry[1] = "movie_video:"
	while flat_nodes.size() < runs.size():
		var pair := [MeshInstance2D.new(), MeshInstance2D.new()]
		for node in pair:
			flat_layer.add_child(node)
		flat_nodes.append(pair)
	for run in flat_nodes.size():
		var pair: Array = flat_nodes[run]
		if run >= runs.size() or (layer_runs >= 0 and run >= layer_runs) or (flat_f >= 0 and run != flat_f):
			pair[0].visible = false
			pair[1].visible = false
			continue
		var entry: Array = runs[run]
		var blend: int = entry[0]
		var two_passes: bool = blend == 3 and entry[5]
		for slot in 2:
			var node: MeshInstance2D = pair[slot]
			node.visible = slot == 0 or two_passes
			if not node.visible:
				continue
			node.mesh = flat_meshes[run]
			# Part 1 (the plain texels) goes first where there are two passes.
			var part := (1 - slot) if two_passes else 0
			if flat_f == run:
				# The check's F: the run's blending pixels, opaque, once.
				node.visible = slot == 0
				part = 9
			var material := _flat_material(blend, entry[1], run, entry[2], part)
			if material.get_meta("area", Vector4.ZERO) != entry[4]:
				material.set_meta("area", entry[4])
				material.set_shader_parameter("area", entry[4])
			node.material = material


## A run's material on the 2D layer: its blend mode, its texture (VRAM, a pack picture, the movie's or the screen's
## picture), which VRAM, the part of a subtracting piece (0 its blending texels, 1 the others). Each run its own (its
## drawing area is a uniform).
func _flat_material(blend: int, texture: String, run: int, vram_source: int, part: int) -> ShaderMaterial:
	var key := "flat|%d|%s|%d|%d|%d" % [blend, texture, run, vram_source, part]
	if materials.has(key):
		return materials[key]
	var source := "vram" if texture.is_empty() else "hd"
	var material := ShaderMaterial.new()
	material.shader = _flat_shader(source, blend, part)
	material.set_shader_parameter("vram", vram_textures[clampi(vram_source, 0, VRAM_SOURCES - 1)])
	material.set_shader_parameter("screen", Vector2(screen_size))
	if source == "hd":
		material.set_shader_parameter("hd", _texture(texture))
		material.set_shader_parameter("alpha_any", texture.ends_with(".bc7") or texture.ends_with(".png"))
		_set_kinds(material, blend, texture)
	materials[key] = material
	return material


## The 2D layer's shader: everything the game draws flat composed as the PS1's GPU composes it, in its own colour
## space. The canvas target holds the finished 3D picture as displayed (after the tone map, gamma-encoded, 8 bits a
## channel; use_hdr_2d off) and the runs blend into it there, so every blend is of the values as stored and its result
## clamps to 0..1, as the GPU's B/2+F/2, B+F, B-F, B+F/4 clamp to 0..31 (an add after a subtract starts from 0, never
## below). Weltall's own renderer composes the field alike (Rendering/FieldSceneRendering.cpp: an 8-bit B8G8R8A8 target,
## the same blend states). F is as its draw-list shader makes it (Shaders/Private/ScreenDrawList.usf): a texel times the
## colour / 128, clamped (a VRAM texel's 5 bits, a pack picture's 8); an untextured primitive its colour. (The GPU also
## truncates F to 5 bits, dithered where it dithers: under one step of 31.) A semi-transparent primitive's texels that
## do not blend (bit 15 clear) are opaque: average, add and add-a-quarter do both in one pass with premultiplied alpha
## (plain: F, 1; blending: F/2, 0.5 / F, 0 / F/4, 0); subtract cannot, so such a piece is drawn twice, its plain texels
## (part 1), then its blending ones subtracted (part 0).
func _flat_shader(source: String, blend: int, part: int) -> Shader:
	var key := "flat|%s|%d|%d" % [source, blend, part]
	if shaders.has(key):
		return shaders[key]
	var mode: String = ["blend_mix", "blend_premul_alpha", "blend_premul_alpha", "blend_sub" if part == 0 else "blend_mix", "blend_premul_alpha"][blend]
	var output: String = [
		"COLOR = vec4(rgb, 1.0);",
		"COLOR = semi ? vec4(rgb * 0.5, 0.5) : vec4(rgb, 1.0);",
		"COLOR = semi ? vec4(rgb, 0.0) : vec4(rgb, 1.0);",
		("if (!semi) {\n\t\tdiscard;\n\t}\n\tCOLOR = vec4(rgb, 1.0);" if part == 0 else "if (semi) {\n\t\tdiscard;\n\t}\n\tCOLOR = vec4(rgb, 1.0);"),
		"COLOR = semi ? vec4(rgb * 0.25, 0.0) : vec4(rgb, 1.0);",
	][blend]
	if part == 9:
		# The blend check's F (flat_f): the blending pixels as they are, opaque.
		mode = "blend_mix"
		output = "if (!semi) {\n\t\tdiscard;\n\t}\n\tCOLOR = vec4(rgb, 1.0);"
	var texel := ""
	if source == "vram":
		texel = """bool blends;
	// Untextured: the colour; textured: the texel (5 bits as stored) times the colour / 128, clamped.
	if (!psx_texel(UV, COLOR.rgb, rgb, blends)) {
		discard;
	}
	semi = blends && (flags & 2) != 0;"""
	else:
		texel = """vec2 at = UV;
	if (texels.z >= 0.0) {
		// Taps kept inside the piece's own texels: its picture holds its neighbours too.
		vec2 half_texel = 0.5 / vec2(textureSize(hd, 0));
		vec2 low = min(texels.xy, texels.zw) + half_texel;
		vec2 high = max(texels.xy, texels.zw) - half_texel;
		at = clamp(at, min(low, high), max(low, high));
	}
	if (alpha_any) {
		// A pack picture: only (0, 0, 0, 0) is transparent; the four texels mixed by hand, the transparent ones left
		// out, the pixel drawn where the visible ones weigh at least half (no dark fringe).
		vec2 size = vec2(textureSize(hd, 0));
		vec2 p = at * size - 0.5;
		ivec2 first = ivec2(floor(p));
		vec2 f = fract(p);
		ivec2 lowest = ivec2(0);
		ivec2 highest = ivec2(size) - 1;
		if (texels.z >= 0.0) {
			lowest = ivec2(floor(min(texels.xy, texels.zw) * size + 0.001));
			highest = max(lowest, ivec2(ceil(max(texels.xy, texels.zw) * size - 0.001)) - 1);
		}
		vec3 sum = vec3(0.0);
		float cover = 0.0;
		for (int tap = 0; tap < 4; tap++) {
			ivec2 offset = ivec2(tap & 1, tap >> 1);
			vec4 t = texelFetch(hd, clamp(first + offset, lowest, highest), 0);
			float weight = (offset.x == 1 ? f.x : 1.0 - f.x) * (offset.y == 1 ? f.y : 1.0 - f.y);
			if (t.r + t.g + t.b + t.a > 0.002) {
				sum += t.rgb * weight;
				cover += weight;
			}
		}
		if (cover < 0.5) {
			discard;
		}
		rgb = sum / cover;
	} else {
		vec4 c = texture(hd, at);
		if (c.a <= 0.5) {
			discard;
		}
		rgb = c.rgb / max(c.a, 0.001);
	}
	if ((flags & 1) == 0) {
		// Modulated as the GPU modulates, by the colour / 128, clamped; the picture's 8 bits kept.
		rgb = min(rgb * c8 / 128.0, vec3(1.0));
	}
	// Which texels blend is the original texel's kind under the picture's (its colour's bit 15; kinds, from the bridge).
	semi = false;
	if ((flags & 2) != 0) {
		float kind = picture_kind(at, texels);
		if (kind < 0.25) {
			discard;
		}
		semi = kind > 0.75;
	}"""
	var code := """shader_type canvas_item;
render_mode unshaded, %s;
#include "res://shaders/vram.gdshaderinc"
// The pack's pictures as stored (no colour hint: the 2D target keeps values as displayed).
uniform sampler2D hd : filter_linear_mipmap, repeat_disable;
uniform bool alpha_any = false;
// Over the picture, the original texels' kinds where the primitive is semi-transparent; white: all of them blend.
uniform sampler2D kinds : hint_default_white, filter_nearest, repeat_disable;
%s
// The screen the layer is laid on (320 x 224, or 320 x 240), and the run's drawing area in its pixels (left, top,
// right, bottom; none where right <= left).
uniform vec2 screen = vec2(320.0, 224.0);
uniform vec4 area = vec4(-1.0);
varying flat vec4 area_px;

void vertex() {
	// CUSTOM0 packs C0 and C1 (xeno_core.cpp, AddFlatSurface): page x + 1024 page y, clut x + 1024 clut y,
	// depth + 8 flags, spans the display; CUSTOM1 is C2.
	float page_y = floor(CUSTOM0.x / 1024.0);
	float clut_y = floor(CUSTOM0.y / 1024.0);
	float flag_bits = floor(CUSTOM0.z / 8.0);
	look = vec4(CUSTOM0.x - page_y * 1024.0, page_y, CUSTOM0.z - flag_bits * 8.0, flag_bits);
	clut = vec4(CUSTOM0.y - clut_y * 1024.0, clut_y, CUSTOM0.w, 0.0);
	texels = CUSTOM1;
	// The window in canvas pixels (the canvas maps them to clip space by SCREEN_MATRIX): the screen scaled to its
	// height and centred, or spread across its whole width for what spans the display.
	vec2 size = 2.0 / abs(vec2(SCREEN_MATRIX[0][0], SCREEN_MATRIX[1][1]));
	float scale = size.y / screen.y;
	vec2 at = clut.z > 0.5 ? vec2(VERTEX.x / screen.x * size.x, VERTEX.y * scale) : vec2(size.x * 0.5 + (VERTEX.x - screen.x * 0.5) * scale, VERTEX.y * scale);
	area_px = (area.z > area.x && clut.z < 0.5)
		? vec4(size.x * 0.5 + (area.x - screen.x * 0.5) * scale, area.y * scale, size.x * 0.5 + (area.z - screen.x * 0.5) * scale, area.w * scale)
		: vec4(-1e9, -1e9, 1e9, 1e9);
	VERTEX = at;
}

void fragment() {
	if (FRAGCOORD.x < area_px.x || FRAGCOORD.y < area_px.y || FRAGCOORD.x >= area_px.z || FRAGCOORD.y >= area_px.w) {
		discard;
	}
	int depth = int(look.z + 0.5);
	int flags = int(look.w + 0.5);
	vec3 c8 = floor(COLOR.rgb * 255.0 + 0.5);
	vec3 rgb;
	bool semi;
	%s
	%s
}
""" % [mode, PICTURE_KINDS, texel, output]
	var shader := Shader.new()
	shader.code = code
	shaders[key] = shader
	return shader


## A surface's material: where it is drawn, its blend mode, its texture (VRAM, a pack picture, a page with them laid in).
func _material(layer: String, blend: int, texture: String, _run: int, vram_source: int = 0) -> ShaderMaterial:
	var key := "%s|%d|%s|%d|%d" % [layer, blend, texture, 0, vram_source]
	if materials.has(key):
		return materials[key]
	var source := "vram" if texture.is_empty() else "hd"
	var material := ShaderMaterial.new()
	material.shader = _shader(layer, source, blend)
	material.set_shader_parameter("vram", vram_textures[clampi(vram_source, 0, VRAM_SOURCES - 1)])
	if source == "hd":
		material.set_shader_parameter("hd", _texture(texture))
		# A pack picture: only (0, 0, 0, 0) is transparent; the pages, the movie and the screen's picture carry alpha.
		material.set_shader_parameter("alpha_any", texture.ends_with(".bc7") or texture.ends_with(".png"))
		_set_kinds(material, blend, texture)
	if blend != 0:
		# The scene's blending surfaces after its opaque ones, sorted among themselves (the 2D layer is the canvas's, after them all).
		material.render_priority = -128
	materials[key] = material
	return material


## A semi-transparent surface's picture: which of its texels blend, the original texels' kinds under it (the bridge
## works them out from VRAM, XenoCore.texel_kinds); without them every texel blends (the movie's, the screen's picture).
func _set_kinds(material: ShaderMaterial, blend: int, texture: String) -> void:
	if blend == 0:
		return
	var kinds: Image = core.texel_kinds(texture)
	if kinds != null:
		material.set_shader_parameter("kinds", ImageTexture.create_from_image(kinds))


## A picture the bridge draws a surface from: it only does so once the picture has loaded (_pump_textures) or the display
## made it (the movie's, the screen's picture), so it is always here.
func _texture(key: String) -> Texture2D:
	return textures.get(key)


func _shader(layer: String, source: String, blend: int) -> Shader:
	var key := "%s|%s|%d" % [layer, source, blend]
	if shaders.has(key):
		return shaders[key]
	var mode: String = BLENDS[blend][0]
	var alpha: String = BLENDS[blend][1]
	var modes := "cull_disabled"
	var vertex := "look = CUSTOM0;\n\tclut = CUSTOM1;\n\ttexels = CUSTOM2;"
	if layer == "battle":
		# A battle's scene, unlit, in its frame's drawing order: each primitive's place in the order (CUSTOM1.w, later
		# more) is its depth, so the later covers the earlier as on the PS1 (Godot's depth runs from 1 near to 0 far).
		modes += ", unshaded"
		modes += (", " + mode) if mode != "" else ""
		vertex += """
	POSITION = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0));
	POSITION.z = clut.w * POSITION.w;"""
	else:
		# Light on what is opaque; what blends (windows, the compass, effects) stays as the game draws it.
		modes += ", diffuse_lambert, specular_disabled" if lit and blend == 0 else ", unshaded"
		modes += (", " + mode) if mode != "" else ""
	var fragment := ""
	if source == "vram":
		fragment = """vec3 rgb;
	bool blends;
	if (!psx_texel(UV, COLOR.rgb, rgb, blends)) {
		discard;
	}
	bool semi = blends && (int(look.w + 0.5) & 2) != 0;
	ALBEDO = srgb_to_linear(rgb);"""
	else:
		fragment = """vec2 at = UV;
	if (texels.z >= 0.0) {
		// Taps kept inside the piece's (or polygon's) own texels: its picture holds its neighbours too.
		vec2 half_texel = 0.5 / vec2(textureSize(hd, 0));
		vec2 low = min(texels.xy, texels.zw) + half_texel;
		vec2 high = max(texels.xy, texels.zw) - half_texel;
		at = clamp(at, min(low, high), max(low, high));
	}
	vec3 rgb;
	if (alpha_any) {
		// A pack picture: only (0, 0, 0, 0) is transparent, and a plain linear tap would mix that black into the piece's
		// edge (a dark fringe; in a small window a whole row of the screen can land on it). So the four texels are mixed
		// by hand, the transparent ones left out, and the pixel drawn where the visible ones weigh at least half.
		vec2 size = vec2(textureSize(hd, 0));
		vec2 p = at * size - 0.5;
		ivec2 first = ivec2(floor(p));
		vec2 f = fract(p);
		ivec2 lowest = ivec2(0);
		ivec2 highest = ivec2(size) - 1;
		if (texels.z >= 0.0) {
			lowest = ivec2(floor(min(texels.xy, texels.zw) * size + 0.001));
			highest = max(lowest, ivec2(ceil(max(texels.xy, texels.zw) * size - 0.001)) - 1);
		}
		vec3 sum = vec3(0.0);
		float cover = 0.0;
		for (int tap = 0; tap < 4; tap++) {
			ivec2 offset = ivec2(tap & 1, tap >> 1);
			vec4 t = texelFetch(hd, clamp(first + offset, lowest, highest), 0);
			float weight = (offset.x == 1 ? f.x : 1.0 - f.x) * (offset.y == 1 ? f.y : 1.0 - f.y);
			if (t.r + t.g + t.b + t.a > 0.002) {
				sum += t.rgb * weight;
				cover += weight;
			}
		}
		if (cover < 0.5) {
			discard;
		}
		rgb = sum / cover;
	} else {
		vec4 c = texture(hd, at);
		if (c.a <= 0.5) {
			discard;
		}
		rgb = c.rgb / max(c.a, 0.001);
	}
	int flags = int(look.w + 0.5);
	if ((flags & 1) == 0) {
		// The PS1 modulates in its own (gamma) space: the factor's power carries it into linear light.
		rgb = min(rgb * pow(COLOR.rgb * (255.0 / 128.0), vec3(2.2)), vec3(1.0));
	}
	// Which texels blend is the original texel's kind under the picture's (its colour's bit 15; kinds, from the bridge).
	bool semi = false;
	if ((flags & 2) != 0) {
		float kind = picture_kind(at, texels);
		if (kind < 0.25) {
			discard;
		}
		semi = kind > 0.75;
	}
	ALBEDO = rgb;"""
	var body := """%s
	// Both sides of the PS1's polygons are drawn: light the side the camera sees (VERTEX is in view space).
	if (dot(NORMAL, -VERTEX) < 0.0) {
		NORMAL = -NORMAL;
	}
	%s""" % [fragment, alpha]
	if source == "vram" and layer == "world" and blend == 1:
		# The characters' shadows drawn soft (depth 5): dark, fading out to the quad's ellipse.
		body = """if (int(look.z + 0.5) == 5) {
		float d = length(UV * 2.0 - 1.0);
		if (d > 1.0) {
			discard;
		}
		ALBEDO = vec3(0.0);
		// Blending is in linear light: 0.8 here darkens the floor on screen by about half.
		// As strong as the game's own: it takes its colour away from the floor (128 = all of it), none for a hidden actor's.
		float strength = clamp(max(COLOR.r, max(COLOR.g, COLOR.b)) * (255.0 / 128.0), 0.0, 1.0);
		ALPHA = 0.8 * strength * pow(1.0 - d * d, 0.6);
	} else {
		%s
	}""" % body
	var code := """shader_type spatial;
render_mode %s;
#include "res://shaders/vram.gdshaderinc"
uniform sampler2D hd : source_color, filter_linear_mipmap, repeat_disable;
uniform bool alpha_any = false;
// Over the picture, the original texels' kinds where the primitive is semi-transparent; white: all of them blend.
uniform sampler2D kinds : hint_default_white, filter_nearest, repeat_disable;
%s
void vertex() {
	%s
}
void fragment() {
	%s
}
""" % [modes, PICTURE_KINDS, vertex, body]
	var shader := Shader.new()
	shader.code = code
	shaders[key] = shader
	return shader


## A cheat (core.cheat: FSession::Cheat says how each acts on the game); the panel's state printed after it, the panel
## filled again. Returns the bridge's answer: empty, or why it was not done.
func _cheat(command: String) -> String:
	var error := core.cheat(command)
	print("xeno: cheat %s '%s' %s" % [command, error, core.cheat_state()])
	if cheat_open:
		_fill_cheat_panel()
	return error


## The bridge's reasons in Russian for the panel and the notes.
func _cheat_why(error: String) -> String:
	match error:
		"not in a battle":
			return "сейчас не бой"
		"the battle's end is already decided":
			return "исход боя уже решён (сюжетный бой ведёт сценарий)"
		"only on the field or the world map":
			return "только на поле и на карте мира"
		"already at the last level":
			return "уже последний уровень"
		"the list is full":
			return "список полон"
		"nothing more to learn now":
			return "сейчас учить больше нечего: следующий приём требует уровня или открывается сюжетом"
	return error


## F1: the panel opened (the game stands: no frames, its sound paused where it is) or closed (the game and its sound go
## on from where they stood: nothing queued while it was open, so nothing stale plays). Tab: 0 party, 1 fast run, 2 items.
func _toggle_cheat_panel(tab := -1) -> void:
	cheat_open = not cheat_open if tab < 0 else true
	cheat_layer.visible = cheat_open
	if sound_player != null:
		sound_player.stream_paused = cheat_open
	if cheat_open:
		if tab >= 0:
			cheat_ui.tabs.current_tab = tab
		_fill_cheat_panel()
		var first: Control = cheat_ui.tabs.get_tab_bar()
		first.grab_focus()
	else:
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null:
			focused.release_focus()
		if turbo_rate != 1 and turbo_always == 1:
			turbo_rate = 1
			core.cheat("turbo:1")
	print("xeno: cheat panel %s, game frames %d, underruns %d" % ["open" if cheat_open else "closed", live_frames, _skips()])


## The panel's controls: plain Godot controls on a layer over the game, readable at 1280 x 720 and full screen (fixed
## sizes, centred), each usable with the mouse and with the keyboard (Tab / arrows to move, Enter or Space to press).
func _build_cheat_panel() -> void:
	cheat_layer = CanvasLayer.new()
	cheat_layer.layer = 90
	cheat_layer.visible = false
	add_child(cheat_layer)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	cheat_layer.add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	cheat_layer.add_child(center)
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(1180, 640)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.07, 0.08, 0.11, 0.97)
	style.set_corner_radius_all(8)
	style.set_content_margin_all(16)
	panel.add_theme_stylebox_override("panel", style)
	var look := Theme.new()
	look.default_font_size = 18
	# Buttons that read as buttons on the dark panel, the keyboard's focus outlined in yellow.
	for kind in ["Button", "OptionButton"]:
		for state in ["normal", "hover", "pressed", "disabled", "focus"]:
			var face := StyleBoxFlat.new()
			face.set_corner_radius_all(4)
			face.content_margin_left = 10
			face.content_margin_right = 10
			face.content_margin_top = 4
			face.content_margin_bottom = 4
			face.bg_color = {"normal": Color(0.2, 0.23, 0.33), "hover": Color(0.28, 0.32, 0.46), "pressed": Color(0.14, 0.16, 0.24),
				"disabled": Color(0.12, 0.13, 0.17), "focus": Color(0, 0, 0, 0)}[state]
			face.draw_center = state != "focus"
			face.set_border_width_all(2 if state == "focus" else 1)
			face.border_color = Color(1.0, 0.85, 0.35) if state == "focus" else Color(0.38, 0.43, 0.58)
			look.set_stylebox(state, kind, face)
		look.set_color("font_disabled_color", kind, Color(0.45, 0.47, 0.52))
	panel.theme = look
	center.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	panel.add_child(box)
	var title := Label.new()
	title.text = "Читы — F1 или Esc: закрыть. Пока панель открыта, игра на паузе."
	title.add_theme_font_size_override("font_size", 22)
	box.add_child(title)
	box.add_child(_cheat_label("Всё, что изменено здесь, попадает в сохранения, сделанные после (File в меню игры, F5).", Color(0.75, 0.85, 1.0), 1140))
	var tabs := TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(tabs)
	cheat_ui.tabs = tabs

	# The party: each member's level, EXP, HP/EP; the money; the gears.
	var party := VBoxContainer.new()
	party.add_theme_constant_override("separation", 8)
	tabs.add_child(party)
	tabs.set_tab_title(0, "Партия и деньги")
	cheat_ui.party_note = _cheat_label("", Color(1.0, 0.8, 0.5), 1140)
	party.add_child(cheat_ui.party_note)
	# Up to three heroes of five lines each: they scroll where the panel is too short for them.
	var heroes_scroll := ScrollContainer.new()
	heroes_scroll.custom_minimum_size.y = 300
	heroes_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	heroes_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	heroes_scroll.follow_focus = true
	party.add_child(heroes_scroll)
	cheat_ui.heroes = VBoxContainer.new()
	cheat_ui.heroes.add_theme_constant_override("separation", 6)
	heroes_scroll.add_child(cheat_ui.heroes)
	var party_wide := HBoxContainer.new()
	party_wide.add_theme_constant_override("separation", 10)
	party.add_child(party_wide)
	cheat_ui.deathblows_party = _cheat_button(party_wide, "Все приёмы всей партии", func():
		var error := _cheat("deathblows:party")
		if not error.is_empty():
			_show_note("Не сделано: " + _cheat_why(error)))
	cheat_ui.deathblows_party.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	party_wide.add_child(_cheat_label("Уровень, опыт и приёмы (deathblows) даёт правило самой игры, как за выигранный бой: статы растут по таблицам диска; приём учится, только если уровень героя не ниже нужного, 7-AP приёмы — когда их откроет сюжет; за опыт остальные персонажи получают четверть, как запасные.", Color(0.7, 0.7, 0.75), 900))
	var money := HBoxContainer.new()
	money.add_theme_constant_override("separation", 10)
	party.add_child(money)
	cheat_ui.money_label = _cheat_label("", Color(1, 1, 1))
	cheat_ui.money_label.custom_minimum_size.x = 260
	money.add_child(cheat_ui.money_label)
	var money_spin := SpinBox.new()
	money_spin.max_value = 9999999
	money_spin.custom_minimum_size.x = 180
	money.add_child(money_spin)
	cheat_ui.money_spin = money_spin
	cheat_ui.money_set = _cheat_button(money, "Установить", func(): _cheat("money:%d" % int(money_spin.value)))
	cheat_ui.money_add = _cheat_button(money, "+10 000", func(): _cheat("money+:10000"))
	var gears := HBoxContainer.new()
	gears.add_theme_constant_override("separation", 10)
	party.add_child(gears)
	cheat_ui.gears_label = _cheat_label("", Color(1, 1, 1), 760)
	gears.add_child(cheat_ui.gears_label)
	cheat_ui.gears = _cheat_button(gears, "Гиры: HP и топливо полностью", func(): _cheat("gears"))

	# The fast run: random battles, turbo, the battle won.
	var fast := VBoxContainer.new()
	fast.add_theme_constant_override("separation", 10)
	tabs.add_child(fast)
	tabs.set_tab_title(1, "Быстрая игра")
	var encounters := CheckButton.new()
	encounters.text = "Случайные бои выключены (настройка самого Weltall «Encounters: None»)"
	encounters.toggled.connect(func(on: bool): _cheat("encounters:%d" % (0 if on else 1)))
	fast.add_child(encounters)
	cheat_ui.encounters = encounters
	var speed := HBoxContainer.new()
	speed.add_theme_constant_override("separation", 10)
	fast.add_child(speed)
	speed.add_child(_cheat_label("Скорость игры:", Color(1, 1, 1)))
	var turbo := OptionButton.new()
	for text in ["обычная (Tab — ×4, пока держишь)", "всегда ×2", "всегда ×4"]:
		turbo.add_item(text)
	turbo.item_selected.connect(func(index: int): turbo_always = [1, 2, 4][index])
	speed.add_child(turbo)
	cheat_ui.turbo = turbo
	fast.add_child(_cheat_label("Ускоряется там же, где ускоряет сам Weltall: бой, поле (и сценки на нём), карта мира; ролики, меню и экран итогов боя идут как есть. Звук идёт в своём темпе: музыка не ускоряется, звуки игры звучат чаще.", Color(0.7, 0.7, 0.75), 1140))
	var win := HBoxContainer.new()
	win.add_theme_constant_override("separation", 10)
	fast.add_child(win)
	cheat_ui.win = _cheat_button(win, "Победить в бою (F4)", func(): _cheat("win"))
	cheat_ui.win_label = _cheat_label("", Color(1.0, 0.8, 0.5))
	win.add_child(cheat_ui.win_label)
	fast.add_child(_cheat_label("Победа — по правилам самой игры: враги падают, игра сама даёт опыт, деньги и находки и показывает итоги. В сюжетном бою исход ведёт сценарий.", Color(0.7, 0.7, 0.75), 1140))

	# The items: any entry of the disc's lists, its count set.
	var items := VBoxContainer.new()
	items.add_theme_constant_override("separation", 10)
	tabs.add_child(items)
	tabs.set_tab_title(2, "Предметы")
	cheat_ui.items_note = _cheat_label("", Color(1.0, 0.8, 0.5), 1140)
	items.add_child(cheat_ui.items_note)
	var pick := HBoxContainer.new()
	pick.add_theme_constant_override("separation", 10)
	items.add_child(pick)
	var kind := OptionButton.new()
	for text in ITEM_LISTS:
		kind.add_item(text)
	pick.add_child(kind)
	cheat_ui.item_kind = kind
	var item := OptionButton.new()
	item.custom_minimum_size.x = 420
	item.fit_to_longest_item = false
	pick.add_child(item)
	cheat_ui.item = item
	pick.add_child(_cheat_label("Сколько:", Color(1, 1, 1)))
	var count := SpinBox.new()
	count.max_value = 99
	pick.add_child(count)
	cheat_ui.item_count = count
	cheat_ui.item_set = _cheat_button(pick, "Установить", func():
		if item.selected >= 0:
			_cheat("item:%d:%d:%d" % [kind.selected, item.get_item_id(item.selected), int(count.value)]))
	kind.item_selected.connect(func(_index: int): _fill_cheat_items())
	item.item_selected.connect(func(index: int): count.value = item.get_item_metadata(index))
	items.add_child(_cheat_label("Названия — из таблиц диска (на обоих дисках английские). Предмет кладётся, как его кладёт сама игра: в ячейку с ним или в первую свободную, не больше 99.", Color(0.7, 0.7, 0.75), 1140))
	cheat_ui.items_held = _cheat_label("", Color(0.85, 0.85, 0.9), 1140)
	items.add_child(cheat_ui.items_held)


## A label of the panel; with a width, wrapped within it.
func _cheat_label(text: String, color: Color, width := 0) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", color)
	if width > 0:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.custom_minimum_size.x = width
	return label


func _cheat_button(parent: Control, text: String, pressed: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(pressed)
	parent.add_child(button)
	return button


## The panel filled from the game as it is now (core.cheat_state): what cannot be done here and now is greyed out.
func _fill_cheat_panel() -> void:
	var state := core.cheat_state()
	var edit: bool = state.can_edit
	cheat_ui.party_note.text = "" if edit else "Сейчас менять нельзя: уровни, приёмы, HP/EP, деньги, предметы и гиры меняются только на поле и на карте мира (в бою у партии свои копии, итоги боя перепишут их)."
	cheat_ui.party_note.visible = not edit
	# A hero's button with the keyboard's focus keeps it over the rows built anew (by its place among them).
	var focused := get_viewport().gui_get_focus_owner()
	var focus_at := -1
	var old_buttons: Array = cheat_ui.get("hero_buttons", [])
	if focused != null:
		focus_at = old_buttons.find(focused)
	cheat_ui.hero_buttons = []
	for child in cheat_ui.heroes.get_children():
		cheat_ui.heroes.remove_child(child)
		child.queue_free()
	var gears := PackedStringArray()
	for hero in state.party:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		cheat_ui.heroes.add_child(row)
		var info := _cheat_label("%s — уровень %d (эфирный %d)\nопыт %d, до следующего %d · эфирный опыт %d, до следующего %d\nHP %d/%d   EP %d/%d   атака %d, защита %d, ловкость %d, эфир %d, эф. защита %d, точность %d, уклонение %d" % [
			hero.name, hero.level, hero.ether_level, hero.exp, hero.exp_next, hero.ether_exp, hero.ether_next, hero.hp, hero.max_hp, hero.ep, hero.max_ep,
			hero.attack, hero.defense, hero.agility, hero.ether, hero.ether_defense, hero.hit, hero.evade] + "\n" + _deathblows_line(hero), Color(1, 1, 1), 660)
		row.add_child(info)
		var buttons := GridContainer.new()
		buttons.columns = 2
		row.add_child(buttons)
		var id: int = hero.id
		for entry in [["+1 уровень", "level:%d:1" % id], ["+10 уровней", "level:%d:10" % id], ["+10 000 опыта", "exp:%d:10000" % id], ["HP и EP полностью", "fill:%d" % id], ["Выучить все приёмы", "deathblows:%d" % id]]:
			var command: String = entry[1]
			var button := _cheat_button(buttons, entry[0], func():
				var error := _cheat(command)
				if not error.is_empty():
					_show_note("Не сделано: " + _cheat_why(error)))
			button.disabled = not edit
			cheat_ui.hero_buttons.append(button)
		if hero.gear >= 0:
			gears.append("%s: HP %d/%d, топливо %d/%d" % [hero.gear_name, hero.gear_hp, hero.gear_max_hp, hero.fuel, hero.max_fuel])
	if focus_at >= 0 and focus_at < cheat_ui.hero_buttons.size():
		cheat_ui.hero_buttons[focus_at].grab_focus.call_deferred()
	if state.party.is_empty():
		cheat_ui.heroes.add_child(_cheat_label("Партии нет (игра ещё не началась).", Color(0.8, 0.8, 0.8)))
	cheat_ui.deathblows_party.disabled = not edit or state.party.is_empty()
	cheat_ui.money_label.text = "Деньги: %d G" % state.gold
	cheat_ui.money_spin.value = state.gold
	for control in [cheat_ui.money_spin, cheat_ui.money_set, cheat_ui.money_add, cheat_ui.gears, cheat_ui.item_kind, cheat_ui.item, cheat_ui.item_count, cheat_ui.item_set]:
		if control is SpinBox:
			control.editable = edit
		else:
			control.disabled = not edit
	cheat_ui.gears_label.text = "Гиры партии: " + (", ".join(gears) if not gears.is_empty() else "у партии сейчас нет гиров") + "."
	cheat_ui.encounters.set_pressed_no_signal(state.encounters_off)
	cheat_ui.turbo.selected = {1: 0, 2: 1, 4: 2}.get(turbo_always, 0)
	cheat_ui.win.disabled = not state.can_win
	cheat_ui.win_label.text = ("Бой: врагов на ногах %d" % state.enemies_left) if state.can_win else ("Исход боя уже решён" if state.in_battle else "Сейчас не бой")
	cheat_ui.items_note.text = "" if edit else "Сейчас менять нельзя: только на поле и на карте мира."
	cheat_ui.items_note.visible = not edit
	_fill_cheat_items()
	var held := PackedStringArray()
	for entry in state.items:
		held.append("%s ×%d" % [entry[1], entry[2]])
	cheat_ui.items_held.text = "В сумке (предметы): " + (", ".join(held) if not held.is_empty() else "пусто")


## A hero's Deathblows in a line: how many of its list are learned, the next the game's routine would teach and the level it
## asks, how many the story has yet to open (the 7-AP tier).
func _deathblows_line(hero: Dictionary) -> String:
	var line := "приёмы: %d из %d" % [hero.deathblows_learned, hero.deathblows_total]
	if hero.deathblows_total == 0:
		return "приёмов у героя нет (бой их не учит)"
	var next := ""
	var closed := 0
	for entry in hero.deathblows:
		if entry[2]:
			continue
		if not entry[5]:
			closed += 1
		elif next.is_empty():
			next = "%s — с ур. %d" % [entry[1], entry[3]]
	if not next.is_empty():
		line += "; следующий: " + next
	if closed > 0:
		line += "; ещё %d (7 AP) откроет сюжет" % closed
	return line + "; AP за ход %d" % hero.ap


## The item list of the chosen kind: every entry the disc names, how many are held (the count's spin box starts there).
func _fill_cheat_items() -> void:
	var item: OptionButton = cheat_ui.item
	var keep := item.get_item_id(item.selected) if item.selected >= 0 else -1
	item.clear()
	for entry in core.cheat_items(cheat_ui.item_kind.selected):
		item.add_item("%s (есть %d)" % [entry[1], entry[2]], entry[0])
		item.set_item_metadata(item.item_count - 1, entry[2])
	if item.item_count > 0:
		var index := maxi(item.get_item_index(keep), 0) if keep >= 0 else 0
		item.select(index)
		cheat_ui.item_count.value = item.get_item_metadata(index)


func _exit_tree() -> void:
	_close_hd_log()
