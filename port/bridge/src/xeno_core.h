#pragma once

#include "xeno_session.h"

#include <godot_cpp/classes/array_mesh.hpp>
#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_vector2_array.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>

#include <mutex>
#include <unordered_map>

namespace godot
{
	/** The game for GDScript: open a disc, step frames with buttons, fill meshes with what the frame draws. */
	class XenoCore : public RefCounted
	{
		GDCLASS(XenoCore, RefCounted)

	public:
		/** USA disc 1 from the folder, or with translation_image (a .cue or .bin) the translation's disc 1 (FSession::Open). */
		String open(const String& games_folder, const String& translation_image = String());
		/** "en", or the translation's language ("ru"). */
		String language() const;
		/**
		 * The disc images in a folder found by content (Xeno::SurveyDiscs): {usa_disc_1, usa_disc_2, russian_disc_1,
		 * russian_disc_2: the first such file or "", others: [[file, why not played]]}.
		 */
		Dictionary survey_discs(const String& folder) const;
		/** The field's open message windows, frontmost first: {map, index, codes (PackedByteArray, the whole message)}. */
		Array open_messages() const;
		String set_pack(const String& folder);
		int pack_pictures() const;
		void set_options(bool hd, bool original_shadows, bool soft_shadows);
		/** A "page:" surface's texture page with the pack's pictures laid in (RGBA8, PageScale * 256 square). */
		Ref<Image> page_image(const String& key) const;
		/**
		 * The original texels' kinds over a surface's pack picture (R8: 255 blends, 128 plain, 0 transparent;
		 * FSession::TexelKinds), null when none were noted.
		 */
		Ref<Image> texel_kinds(const String& key) const;
		String enter_field(int map);
		/** The game as it stands (a state loaded) entering field map N (for checks: a map at that point of the story). */
		String enter_field_keeping(int map);
		/** The original texels of the pack's pictures (FSession::SetAliasIndex): pictures found by content; empty path: off. */
		String set_alias_index(const String& path);
		/** The saves of a memory card image as text (slot -1), or that slot loaded and the game going on from it (empty, or an error). */
		String load_card(const String& path, int slot);
		/** The game's own saves (the File screen, the title's Continue) kept in this folder (Weltall's FSaveStore); empty, or an error. */
		String set_save_folder(const String& folder);
		String save_state(const String& path);
		String load_state(const String& path);
		/** F6's state to go back to taken at quiet moments every N frames (FSession::SetRollingState; 0 off), and what that has cost. */
		void set_rolling_state(int every);
		Dictionary rolling_stats() const;
		/**
		 * F6's state into the file (FSession::WriteReportState): {source ("now", where the rolling state came from, or ""),
		 * error, inputs (each frame's buttons since it), vblanks, turbo_frames, cheats, seconds}.
		 */
		Dictionary write_report_state(const String& path);
		/** F6's text of the frame shown, built again without a step (FSession::FrameReport). */
		String frame_report();
		String step(int buttons, int stick_x, int stick_y, bool analog);
		int vblanks_per_frame() const;
		double vblank_seconds() const;
		/** Live play: the vertical blanks due as real time passes (Weltall's FTickClock: at most 4 after a stall). */
		int vblanks_due(double seconds);
		/** The game's sound: its rate (44,100 Hz), how far ahead a listener keeps it, the switch to a listener, its samples. */
		int sound_rate() const;
		int sound_lead_frames() const;
		String hear(int latency_frames);
		/** The next frames of the heard sound as (left, right) in -1..1; empty while the sound is not heard. */
		PackedVector2Array render_sound(int frames);
		/** The field's screen wave: each cell's 4 corners as (x, y waved, x, y shown) in 320 x 224 screen pixels; empty: none (FSession::ScreenWave). */
		PackedFloat32Array screen_wave() const;
		Dictionary info() const;
		/** VRAM as RG8 pixels (the 16-bit units' low and high bytes), 1024 wide. */
		PackedByteArray vram() const;
		int vram_rows() const;
		/** Clears the mesh and adds its surfaces; returns each surface's [blend mode, pack picture path or ""] in order. */
		Array fill_world(const Ref<ArrayMesh>& mesh);
		Array fill_screen(const Ref<ArrayMesh>& mesh);
		/**
		 * The 2D layer as canvas meshes, one ArrayMesh per run (meshes grows to as many as are needed; those past the runs
		 * are left as they were): 2D vertices in screen pixels, CUSTOM0 the packed C0 and C1, CUSTOM1 C2. Returns each
		 * run's [blend mode, picture, VRAM source, unlit, drawing area (Vector4, -1 for none)] in drawing order.
		 */
		Array fill_flat(const Array& meshes);
		/** World (the game's axes) to the view in Godot's axes. */
		Transform3D view_transform() const;

		/**
		 * The cheat panel (FSession::CheatState): {can_edit, in_battle, can_win, enemies_left, program, gold, encounters_off,
		 * turbo, pace, party: [{id, name, level, ether_level, exp, ether_exp, exp_next, ether_next, hp, max_hp, ep, max_ep,
		 * attack, defense, agility, ether, ether_defense, hit, evade, gear, gear_name, gear_hp, gear_max_hp, fuel, max_fuel,
		 * deathblows: [[number, name, learned, level, percent, tier_open, buttons]], deathblows_learned, deathblows_total,
		 * gear_deathblows, ap}],
		 * items: [[id, name, count]] (the Items list's entries held)}.
		 */
		Dictionary cheat_state() const;
		/** One of the inventory's lists (0 items, 1 weapons, 2 accessories, 3 gear weapons, 4 gear parts): [[id, name, count]], every entry the disc names. */
		Array cheat_items(int list) const;
		/** A cheat (FSession::Cheat: "money:N", "exp:fei:N", "level:fei:K", "fill:party", "gears", "item:0:id:count", "win", "encounters:0", "turbo:N"); empty, or why not. */
		String cheat(const String& command);
		/** For checks: the running field asks for the Battling arena with FE BF's six bytes (FSession::AskBattling); empty, or why not. */
		String ask_battling(const PackedInt32Array& parameters);
		/** For checks: the running field asks for movie Number of the disc in the drive full screen (FSession::AskFieldMovie); empty, or why not. */
		String ask_field_movie(int number, int end_frame);
		/** The pace the game runs at now (the turbo where Weltall's fast-forward would run, else 1), and the programs started so far. */
		int game_pace() const;
		int program_runs() const;

		/** The console powered on as a player starts it: the kernel's notice, the opening movie, the title. */
		String power_on();
		/** One of the frame's VRAMs (0 the scene's, 1 the 2D layer's own, 2 the overlay's) as RG8 rows; empty where there is none. */
		PackedByteArray vram_of(int source);
		/** Changes whenever vram_of(source) may have (0: none). */
		int64_t vram_stamp(int source) const;
		/** The movie's picture on screen (RGBA8), null when none shows. */
		Ref<Image> movie_image() const;
		/**
		 * The picture of the screen the field took (its count of pictures taken), given as the frame the window showed last:
		 * kept for the screen's pixels the field copies into VRAM, and returned with its black pixels transparent (an opaque
		 * picture's black lets what lies below through).
		 */
		Ref<Image> take_screen_picture(const Ref<Image>& image, int taken);

		/** Lazy pictures: the bridge draws from the pack only what is ready, and asks for the rest. */
		void set_lazy_textures(bool lazy);
		void mark_texture_ready(const String& key);
		PackedStringArray wanted_textures();
		/** A picture to load on a worker thread: a "page:" key (what it needs taken now) or a pack picture's path; returns the job. */
		int texture_job(const String& key);
		/** Builds a job's picture (on any thread); take_built then hands it over (null until it is built). */
		void build_job(int job);
		Ref<Image> take_built(int job);

		XenoCore();

	protected:
		static void _bind_methods();

	private:
		struct FJob
		{
			bool bPage = false;
			std::string Path;
			Xeno::FPageJob Page;
		};
		std::mutex JobLock;
		std::unordered_map<int, FJob> Jobs;
		std::unordered_map<int, Ref<Image>> Built;
		int NextJob = 1;
		Xeno::FSession Session;
		std::vector<Xeno::FSurface> World;
		std::vector<Xeno::FSurface> Screen;
		std::vector<int16_t> SoundScratch;
	};
}
