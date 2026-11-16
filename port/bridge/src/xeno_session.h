// The game as WeltallCore runs it, seen through flat buffers: no Godot headers here and no Weltall headers in
// this file either, so the two libraries' names and macros never meet (the Godot side only sees this header).
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace Weltall
{
	class FGameLoop;
	class FGameSession;
	class FVram;
	struct FSpriteQuad;
}

namespace Xeno
{
	/** How a surface's pixels meet what lies below: the PS1 GPU's modes, plus opaque. */
	enum class EBlend : int
	{
		Opaque = 0,
		Average = 1, // B/2 + F/2
		Add = 2, // B + F
		Subtract = 3, // B - F
		AddQuarter = 4, // B + F/4
	};
	inline constexpr int BlendCount = 5;

	/**
	 * Triangles, three vertices each, with everything the shaders need per vertex:
	 * Pos (x, y, z), Normal (x, y, z), Color (r, g, b, 1; 128/255 leaves a texel as it is),
	 * Uv (texel u, v in the page; for a surface with a pack texture, 0-1 across that picture),
	 * C0 (page x, page y, depth 0/1/2, 3 untextured or 5 a soft shadow, flags: 1 raw, 2 semi-transparent, 4 every texel blends),
	 * C1 (clut x, clut y, 1 = spread over the whole display, the place in a battle frame's drawing order: 0 none, else
	 *    later = more, in 0..1, which the battle's shaders write as the depth),
	 * C2 (first u, first v, last u, last v; -1 when unclamped),
	 * C3 (on the 2D layer, the rectangle of screen pixels the primitive is drawn inside, as the GPU's drawing area limits
	 *    it: left, top, right, bottom; -1 everywhere for none).
	 */
	struct FMeshBuffers
	{
		std::vector<float> Pos, Normal, Color, Uv, C0, C1, C2, C3;

		void Clear();
		std::size_t Vertices() const { return Pos.size() / 3; }
	};

	/** The VRAMs a frame's surfaces are textured from (FSurface::Vram, FSession::VramOf). */
	enum EVramSource : int
	{
		/** The scene's: the field's, the battle's (the 2D layer of both draws from it too). */
		SceneVram = 0,
		/** The 2D layer's own where a program draws it from a VRAM of its own: a menu's, the boot notice's. */
		ScreenVram = 1,
		/** The pictures a display draws over the game from a VRAM of their own: a chapter's card. */
		OverlayVram = 2,
	};
	inline constexpr int VramSourceCount = 3;

	/**
	 * Triangles drawn alike: one blend mode, and VRAM's texels (Texture empty; Vram says which VRAM), one picture of the
	 * pack (its path), a texture page the pack's pictures are laid into ("page:" and its texture view, FSession::PageImage),
	 * the movie's picture on screen ("movie:", FSession::MovieImage), or the picture of the screen the field took
	 * ("cover:", the frame shown last, which the display captures).
	 */
	struct FSurface
	{
		EBlend Blend = EBlend::Opaque;
		std::string Texture;
		FMeshBuffers Mesh;
		int Vram = SceneVram;
		/** Drawn as the game's own picture, unlit, behind everything else (the field's panorama: C1's w, its order, is 0). */
		bool bUnlit = false;
		/**
		 * On the 2D layer, the GPU's drawing area every primitive of the run is drawn inside (screen pixels: left, top,
		 * right, bottom; -1 everywhere for none): a run ends where the area changes, so a display can clip a run as a whole.
		 * The same rectangle is in each vertex's C3.
		 */
		std::array<float, 4> Area{-1.0f, -1.0f, -1.0f, -1.0f};
	};

	/** What a texture page of a "page:" surface is built from, taken on the game's thread so a worker can build it alone. */
	struct FPageJob
	{
		/** The page's own texels through its CLUT, 256 x 256 RGBA (alpha 0 where the texel is transparent). */
		std::vector<uint8_t> Texels;
		struct FPart
		{
			std::string Path;
			int U = 0, V = 0, Width = 0, Height = 0, FromU = 0, FromV = 0, UploadUnitsWide = 1, UploadUnitsHigh = 1;
		};
		/** Each upload under the page the pack has a picture of, as it lies in the page. */
		std::vector<FPart> Parts;
		/** Texels per VRAM unit of the page (4, 2, 1). */
		int Per = 1;
	};

	/** What the display shows now, by the program and its state. */
	enum class EScreenKind : int
	{
		Blank = 0,
		Field = 1,
		Battle = 2,
		/** A menu the field runs inside itself, over the field's last picture. */
		Menu = 3,
		/** The Movie program. */
		Movie = 4,
		/** A movie the field plays full screen (alone, or with its message windows over it). */
		FieldMovie = 5,
		/** The kernel's boot notice. */
		Notice = 6,
		/** The World Map program (its menu shows as Menu). */
		WorldMap = 7,
		/** The Battling program (the gear arena): its menus, its versus screen, its bouts and winner screen, its pause. */
		Battling = 8,
	};

	/** One of a character's Deathblows as the cheat panel shows it (FCheatHero::Deathblows). */
	struct FCheatDeathblow
	{
		/** Its number in the character's list (0-12; 7 and up the 7-AP tier) and its name in the disc's name table. */
		int Number = 0;
		std::string Name;
		bool bLearned = false;
		/** The level the growth table asks for before the battle's end learns it, and how far the practice has come (the Skills screen's percent). */
		int Level = 0;
		int Percent = 0;
		/** The 7-AP tier, which the battle's end learns only once the story opens it (the story flags' bit 14). */
		bool bUpperTier = false;
		bool bTierOpen = true;
		/** The presses before the Fierce one that finish it (the battle program's pattern: W weak, S strong, F fierce), empty when no pattern completes it. */
		std::string Buttons;
	};

	/** A party member as the cheat panel shows it (FSession::CheatState): the character's record in the game's state. */
	struct FCheatHero
	{
		int Character = -1;
		std::string Name;
		int Level = 0;
		int EtherLevel = 0;
		uint32_t Exp = 0;
		uint32_t EtherExp = 0;
		/** The EXP still wanted for the next level and ether level (the record keeps what is left, not a total). */
		uint32_t ExpToNext = 0;
		uint32_t EtherExpToNext = 0;
		int Hp = 0, MaxHp = 0, Ep = 0, MaxEp = 0;
		int Attack = 0, Defense = 0, Agility = 0, Ether = 0, EtherDefense = 0, Hit = 0, Evade = 0;
		/** The gear the character pilots (-1 none), its name, HP and fuel. */
		int Gear = -1;
		std::string GearName;
		int64_t GearHp = 0, GearMaxHp = 0;
		int Fuel = 0, MaxFuel = 0;
		/** The character's Deathblows (those its name table names; none for a character the battle's end teaches none), and its gear Deathblows' word (learned-skills +4). */
		std::vector<FCheatDeathblow> Deathblows;
		int GearDeathblows = 0;
		/** The AP a turn gives (learned-skills +17h), which bounds the presses a Deathblow's pattern can take. */
		int ApPerTurn = 0;
	};

	/** An entry of one of the inventory's lists (FSession::CheatItems): its number in the list, its name on the disc, how many are held. */
	struct FCheatItem
	{
		int Id = 0;
		std::string Name;
		int Count = 0;
	};

	/** What the cheat panel can read and do now (FSession::CheatState). */
	struct FCheatState
	{
		/** The game's state may be changed now: the field or the world map runs (a battle keeps its own copies of the party). */
		bool bCanEdit = false;
		/** A battle is being fought; and it can be won now (its end not yet decided). */
		bool bInBattle = false;
		bool bCanWin = false;
		/** The enemies still standing in the battle. */
		int EnemiesLeft = 0;
		int Program = -1;
		uint32_t Gold = 0;
		std::vector<FCheatHero> Party;
		/** The items list's entries held (list 0, the Items menu's). */
		std::vector<FCheatItem> Items;
		/** Random battles off (the game's own setting, Balance.Encounters = None), and the turbo asked for. */
		bool bEncountersOff = false;
		int Turbo = 1;
	};

	/** A picture of the pack read as RGBA rows (the Godot side reads files and decodes BC7 and PNG); false when it cannot. */
	using FReadPicture = std::function<bool(const std::string& Path, std::vector<uint8_t>& Rgba, int& Width, int& Height)>;

	/** Texels across a texture page the pack's pictures are laid into: the page's 256 times this. */
	inline constexpr int PageScale = 4;

	/** How the drawing is made. */
	struct FDrawOptions
	{
		/** Pictures of the texture pack where it has them. */
		bool bHd = true;
		/** The game's own round shadows under the characters. */
		bool bOriginalShadows = true;
		/** Those shadows as soft dark ellipses where the game puts them (depth 5 in C0, Uv 0-1 across), not its texels. */
		bool bSoftShadows = false;
	};

	/** What a frame says about itself, for checks and the window title. */
	struct FFrameInfo
	{
		int Program = -1;
		int Map = -1;
		bool bField = false;
		bool bRunning = false;
		bool bSceneDrawn = false;
		int Tick = 0;
		int Leader = -1;
		std::array<int, 3> LeaderPosition{};
		/** The frame of the leader's sprite file it shows (the user's layouts number them from 0, this from 1). */
		int LeaderFrame = -1;
		bool bMessageOpen = false;
		int Characters = 0;
		std::array<uint8_t, 3> Background{};
		float ProjectionDistance = 512.0f;
		/** Textured primitives of the last frame built: by the pack's upload names, by the drawn rectangle's, from VRAM. */
		int HdUpload = 0;
		int HdRect = 0;
		/** Sprite pieces cut along the uploads they span, each part from its own picture. */
		int HdSplit = 0;
		int FromVram = 0;
		/**
		 * Textured primitives whose pack picture holds only some of the texels they show (a drawn rectangle's picture a
		 * column short): cut at the picture's edge, the rest from VRAM. The sprite pieces among them (counted partial too),
		 * and the 2D layer's (not counted wholly from the pack).
		 */
		int HdBeyond = 0, SpriteBeyond = 0, ScreenBeyond = 0;
		/**
		 * Since the last BuildWorld: semi-transparent primitives drawn from a pack picture some of whose texels do not
		 * blend (FSession::TexelKinds), and a battle's quads that are no sprite's part (the HUD sheet's glyphs, drawn edge
		 * to edge).
		 */
		int KindsPlainDrawn = 0, BattleGlyphs = 0;
		/**
		 * Since the last BuildWorld: semi-transparent primitives drawn from a pack picture with a transparent texel among
		 * their own that has a blending one within two texels: the picture's rim over it blends with that texel now (it
		 * was drawn plain, a dark outline where the primitive's colour fades), how many such transparent texels, and the
		 * primitives among them that are a scene's models on a page with pictures laid in.
		 */
		int KindsRimDrawn = 0, KindsRimTexels = 0, KindsRimScenery = 0;
		/** Regions without a picture so far: no upload under them, more than one, a name the pack lacks. */
		int MissNoUpload = 0, MissSplit = 0, MissName = 0;
		/** Drawn-rectangle hits so far by the column tried: a texel before Weltall's U, at it, a texel after. */
		std::array<int, 3> RectHitsByShift{};
		int PageHits = 0;
		/** Counts the maps loaded: the textures of "page:" surfaces belong to one map. */
		int MapLoads = 0;
		/**
		 * The last BuildWorld's sprite pieces that ask for a pack picture (the game's shadows not among them): drawn wholly
		 * from the pack (one picture, or cut along uploads with every part found), cut with at least one part from VRAM, or
		 * nothing from the pack.
		 */
		int SpritePieces = 0, SpriteHd = 0, SpritePartial = 0, SpriteVram = 0;
		/** Of the sprite pieces not wholly from the pack: no tracked upload under them at all; every upload under them in the pack. */
		int SpriteNoUpload = 0, SpriteAllInPack = 0;
		/** Sprite pieces cut along uploads whose parts leave some of their texels uncovered (drawn with holes). */
		int SpriteSplitGaps = 0;
		/** The last BuildScreen's textured primitives, those drawn wholly from the pack, and the same two kinds of miss. */
		int ScreenTextured = 0, ScreenHd = 0, ScreenNoUpload = 0, ScreenAllInPack = 0;
		/**
		 * Sprite pieces (of the last BuildWorld) and 2D primitives (of the last BuildScreen) drawn from VRAM, wholly or in a
		 * part cut along uploads, only because their pack picture is not loaded yet (SetLazyTextures); counted among the
		 * pieces from VRAM (a whole piece) or the whole ones (a part of a cut piece) above.
		 */
		int SpriteWaiting = 0, ScreenWaiting = 0;
		/**
		 * The last BuildWorld's textured scenery polygons: from a page with the pack's pictures laid in, or from VRAM; and
		 * of the first, those whose texels lie (partly) in uploads the pack has no picture of (they show the page's own
		 * texels there, scaled up).
		 */
		int SceneryHd = 0, SceneryVram = 0, SceneryHdMixed = 0;
		/**
		 * The last BuildWorld's field scenery polygons lying on another the PS1 draws before them (a picture on a wall, a rug
		 * on a floor): drawn a hair nearer the eye along its line of sight, so the depth buffer gives them the PS1's order.
		 */
		int SceneryLaid = 0;
		/**
		 * The Battle program runs and its show has begun: BuildWorld and BuildScreen draw its frame. In battle the scene is
		 * drawn as the PS1 draws it, unlit (no sun, no soft shadows), in the frame's own drawing order (C1's w per vertex).
		 */
		bool bBattle = false;
		bool bUnlit = false;
		/** The screen the 2D layer's pixels are of (the field's and the battle's are both 320 x 224). */
		int ScreenWidth = 320, ScreenHeight = 224;
		/** In battle: the show's frame number, the HUD's primitives and a hash of where they are (a cursor moved changes it). */
		int BattleStep = 0, HudPrimitives = 0;
		uint32_t HudHash = 0;
		/** In battle: the links of the frame's drawing order in the scene (before the fade and the HUD) and after them. */
		int SceneLinks = 0, OverLinks = 0;
		/** The loop's stage (FGameLoop: 0 boot, 1 a program, 2 soft reset, 3 stopped) and what the display shows. */
		int Stage = -1;
		EScreenKind Screen = EScreenKind::Blank;
		/** A menu runs: its mode, its frame's number and primitives. */
		int MenuMode = -1, MenuPrimitives = 0;
		uint32_t MenuNumber = 0;
		/** The 2D layer the last BuildScreen made: its primitives and a hash of what they draw and where (a cursor moved changes it). */
		int ScreenPrimitives = 0;
		uint32_t ScreenHash = 0;
		/** A movie plays (the Movie program's, or the field's): pictures shown so far, the movie's frame on screen, the picture's size, the field's view of it. */
		int MoviePicture = 0, MovieFrame = 0, MovieWidth = 0, MovieHeight = 0, MovieView = -1;
		/** The movie the picture shown is of (its disc, 1 or 2, 0 none; its number in the disc's movie group, -1 none) and its frame number. */
		int MovieDisc = 0, MovieNumber = -1, MovieShownFrame = 0;
		/** The disc the movie is of as the display keys replacements ("usa.disc1", "rus.disc1", "rus.disc2"); empty: none shows. */
		std::string MovieSource;
		/** The disc in the drive (1 or 2, 0 before a session), as DiscId names it, and its image's file. */
		int DriveDisc = 0;
		std::string DriveDiscId, DriveDiscFile;
		/**
		 * A disc the game asked for and the bridge did not find (1 or 2, 0 none): the game waits on it until the player
		 * puts its image where the bridge looks ("rus": the Russian translation's disc, "usa": the USA release's) and
		 * confirms. The folder looked in first (the translation's image's own, else the games folder).
		 */
		int DiscWanted = 0;
		std::string DiscWantedKind, DiscWantedFolder;
		/** The discs the game has (bit 0 disc 1, bit 1 disc 2): the one opened, and the other once the bridge has found it. */
		int DiscsHeld = 0;
		/** The field's picture of the screen: drawn this frame, its count of pictures taken; rectangles of VRAM holding screen pixels. */
		bool bCover = false, bCoverScreen = false;
		int CoverTaken = 0, ScreenInVram = 0;
		/** On the field: the player has control, and the menu button is locked (Triangle opens nothing). */
		bool bPlayerControlled = false, bMenuLocked = false;
		/** A chapter's card shows at this level (0 none, 128 whole). */
		int CardLevel = 0;
		/** Primitives the last BuildWorld and BuildScreen drew from VRAM while their picture was loading (lazy textures). */
		int Waiting = 0;
		/** The lines of the screen the scene is projected for (the camera's height): the world map's 216, the arena's 218, the others' 224. */
		int SceneLines = 224;
		/**
		 * The World Map program runs: drawn as the battle is (unlit, in its frame's order). Its playable scene (0-7), how the
		 * party travels (1 on foot, 2 gears, 4/5/7 the ship), the place record stood on (-1 none), the camera's yaw (4096 a
		 * turn); LeaderPosition is where the party (or its ship) stands in whole units.
		 */
		bool bWorldMap = false;
		int WorldScene = -1, TravelMode = 0, MapPlace = -1, CameraYaw = 0;
		/** The last BuildWorld's world map polygons, by layer (EWorldMapLayer: terrain, sky, horizon, sprite, model, shadow, billboard, cloud, particle, gear, effect), and one-sided triangles dropped facing away. */
		int MapPolygons = 0, MapOneSidedDropped = 0;
		/** Of its scenery, pieces whose texels the program animates (looked up upload by upload each frame), and those drawn from the pack. */
		int MapAnimatedPieces = 0, MapAnimatedHd = 0;
		std::array<int, 11> MapLayers{};
		/** The level of the program's own fade shown (-1 none). */
		int FadeLevel = -1;
		/**
		 * The Battling program runs (the gear arena): drawn as the world map is (its frame is in the world map's form: unlit,
		 * in its frame's order, its own projection on 218 lines). Its stage (EBattlingGameStage: 0 menus, 1 versus, 2 bout),
		 * the fight's state (1 fighting, 0 paused, 3 leaving...), round, the winner of the last round and the bout's result
		 * as the field reads it; each side's gear, HP of its maximum, and place in the arena (whole units); the frame's
		 * columns (640 on the winner screen), its pause's blurs, whether it is the demonstration's (trails).
		 */
		bool bBattling = false;
		int ArenaStage = -1, ArenaState = -1, ArenaRound = 0, ArenaWinner = 0, ArenaResult = 0;
		std::array<int, 2> ArenaGears{}, ArenaHp{}, ArenaMaxHp{};
		std::array<std::array<int, 3>, 2> ArenaPositions{};
		int ArenaColumns = 320, ArenaBlurs = 0;
		bool bArenaTrails = false;
		/** The story's progress (the game's saved variable 0). */
		int Story = -1;
	};

	/** One stretch of a sprite piece as the bridge draws it (FSession::ClassifySpriteQuad). */
	struct FSpritePieceDraw
	{
		/** The pack picture's path; empty: VRAM's texels. */
		std::string Texture;
		/** Where in the piece's quad: s and t (0-1 from its corner 0 toward corners 1 and 2) of the stretch's corner 0 and corner 3. */
		std::array<float, 4> Cell{};
		/** What it shows there: u, v at corner 0 and at corner 3 (texels of the page for VRAM, 0-1 across a picture). */
		std::array<float, 4> Source{};
	};

	/** How the bridge draws one sprite piece from the pack, and why (FSession::ClassifySpriteQuad). */
	struct FSpritePieceVerdict
	{
		/** 0 wholly from the pack, 1 partly, 2 from VRAM (the bridge's SpriteHd / SpritePartial / SpriteVram). */
		int Kind = 2;
		/** The texels the piece shows (its last-texel rectangle) and how many of them come from VRAM. */
		int Texels = 0;
		double TexelsFromVram = 0.0;
		/** The piece's texels: page, CLUT, first texel and size, as the lookup took them. */
		int PageX = 0, PageY = 0, Depth = 0, ClutX = 0, ClutY = 0, U = 0, V = 0, Width = 0, Height = 0;
		/**
		 * Each name the lookup tried, in its order, with what it found: per upload part under the piece its name, whether
		 * it covers the piece, whether the pack has it by its own palette, the reduced one or a palette agreeing on its
		 * colours, and every other palette the pack has that upload under; then the drawn rectangle's name.
		 */
		std::string Tried;
		/** The uploads under the piece by their names' two halves (upload, palette), as the pack names them. */
		std::vector<std::array<uint32_t, 2>> Names;
		/** Miss class: "" (whole), "a" no picture of any upload under it under any palette, "b" pictures only under other palettes, "c" every upload under it has its picture, "d" no upload tracked under it. */
		std::string Miss;
		std::vector<FSpritePieceDraw> Draws;
	};

	/** F6's state as FSession::WriteReportState wrote it, and the frames from it to the frame shown. */
	struct FReportState
	{
		/** "now" (the game is quiet: the state of this moment, as F5's), the rolling state's origin ("a quiet moment", "F5's state", "the state loaded"), or empty: none written. */
		std::string Source;
		/** Why none was written, or why the state of this moment was not taken. */
		std::string Error;
		/** The frames played since the state: each frame's buttons (FPadState bits), their vertical blanks, how many the turbo ran, the cheats asked for since. */
		std::vector<uint16_t> Inputs;
		long long Vblanks = 0;
		int TurboFrames = 0;
		int Cheats = 0;
		/** Real time since the state was taken. */
		double Seconds = 0.0;
	};

	/** What taking the rolling state has cost so far (FSession::SetRollingState). */
	struct FRollingStats
	{
		int Every = 0;
		long long Tries = 0, Captures = 0;
		double UsecTotal = 0.0, UsecLongest = 0.0, FailedTryUsecLongest = 0.0;
	};

	/** Something the frame holds that the bridge does not draw, or draws by a stand-in: its name and how many of it this frame has. */
	struct FUnhandled
	{
		const char* Name = "";
		int Count = 0;
	};

	class FSession
	{
	public:
		FSession();
		~FSession();

		/**
		 * Opens USA disc 1 from the folder and powers the session on; an error, or empty. With TranslationImage (a .cue or
		 * .bin), the game plays that disc instead: a translation of disc 1 the bridge knows by its program (the Russian),
		 * its data as it is and its program's own changes the core lacks (OpenTranslation).
		 */
		std::string Open(const std::string& GamesFolder, const std::string& TranslationImage = {});
		/** The text the game plays: "en" (USA disc 1) or the translation's ("ru"); empty before Open. */
		const std::string& Language() const;
		/** A message window open in the field, as the core holds it. */
		struct FOpenMessage
		{
			/** The map whose table the message is in, and its number there (-1 where it is not one of the table's). */
			int Map = -1;
			int Index = -1;
			/** The window's lines as it was laid out (its frame's height), and whether it shows a portrait. */
			int Lines = 0;
			bool bPortrait = false;
			/** The whole message the window types, from its start to its end code (00) included. */
			std::vector<uint8_t> Codes;
		};
		/** Every message window open in the field now, frontmost first. */
		std::vector<FOpenMessage> OpenMessages() const;
		/**
		 * The console powered on again (a new game's state) with the disc, sound, pack and options already opened: a clean
		 * game for each map of a sweep without reading the disc and the pack again; an error, or empty.
		 */
		std::string Restart();
		/** Whether the opened disc holds field map Number, not the mastering tool's stand-in (a second disc has those for maps it never loads). */
		bool HoldsFieldMap(int Number) const;
		/** Reads the names of a Beetle PSX HW texture pack's pictures (.bc7 and .png); an error, or empty. */
		std::string SetPack(const std::string& Folder);
		/**
		 * Reads the names of the pack's whole-page pictures (the user's core's -texture-replacements-pages: a texture page,
		 * 256 rows of its width in units, and the CLUT), the last resort for sprite pieces; an error, or empty.
		 */
		std::string SetPagePack(const std::string& Folder);
		int PackPictures() const;
		void SetPictureReader(FReadPicture Reader);
		void SetOptions(const FDrawOptions& Options);
		/**
		 * The texture page of a "page:" surface (its key after "page:") as RGBA rows, PageScale * 256 square: the page's
		 * own texels through its CLUT, each upload with a picture in the pack laid over them as Beetle scales it.
		 */
		std::vector<uint8_t> PageImage(const std::string& Key, int& Size) const;
		/** What PageImage builds from, taken now (on the game's thread); BuildPage builds it anywhere, from that alone. */
		FPageJob PageJob(const std::string& Key) const;
		static std::vector<uint8_t> BuildPage(const FPageJob& Job, const FReadPicture& Reader, int& Size);
		/**
		 * Which texels of a pack picture (a surface's texture) blend where a semi-transparent primitive drawn from it blends:
		 * the kind of the original texel under each, bit 15 of its colour, as the GPU decides it texel by texel (the pack's
		 * pictures do not carry it; Weltall's renderer likewise gives a picture without kinds those of the texel under it,
		 * TextureModLibrary.h). Width x Height bytes over the picture: 255 where the texel blends, 128 where it is drawn
		 * plain, 0 where it is transparent (colour 0, which has no kind: the display gives the picture's rim over it the
		 * kind of the nearest drawn texel, main.gd PICTURE_KINDS); empty for a picture no semi-transparent primitive has
		 * been drawn from (the display then lets every texel blend).
		 */
		std::vector<uint8_t> TexelKinds(const std::string& Key, int& Width, int& Height) const;
		/** Whether some texels of the picture blend and some do not (a subtracting run of it then takes two passes). */
		bool TexelKindsMixed(const std::string& Key) const;
		/**
		 * Pictures are drawn from the pack only once the display has them (MarkTextureReady): until then a surface is drawn
		 * from VRAM, its picture asked for (TakeWantedTextures). Off (the default, headless tools): every picture is ready.
		 */
		void SetLazyTextures(bool bLazy);
		void MarkTextureReady(const std::string& Key);
		/** The "page:" textures are the map's: a new scene's are not ready until loaded again. */
		void ForgetReadyPages();
		/** The pictures asked for since the last call and not ready: "page:" keys and pack picture paths. */
		std::vector<std::string> TakeWantedTextures();
		/** A new game entering field map Number (Weltall's numbering: our disc file = 606 + 2 * Number). */
		std::string EnterField(int Number);
		/** The game as it stands (a state loaded, its story) entering field map Number, for sweeps from a point of the story. */
		std::string EnterFieldKeeping(int Number);
		/**
		 * A new game's party entering the world map's Scene (1 the playable one; 8-18 cutscenes) at its arrival Entrance with
		 * the story at Story, as Weltall's sorting audit enters each era (Tests/Tools/SortingAuditWorldMapRun.cpp, StartMap).
		 */
		std::string EnterWorldMap(int Story, int Scene, int Entrance);
		/** The arrivals (FWorldMapEntrance ids) of the world map scene running now; empty off the world map. */
		std::vector<int> WorldMapArrivals() const;
		/**
		 * The running field asks for the Battling arena with the six bytes of the field's FE BF (from, kind, the two gears,
		 * wins a set, level), as that instruction and Weltall's arena audit ask (Tests/Tools/SortingAuditArenaRun.cpp): the
		 * next frames leave the field into the arena. An error where no field runs.
		 */
		std::string AskBattling(const std::array<int, 6>& Parameters);
		/**
		 * For checks: the running field asks for movie Number of the disc in the drive full screen, skippable, waiting for
		 * frame EndFrame, as FE 60 of kind 2 asks (EventOpsMovies.cpp, PlayMovie) and Weltall's movie tests ask
		 * (Tests/WeltallCore/Game/FieldMovieContentTests.cpp, AskForMovie). An error where no field runs.
		 */
		std::string AskFieldMovie(int Number, int EndFrame);
		/**
		 * For finding where the story starts the arena: every FE BF (StartBattling) in the event scripts of maps First to
		 * Last as the disc holds them, a line each: map, offset, its six operands (constants as numbers, variables as vXXXX).
		 */
		std::string DebugBattlingSites(int First, int Last) const;
		/** The console powered on as a player starts it: the kernel's notice, the opening movie, the title (FGameLoop::PowerOn). */
		std::string PowerOn();
		/**
		 * The saves of a memory card image (Listing: one line each); with Slot >= 0 that save loaded and the game going on
		 * where it was made, as the game's own load leaves it (the party by the save point).
		 */
		std::string LoadCard(const std::string& CardPath, int Slot, std::string& Listing);
		/**
		 * The game's own saves (the File screen's, the title's Continue) kept in Folder as Weltall keeps them (FSaveStore:
		 * eight stores of 15 slots, a store a memory card); an error, or empty. Without it the File screen shows empty cards.
		 */
		std::string SetSaveFolder(const std::string& Folder);
		/** The game now as Weltall's save state file (only where the player has control, as the core allows); an error, or empty. */
		std::string SaveState(const std::string& Path);
		/**
		 * The game going on from a save state file, at any moment, as Weltall's game screen loads one (GameLoopScreenStates.cpp,
		 * LoadState; GameLoopScreen.cpp, Start): the file read first (a bad one leaves the game running), then the sound
		 * started afresh, the console powered on afresh and the state taken over it, everything drawn from the old game
		 * forgotten. When the state cannot be entered, the console powers on from the start, as Weltall's does. An error, or empty.
		 */
		std::string LoadState(const std::string& Path);
		/** One frame of the game with the buttons (FPadState bits, 1 = held) held through its vertical blanks. */
		std::string Step(uint16_t Buttons, uint8_t StickX, uint8_t StickY, bool bAnalog);

		/**
		 * F6: the state a frame report goes back to. With Every > 0 the game's state is taken at a quiet moment (where F5
		 * would save) once Every frames have run since the last (tried each frame after that until the game is quiet), F5's
		 * and a load's state count too; the frames since are kept (their buttons). 0 (the default): none taken.
		 */
		void SetRollingState(int Every);
		FRollingStats RollingStats() const;
		/** F6's state into Path: the game now where it is quiet (as F5), else the newest state taken (SetRollingState). */
		FReportState WriteReportState(const std::string& Path);
		/**
		 * F6: the frame shown, built again without a step of the game (BuildWorld, BuildScreen; nothing of the game changes):
		 * a summary of what is drawn not from the pack (by upload name, size, where, why; sprites with their actor, set and
		 * frame; models' textures apart), the frame's classes the bridge leaves undrawn, then every primitive as the
		 * XENO_DUMP_2D, XENO_DUMP_OBJECTS and XENO_TALLY_LOG=2 lines give them, the field's scenery polygons with their place
		 * in the PS1's order and depth, its sprite pieces.
		 */
		std::string FrameReport();

		int VblanksPerFrame() const;
		static double VblankSeconds();
		/**
		 * Live play: the vertical blanks that fall due as Seconds of real time pass, as Weltall's game screen counts them
		 * (FTickClock): after a stall no more than FTickClock::MaxTicksPerAdvance (4) run at once, the rest of the time dropped.
		 */
		int VblanksDue(double Seconds);

		/** The game's sound: 16-bit stereo at this rate (IGameSound::SampleRate, 44,100 Hz). */
		static int SoundRate();
		/**
		 * How far a listener keeps the sound made ahead of what is heard, in frames: the time of the longest stall the game
		 * rides through without dropping time (FTickClock::MaxTicksPerAdvance vertical blanks), so a stall the game takes
		 * in its stride the sound does too, and a longer one both lose alike.
		 */
		static int SoundLeadFrames();
		/**
		 * From now on a listener takes the sound's samples through RenderSound, each heard LatencyFrames after it is made,
		 * and Step no longer passes the sound's time. Only the live game is heard: scripted and headless runs keep the sound
		 * unheard (it passes each frame's time), so they stay the same however fast they run. One-way; an error, or empty.
		 */
		std::string Hear(int LatencyFrames);
		bool Heard() const;
		/** The next Frames of the heard sound, left and right interleaved; false (nothing made) when it is not heard. */
		bool RenderSound(int16_t* Stereo, int Frames);
		/** For checks: the SPU's voices sounding now (envelope above 0), by the kind of their last note: music, effect, voice. */
		std::array<int, 3> SoundingVoices() const;
		FFrameInfo Info() const;
		/**
		 * For checks: everything of the frame shown now that the bridge leaves undrawn or draws by a stand-in, each class
		 * once with its count in this frame (0 where there is none), always in the same order (UnhandledNames).
		 */
		std::vector<FUnhandled> Unhandled() const;
		static std::vector<const char*> UnhandledNames();
		/**
		 * The field's screen wave (FFieldFrame::bScreenWave), empty where there is none: the scene drawn so far drawn again
		 * through a grid of 16-pixel cells, here the wide grid (WideWave: 56 columns by 14 rows, from 18 columns left of the
		 * screen's), each cell's 4 corners (top left, top right, bottom left, bottom right) as x, y where the wave puts it and
		 * x, y of the screen it shows, in pixels of the 320 x 224 screen.
		 */
		std::vector<float> ScreenWave() const;

		/**
		 * For a tool that plays the game itself (the story walk's explorer): its session and loop drawn from now on as if
		 * this session ran them, after each of its frames; Open must have been called (the disc, the pack). Not owned; the
		 * session's own game is gone. Null for both lets go of them.
		 */
		void Observe(Weltall::FGameSession* Session, Weltall::FGameLoop* Loop);

		/** VRAM as 1024 x 1024 16-bit units (the console's 512 rows, then the port's own). */
		const uint16_t* Vram() const;
		int VramRows() const;
		/**
		 * One of the frame's VRAMs (EVramSource), null where there is none (the 2D layer's own and the overlay's fall back
		 * to the scene's). The scene's holds the screen's pixels the field copied into it (FFieldFrame::ScreenInVram) once
		 * the display has given the picture (SetScreenPicture).
		 */
		const uint16_t* VramOf(int Source);
		/** Changes whenever VramOf(Source)'s units may have: which VRAM, its uploads, the screen's pixels written in. */
		uint64_t VramStamp(int Source) const;
		/**
		 * The display's picture of the screen it showed last (RGBA rows, the whole window, the 320 x 224 game screen in it as
		 * the 2D layer places it: scaled to the height, centred), for the field's picture Taken (FFieldCover::Taken).
		 */
		void SetScreenPicture(int Taken, const uint8_t* Rgba, int Width, int Height);
		/** The movie's picture on screen as RGBA rows (alpha 255); false when no movie shows one. */
		bool MovieImage(std::vector<uint8_t>& Rgba, int& Width, int& Height) const;

		/** The scenery and the characters (sprites, shadows, particles) in Godot's view space. */
		void BuildWorld(std::vector<FSurface>& Out);
		/** The 2D layer (message windows, menus, fades) in screen pixels of 320 x 224, as runs in drawing order. */
		void BuildScreen(std::vector<FSurface>& Out);
		/**
		 * The names (as the pack's files are named, "<upload>-<palette>") of uploads under sprite pieces and 2D primitives
		 * not wholly drawn from the pack that the pack has no picture of, gathered since the last call; sorted, and cleared.
		 */
		std::vector<std::string> TakeMissingNames();
		/**
		 * For coverage tools: one sprite piece (a quad of the core's sprite drawing) over Vram drawn as BuildWorld draws a
		 * field sprite's piece (PushViewQuad: the same lookup, cut and fallbacks, the same tallies), and what came of it.
		 * The frame's lookups and the VRAM's caches are forgotten first (Vram is the caller's); pictures found through a
		 * palette agreeing on an upload's colours are remembered as in a scene, until ForgetSamePalettes.
		 */
		FSpritePieceVerdict ClassifySpriteQuad(const Weltall::FVram& Vram, const Weltall::FSpriteQuad& Quad);
		/**
		 * For checks: the field's frame shown now, each sprite piece of Actor (its game shadow left out) judged as
		 * ClassifySpriteQuad judges it, over the field's VRAM: one JSON object a line, as sprite_coverage's draws (the cell
		 * in the sprite's own units, the original texels as RGBA hex, what is drawn where), with the names tried.
		 */
		std::string DebugActorPieces(int Actor);
		/**
		 * The original texels of the pack's pictures where they are known (tools/sprite_alias_index.py): an upload of a
		 * sprite piece or a 2D primitive whose own names the pack lacks takes the picture of the same drawing (same size,
		 * the colours of texels opaque in both equal, at most max(2, 5 %) of texels opaque in one only - the user's alias
		 * rule, xeno_sprites/tools/alias_dump_parts.py). Empty path: off. An error, or empty.
		 */
		std::string SetAliasIndex(const std::string& Path);
		/**
		 * The table of pictures found by content (data/sprite_alias_table.csv, tools/sprite_alias_table.py): what the index's
		 * rule found, without the index's texels - a line "kind,width,height,hash,palette,picture,added" a substitution. kind
		 * "upload": hash is the upload's CRC-32 as Beetle names it (the name the pack lacks is "<hash>-<palette>"); region-rect,
		 * region-piece, port-rect, port-piece: the CRC-32 of the region's texels through its CLUT (0 transparent, else 0x8000 |
		 * the colour, row by row), continuing from the palette's CRC-32. width x height in texels; picture the pack's file
		 * name; added the texels the game draws that the picture's original lacked ("u:v" separated by spaces, drawn from VRAM
		 * under it). '#' begins a comment; picture "?" is a line left to fill in. Asked before the index. Empty path: off.
		 * An error or the lines not understood (the rest is kept), or empty.
		 */
		std::string SetAliasTable(const std::string& Path);
		/** The table's lines kept (SetAliasTable). */
		int AliasTableRows() const;
		/**
		 * Each upload or region compared by content (once a session) written into Path as a line of the table, appended: the
		 * picture found (by the table or the index), or "?" where none was. Empty path: off. An error, or empty.
		 */
		std::string SetAliasRecord(const std::string& Path);
		/** Forgets the pictures found through palettes agreeing on an upload's colours (as a new map in a sweep, Restart). */
		void ForgetSamePalettes();
		/**
		 * With XENO_SPRITE_PALETTES set: every (upload, palette) under the sprite pieces the world was built with since the last
		 * call, one CSV line each, "upload,palette,clut_x,clut_y,depth,pieces,colours" (colours: the CLUT's 16 or 256 units in hex).
		 */
		std::string TakeSpritePalettes();
		/**
		 * With XENO_SPRITE_PALETTES set: the sprite pieces not wholly from the pack since the last call, one CSV line per class
		 * and name, "class,name,pieces" (class a: an upload under the piece the pack has under no palette; b: only under
		 * other palettes; c: every upload under it has its picture; d: no upload tracked under it, name "-"; beyond: the
		 * picture found holds fewer texels than the piece shows, name the picture's).
		 */
		std::string TakeSpriteMisses();
		/** World to view in Godot's axes and scale, rows of 3 then the translation (12 floats). */
		std::array<float, 12> ViewTransform() const;
		/** Checks for the smoke test: each placed model's origin by its own matrix against its world place through the view. */
		std::string DebugPlacements(int Count) const;
		/**
		 * In the arena: where the bridge places each scene polygon's corners (the camera on the arena's 218 lines, the frame's
		 * centre reached in proportion to depth) against where the GTE put them on the original's screen (ScreenX/ScreenY),
		 * corners in front of the eye: how many, the mean and largest distance in the original's pixels, by layer.
		 */
		std::string DebugArena() const;
		/** In battle: what the frame holds (its drawing order's links by kind, the objects' links, the HUD, the fade, VRAM's revision). */
		std::string DebugBattle() const;
		/** On the world map: its animated VRAM rectangles, and its textured polygons by layer and texture view (pictures, animation). */
		std::string DebugMap() const;
		/** On the field: each character view (actor, pass, shadow or not), its quads, how many of their texels are not transparent, the actor's flags. */
		std::string DebugCharacters() const;

		/** The cheat panel: the party, the money, the items held, what can be done now. */
		FCheatState CheatState() const;
		/** One of the inventory's lists (0 items, 1 weapons, 2 accessories, 3 gear weapons, 4 gear parts): every entry the disc names, or those held. */
		std::vector<FCheatItem> CheatItems(int List, bool bHeldOnly) const;
		/**
		 * A cheat, each through the game's own state and routines (the code says which): "money:N", "money+:N", "exp:<hero>:N",
		 * "exp:party:N", "level:<hero>:K", "fill:<hero>" / "fill:party", "deathblows:<hero>" / "deathblows:party", "gears",
		 * "item:<list>:<id>:<count>", "win",
		 * "encounters:0|1", "turbo:N". A hero is a name ("fei") or a character's number. Empty, or why it was not done.
		 */
		std::string Cheat(const std::string& Command);
		/**
		 * The turbo asked for (1 none): live play runs that many times the game's pace where Weltall's own fast-forward
		 * would (a battle fought, the field or the world map ticking), through VblanksDue and the session's pace.
		 */
		void SetTurbo(int Rate);
		/** The pace the game runs at now: the turbo where it applies, else 1. */
		int GamePace() const;
		/** How many programs have started (a new one: a battle, a map, the world map). */
		int ProgramRuns() const;

	private:
		struct FImpl;
		std::unique_ptr<FImpl> Impl;
	};

	/** View units to Godot units (a view unit is a third of a world unit). */
	inline constexpr float ViewScale = 1.0f / 1024.0f;
}
