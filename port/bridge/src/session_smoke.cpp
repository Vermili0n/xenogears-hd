// The bridge's session without Godot: open, enter a map, run frames, build the meshes, print their sizes.
// Usage: session_smoke <Games folder> [map=1] [frames=60] [placements=20] [mash=0]; XENO_PACK=<folder> reads a texture pack
// map -1: the console powered on (the kernel's notice, the opening movie, the title) instead of entering a map.
// XENO_TRANSLATION=<image>: the game plays that translation's disc (the Russian); XENO_MESSAGES=1: a line whenever the
// field's open message windows change, with each one's map, number and codes as the core holds them.
// XENO_CHEATS=<frame>:<cheat>;...: the cheat panel's cheats (FSession::Cheat) before those frames, its state printed around each.

#include "xeno_session.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace
{
	/** The cheat panel's state in a line (FSession::CheatState). */
	std::string CheatLine(const Xeno::FSession& Session)
	{
		const Xeno::FCheatState State = Session.CheatState();
		char Line[512];
		std::snprintf(Line, sizeof(Line), "program %d edit %d battle %d win %d enemies %d gold %u encounters_off %d pace %d items %zu", State.Program,
			State.bCanEdit ? 1 : 0, State.bInBattle ? 1 : 0, State.bCanWin ? 1 : 0, State.EnemiesLeft, State.Gold, State.bEncountersOff ? 1 : 0,
			Session.GamePace(), State.Items.size());
		std::string Out = Line;
		for (const Xeno::FCheatHero& Hero : State.Party)
		{
			std::snprintf(Line, sizeof(Line), " | %d %s LV %d/%d exp %u/%u next %u/%u HP %d/%d EP %d/%d atk %d def %d agi %d eth %d edef %d hit %d eva %d gear %d %s %lld/%lld fuel %d/%d",
				Hero.Character, Hero.Name.c_str(), Hero.Level, Hero.EtherLevel, Hero.Exp, Hero.EtherExp, Hero.ExpToNext, Hero.EtherExpToNext, Hero.Hp, Hero.MaxHp,
				Hero.Ep, Hero.MaxEp, Hero.Attack, Hero.Defense, Hero.Agility, Hero.Ether, Hero.EtherDefense, Hero.Hit, Hero.Evade, Hero.Gear, Hero.GearName.c_str(),
				static_cast<long long>(Hero.GearHp), static_cast<long long>(Hero.GearMaxHp), Hero.Fuel, Hero.MaxFuel);
			Out += Line;
			// Its Deathblows: number, name, learned (+) or not (-), the level asked, the percent, the 7-AP tier closed (!).
			int Learned = 0;
			std::string List;
			for (const Xeno::FCheatDeathblow& Deathblow : Hero.Deathblows)
			{
				Learned += Deathblow.bLearned ? 1 : 0;
				std::snprintf(Line, sizeof(Line), " %d:%s%s:L%d:%d%%:%s%s", Deathblow.Number, Deathblow.bLearned ? "+" : "-", Deathblow.Name.c_str(), Deathblow.Level,
					Deathblow.Percent, Deathblow.Buttons.c_str(), Deathblow.bTierOpen ? "" : "!");
				List += Line;
			}
			std::snprintf(Line, sizeof(Line), " AP %d deathblows %d/%zu gear %04x [", Hero.ApPerTurn, Learned, Hero.Deathblows.size(), Hero.GearDeathblows);
			Out += Line + List + " ]";
		}
		return Out;
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 2)
	{
		std::fprintf(stderr, "usage: session_smoke <Games folder> [map] [frames]\n");
		return 1;
	}
	Xeno::FSession Session;
	const char* Translation = std::getenv("XENO_TRANSLATION");
	std::printf("open: '%s' language %s\n", Session.Open(Argv[1], Translation != nullptr ? Translation : "").c_str(), Session.Language().c_str());
	const bool bMessages = std::getenv("XENO_MESSAGES") != nullptr;
	std::vector<Xeno::FSession::FOpenMessage> LastMessages;
	if (const char* Pack = std::getenv("XENO_PACK"))
	{
		const std::string Error = Session.SetPack(Pack);
		std::printf("pack: '%s' %d pictures\n", Error.c_str(), Session.PackPictures());
	}
	if (const char* Pages = std::getenv("XENO_PAGES"))
	{
		std::printf("page pack: '%s'\n", Session.SetPagePack(Pages).c_str());
	}
	// XENO_SAVES=<folder>: the game's own saves (the File screen's) kept there.
	if (const char* Saves = std::getenv("XENO_SAVES"))
	{
		std::printf("saves: '%s'\n", Session.SetSaveFolder(Saves).c_str());
	}
	const int Map = Argc > 2 ? std::atoi(Argv[2]) : 1;
	// XENO_LOAD=<save state>: the game goes on from it instead (the map argument is then ignored).
	const char* Load = std::getenv("XENO_LOAD");
	// XENO_CARD=<memory card image>:<slot>: the game goes on from that save instead (as play.cmd card= slot=).
	const char* Card = std::getenv("XENO_CARD");
	std::string Listing;
	const std::string CardText = Card != nullptr ? Card : "";
	const std::size_t CardColon = CardText.rfind(':');
	std::printf("enter: '%s'\n", (Card != nullptr ? Session.LoadCard(CardText.substr(0, CardColon), std::atoi(CardText.c_str() + CardColon + 1), Listing)
		: Load != nullptr ? Session.LoadState(Load) : Map < 0 ? Session.PowerOn() : Session.EnterField(Map)).c_str());
	// XENO_ENTER_MAP=<map>: with XENO_LOAD, that map entered from the state's point of the story (FSession::EnterFieldKeeping).
	if (const char* EnterMap = std::getenv("XENO_ENTER_MAP"); EnterMap != nullptr && Load != nullptr)
	{
		std::printf("enter map %s: '%s'\n", EnterMap, Session.EnterFieldKeeping(std::atoi(EnterMap)).c_str());
	}
	const int Frames = Argc > 3 ? std::atoi(Argv[3]) : 60;
	const uint16_t Mash = static_cast<uint16_t>(Argc > 5 ? std::strtol(Argv[5], nullptr, 0) : 0);
	// XENO_MASH_FRAMES=<n>: the mash only for the first n frames, none after (as the window's ff=<n> then a script of none).
	const int MashFrames = std::getenv("XENO_MASH_FRAMES") != nullptr ? std::atoi(std::getenv("XENO_MASH_FRAMES")) : INT_MAX;
	// XENO_TRACE=<N>: every N frames (and whenever the program or the HUD changes) a line: frame, program, battle step, HUD.
	const int Trace = std::getenv("XENO_TRACE") != nullptr ? std::atoi(std::getenv("XENO_TRACE")) : 0;
	// XENO_WORLD_EVERY=<n>: the scene built every n frames too, as the display builds it after each frame.
	const int WorldEvery = std::getenv("XENO_WORLD_EVERY") != nullptr ? std::atoi(std::getenv("XENO_WORLD_EVERY")) : 0;
	std::vector<Xeno::FSurface> BuiltEvery;
	double BuildTotalMs = 0.0, BuildLongestMs = 0.0;
	int BuildCount = 0;
	int LastProgram = -2;
	uint32_t LastHud = 0;
	int LastScreen = -2, LastMenu = -2;
	std::vector<Xeno::FSurface> Traced;
	// XENO_SCRIPT=<frames>:<buttons hex>,...: the buttons held for so many frames each, before the mash takes over.
	std::vector<std::pair<int, uint16_t>> Script;
	if (const char* Steps = std::getenv("XENO_SCRIPT"))
	{
		for (const char* At = Steps; *At != '\0';)
		{
			char* End = nullptr;
			const int Count = static_cast<int>(std::strtol(At, &End, 10));
			const uint16_t Buttons = static_cast<uint16_t>(*End == ':' ? std::strtol(End + 1, &End, 16) : 0);
			Script.emplace_back(Count, Buttons);
			At = *End == ',' ? End + 1 : End;
			if (End == At && *At != '\0' && *At != ',')
			{
				break;
			}
		}
	}
	const char* Reload = std::getenv("XENO_RELOAD");
	const int ReloadFrame = Reload != nullptr ? std::atoi(Reload) : -1;
	const char* ReloadPath = Reload != nullptr && std::strchr(Reload, ':') != nullptr ? std::strchr(Reload, ':') + 1 : "";
	std::vector<std::pair<int, std::string>> Cheats;
	if (const char* Given = std::getenv("XENO_CHEATS"))
	{
		std::string Text = Given;
		for (std::size_t From = 0; From < Text.size();)
		{
			const std::size_t To = std::min(Text.find(';', From), Text.size());
			const std::string Entry = Text.substr(From, To - From);
			const std::size_t Colon = Entry.find(':');
			if (Colon != std::string::npos)
			{
				Cheats.emplace_back(std::atoi(Entry.c_str()), Entry.substr(Colon + 1));
			}
			From = To + 1;
		}
	}
	std::size_t ScriptStep = 0;
	int ScriptLeft = Script.empty() ? 0 : Script[0].first;
	for (int Frame = 0; Frame < Frames; ++Frame)
	{
		uint16_t Held = Frame % 2 == 0 && Frame < MashFrames ? Mash : 0;
		while (ScriptStep < Script.size() && ScriptLeft <= 0)
		{
			++ScriptStep;
			ScriptLeft = ScriptStep < Script.size() ? Script[ScriptStep].first : 0;
		}
		if (ScriptStep < Script.size())
		{
			Held = Script[ScriptStep].second;
			--ScriptLeft;
		}
		// XENO_CHEATS=<frame>:<cheat>;...: each cheat (FSession::Cheat) before that frame, the cheat panel's state printed
		// before and after it.
		for (const auto& [CheatFrame, Command] : Cheats)
		{
			if (CheatFrame == Frame)
			{
				std::printf("cheat state before frame %d: %s\n", Frame, CheatLine(Session).c_str());
				std::printf("cheat '%s' before frame %d: '%s'\n", Command.c_str(), Frame, Session.Cheat(Command).c_str());
				std::printf("cheat state after: %s\n", CheatLine(Session).c_str());
			}
		}
		// XENO_ARENA=<frame>:<b0>,<b1>,<b2>,<b3>,<b4>,<b5>: before that frame the running field asks for the Battling arena with
		// FE BF's six bytes (FSession::AskBattling), as Weltall's arena audit asks it from map 15.
		if (const char* Arena = std::getenv("XENO_ARENA"); Arena != nullptr && std::atoi(Arena) == Frame && std::strchr(Arena, ':') != nullptr)
		{
			std::array<int, 6> Bytes{};
			const char* At = std::strchr(Arena, ':') + 1;
			for (std::size_t Byte = 0; Byte < Bytes.size() && *At != '\0'; ++Byte)
			{
				char* End = nullptr;
				Bytes[Byte] = static_cast<int>(std::strtol(At, &End, 10));
				At = *End == ',' ? End + 1 : End;
			}
			std::printf("arena asked before frame %d: '%s'\n", Frame, Session.AskBattling(Bytes).c_str());
		}
		// XENO_MOVIE=<frame>:<movie>:<end frame>: before that frame the running field asks for that movie of the disc in the drive
		// (FSession::AskFieldMovie, as FE 60 asks one full screen).
		if (const char* Movie = std::getenv("XENO_MOVIE"); Movie != nullptr && std::atoi(Movie) == Frame && std::strchr(Movie, ':') != nullptr)
		{
			char* End = nullptr;
			const int Number = static_cast<int>(std::strtol(std::strchr(Movie, ':') + 1, &End, 10));
			const int EndFrame = *End == ':' ? std::atoi(End + 1) : 1;
			std::printf("movie %d asked before frame %d: '%s'\n", Number, Frame, Session.AskFieldMovie(Number, EndFrame).c_str());
		}
		// XENO_RELOAD=<frame>:<state>: that state loaded over the game running before that frame (as F9 loads one).
		if (Reload != nullptr && Frame == ReloadFrame)
		{
			std::printf("reload before frame %d: '%s'\n", Frame, Session.LoadState(ReloadPath).c_str());
		}
		const std::string Error = Session.Step(Held, 128, 128, false);
		if (!Error.empty())
		{
			std::printf("step %d: %s\n", Frame, Error.c_str());
			break;
		}
		if (bMessages)
		{
			std::vector<Xeno::FSession::FOpenMessage> Messages = Session.OpenMessages();
			const auto Same = [](const Xeno::FSession::FOpenMessage& A, const Xeno::FSession::FOpenMessage& B)
			{ return A.Map == B.Map && A.Index == B.Index && A.Lines == B.Lines && A.Codes == B.Codes; };
			if (!std::equal(Messages.begin(), Messages.end(), LastMessages.begin(), LastMessages.end(), Same))
			{
				for (const Xeno::FSession::FOpenMessage& Message : Messages)
				{
					std::printf("message frame %d: map %d index %d lines %d portrait %d codes ", Frame + 1, Message.Map, Message.Index, Message.Lines,
							Message.bPortrait ? 1 : 0);
					for (const uint8_t Code : Message.Codes)
					{
						std::printf("%02x", Code);
					}
					std::printf("\n");
				}
				LastMessages = std::move(Messages);
			}
		}
		if (WorldEvery > 0 && Frame % WorldEvery == 0)
		{
			const auto BuildStart = std::chrono::steady_clock::now();
			Session.BuildWorld(BuiltEvery);
			const double BuildMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - BuildStart).count();
			BuildTotalMs += BuildMs;
			BuildLongestMs = std::max(BuildLongestMs, BuildMs);
			++BuildCount;
			if (std::getenv("XENO_MAP_PAGES_EVERY") != nullptr)
			{
				std::printf("frame %d\n%s", Frame + 1, Session.DebugMap().c_str());
			}
		}
		if (Trace > 0)
		{
			const Xeno::FFrameInfo Now = Session.Info();
			if (Frame % Trace == 0 || Now.Program != LastProgram || Now.HudHash != LastHud || static_cast<int>(Now.Screen) != LastScreen
				|| Now.MenuMode != LastMenu)
			{
				// The 2D layer built now: its primitives and hash (a menu's cursor moved changes it).
				Session.BuildScreen(Traced);
				const Xeno::FFrameInfo Drawn = Session.Info();
				// The 2D layer's runs by blend mode (opaque, average, add, subtract, add a quarter).
				std::array<int, Xeno::BlendCount> ByBlend{};
				for (const Xeno::FSurface& Surface : Traced)
				{
					++ByBlend[static_cast<std::size_t>(Surface.Blend)];
				}
				// The last BuildWorld's sprite pieces (whole from the pack / partly / from VRAM) and the leader's sprite frame.
				std::printf("trace %d: sprites %d whole %d partly %d vram %d, leader frame %d, map %d story %d program %d\n", Frame + 1, Now.SpritePieces,
					Now.SpriteHd, Now.SpritePartial, Now.SpriteVram, Now.LeaderFrame, Now.Map, Now.Story, Now.Program);
				// XENO_CHARACTERS_EVERY=1: the field's character views at each trace line.
				if (std::getenv("XENO_CHARACTERS_EVERY") != nullptr && Now.bField)
				{
					std::printf("%s", Session.DebugCharacters().c_str());
				}
				std::printf("trace %d: stage %d program %d screen %d map %d battle step %d hud %d hash %08x leader %d %d %d; menu mode %d frame %u; movie picture %d "
							"frame %d %dx%d view %d; cover %d/%d taken %d in-vram %d card %d; 2D runs by blend %d/%d/%d/%d/%d; 2D %d primitives hash %08x, %zu runs\n",
					Frame + 1, Now.Stage, Now.Program, static_cast<int>(Now.Screen), Now.Map, Now.BattleStep, Now.HudPrimitives, Now.HudHash,
					Now.LeaderPosition[0], Now.LeaderPosition[1], Now.LeaderPosition[2], Now.MenuMode, Now.MenuNumber, Now.MoviePicture, Now.MovieFrame,
					Now.MovieWidth, Now.MovieHeight, Now.MovieView, Now.bCover, Now.bCoverScreen, Now.CoverTaken, Now.ScreenInVram, Now.CardLevel, ByBlend[0],
					ByBlend[1], ByBlend[2], ByBlend[3], ByBlend[4], Drawn.ScreenPrimitives, Drawn.ScreenHash, Traced.size());
				// The disc in the drive, the movie's disc, a disc the game waits on that the bridge has not found; the player's control.
				std::printf("  disc in drive %d (%s) movie %d %s #%d; wanted %d %s in %s; controlled %d\n", Now.DriveDisc, Now.DriveDiscId.c_str(), Now.MovieDisc,
					Now.MovieSource.c_str(), Now.MovieNumber, Now.DiscWanted, Now.DiscWantedKind.c_str(), Now.DiscWantedFolder.c_str(), Now.bPlayerControlled ? 1 : 0);
				if (Now.bWorldMap)
				{
					// The world map: its scene, travel, place stood on, camera yaw, fade, tick, whether the player may open the menu.
					std::printf("  world map scene %d travel %d place %d yaw %d fade %d tick %d controlled %d\n", Now.WorldScene, Now.TravelMode, Now.MapPlace,
						Now.CameraYaw, Now.FadeLevel, Now.Tick, Now.bPlayerControlled);
				}
				if (Now.bBattling)
				{
					// The arena: its stage, the fight's state, round, winner, result; each side's gear, HP and place; the frame.
					Session.BuildWorld(Traced);
					const Xeno::FFrameInfo Scene = Session.Info();
					std::printf("  arena stage %d state %d round %d winner %d result %d pass %d; gears %d/%d hp %d/%d %d/%d at (%d,%d,%d) (%d,%d,%d); columns %d blurs %d "
								"trails %d drawn %d polygons %d (terrain %d sky %d shadow %d gear %d effect %d) dropped %d clear %d,%d,%d H %.0f\n",
						Now.ArenaStage, Now.ArenaState, Now.ArenaRound, Now.ArenaWinner, Now.ArenaResult, Now.Tick, Now.ArenaGears[0], Now.ArenaGears[1], Now.ArenaHp[0],
						Now.ArenaMaxHp[0], Now.ArenaHp[1], Now.ArenaMaxHp[1], Now.ArenaPositions[0][0], Now.ArenaPositions[0][1], Now.ArenaPositions[0][2],
						Now.ArenaPositions[1][0], Now.ArenaPositions[1][1], Now.ArenaPositions[1][2], Now.ArenaColumns, Now.ArenaBlurs, Now.bArenaTrails,
						Now.bSceneDrawn, Scene.MapPolygons, Scene.MapLayers[0], Scene.MapLayers[1], Scene.MapLayers[5], Scene.MapLayers[9], Scene.MapLayers[10],
						Scene.MapOneSidedDropped, Now.Background[0], Now.Background[1], Now.Background[2], Now.ProjectionDistance);
				}
			}
			// XENO_UNHANDLED=1: what the frame holds that the bridge leaves undrawn (FSession::Unhandled), the classes found.
			if (std::getenv("XENO_UNHANDLED") != nullptr && (Frame % Trace == 0 || Now.Program != LastProgram))
			{
				Session.BuildWorld(Traced);
				Session.BuildScreen(Traced);
				std::printf("  unhandled %d:", Frame + 1);
				for (const Xeno::FUnhandled& Class : Session.Unhandled())
				{
					if (Class.Count != 0)
					{
						std::printf(" %s=%d", Class.Name, Class.Count);
					}
				}
				std::printf("\n");
			}
			LastProgram = Now.Program;
			LastHud = Now.HudHash;
			LastScreen = static_cast<int>(Now.Screen);
			LastMenu = Now.MenuMode;
		}
	}
	if (BuildCount > 0)
	{
		std::printf("scene builds %d: mean %.2f ms, longest %.2f ms\n", BuildCount, BuildTotalMs / BuildCount, BuildLongestMs);
	}
	const Xeno::FFrameInfo Info = Session.Info();
	std::printf("map %d running %d drawn %d leader %d at %d %d %d, H %.0f\n", Info.Map, Info.bRunning, Info.bSceneDrawn, Info.Leader,
		Info.LeaderPosition[0], Info.LeaderPosition[1], Info.LeaderPosition[2], Info.ProjectionDistance);
	std::vector<Xeno::FSurface> World;
	Session.BuildWorld(World);
	std::size_t Vertices = 0;
	for (const Xeno::FSurface& Surface : World)
	{
		Vertices += Surface.Mesh.Vertices();
	}
	const Xeno::FFrameInfo Built = Session.Info();
	std::printf("world: %zu surfaces, %zu vertices; textured primitives: pack by upload %d, by rect %d, cut along uploads %d, VRAM %d; scenery laid %d\n", World.size(),
		Vertices, Built.HdUpload, Built.HdRect, Built.HdSplit, Built.FromVram, Built.SceneryLaid);
	std::printf("regions without a picture: no upload %d, split %d, name not in pack %d; rect hits at U-1 %d, U %d, U+1 %d; page hits %d\n", Built.MissNoUpload,
		Built.MissSplit, Built.MissName, Built.RectHitsByShift[0], Built.RectHitsByShift[1], Built.RectHitsByShift[2], Built.PageHits);
	std::vector<Xeno::FSurface> Screen;
	Session.BuildScreen(Screen);
	std::printf("screen runs: %zu\n", Screen.size());
	for (std::size_t Run = 0; Run < Screen.size() && Run < 40; ++Run)
	{
		const Xeno::FSurface& Surface = Screen[Run];
		std::printf("  screen run blend %d, %zu vertices, %s (VRAM source %d)", static_cast<int>(Surface.Blend), Surface.Mesh.Vertices(),
			Surface.Texture.empty() ? "VRAM" : Surface.Texture.c_str(), Surface.Vram);
		// The run's first corner: place, colour, texel, page and flags (C0), CLUT (C1), drawing area (C3).
		if (Surface.Mesh.Vertices() > 0)
		{
			const Xeno::FMeshBuffers& M = Surface.Mesh;
			std::printf(" first corner at %.0f,%.0f colour %.0f,%.0f,%.0f uv %.1f,%.1f page %.0f,%.0f depth %.0f flags %.0f clut %.0f,%.0f area %.0f,%.0f,%.0f,%.0f",
				M.Pos[0], M.Pos[1], M.Color[0] * 255, M.Color[1] * 255, M.Color[2] * 255, M.Uv[0], M.Uv[1], M.C0[0], M.C0[1], M.C0[2], M.C0[3], M.C1[0], M.C1[1],
				M.C3[0], M.C3[1], M.C3[2], M.C3[3]);
		}
		std::printf("\n");
	}
	// XENO_VRAM_ROWS=<source>: after the 2D layer, the units set (non-zero) in each of that VRAM's first 40 rows, its first 256 columns.
	if (const char* Source = std::getenv("XENO_VRAM_ROWS"))
	{
		if (const uint16_t* Units = Session.VramOf(std::atoi(Source)))
		{
			for (int Row = 0; Row < 40; ++Row)
			{
				int Set = 0;
				uint16_t Sample = 0;
				for (int Column = 0; Column < 256; ++Column)
				{
					Set += Units[Row * 1024 + Column] != 0 ? 1 : 0;
					Sample = Units[Row * 1024 + Column] != 0 && Sample == 0 ? Units[Row * 1024 + Column] : Sample;
				}
				std::printf("vram %s row %d: %d set, first %04x\n", Source, Row, Set, Sample);
			}
		}
	}
	// XENO_VRAM_FILE=<path>: after the 2D layer, each VRAM source's units as they are (1024 x rows, 16-bit little-endian) into <path>.<source>.
	if (const char* VramFile = std::getenv("XENO_VRAM_FILE"))
	{
		for (int Source = 0; Source < Xeno::VramSourceCount; ++Source)
		{
			if (const uint16_t* Units = Session.VramOf(Source))
			{
				const std::string Path = std::string(VramFile) + "." + std::to_string(Source);
				if (std::FILE* Out = std::fopen(Path.c_str(), "wb"))
				{
					std::fwrite(Units, sizeof(uint16_t), static_cast<std::size_t>(1024 * Session.VramRows()), Out);
					std::fclose(Out);
				}
			}
		}
	}
	const Xeno::FFrameInfo AfterScreen = Session.Info();
	std::printf("after the 2D layer: pack by upload %d, by rect %d, VRAM %d; misses no upload %d, split %d, name %d\n", AfterScreen.HdUpload,
		AfterScreen.HdRect, AfterScreen.FromVram, AfterScreen.MissNoUpload, AfterScreen.MissSplit, AfterScreen.MissName);
	std::printf("vram %p rows %d\n", static_cast<const void*>(Session.Vram()), Session.VramRows());
	// The program, and in battle what its frame holds and what the pack drew of it (the world's tallies from BuildWorld,
	// the 2D layer's from BuildScreen).
	std::printf("program %d battle %d unlit %d screen %dx%d step %d; scene links %d, over the layers %d; hud %d primitives, hash %08x\n", AfterScreen.Program,
		AfterScreen.bBattle, AfterScreen.bUnlit, AfterScreen.ScreenWidth, AfterScreen.ScreenHeight, AfterScreen.BattleStep, AfterScreen.SceneLinks,
		AfterScreen.OverLinks, AfterScreen.HudPrimitives, AfterScreen.HudHash);
	std::size_t ScreenVertices = 0;
	for (const Xeno::FSurface& Surface : Screen)
	{
		ScreenVertices += Surface.Mesh.Vertices();
	}
	std::printf("surfaces: world %zu (%zu vertices), screen %zu (%zu vertices)\n", World.size(), Vertices, Screen.size(), ScreenVertices);
	// FNV-1a of everything the world's and the 2D layer's surfaces carry (two runs that draw alike hash alike).
	for (const std::vector<Xeno::FSurface>* Surfaces : {&World, &Screen})
	{
		uint32_t Hash = 2166136261u;
		const auto Mix = [&Hash](const std::vector<float>& Values) {
			for (const float Value : Values)
			{
				uint32_t Bits = 0;
				std::memcpy(&Bits, &Value, sizeof(Bits));
				for (int Byte = 0; Byte < 4; ++Byte)
				{
					Hash = (Hash ^ (Bits >> (Byte * 8) & 0xFF)) * 16777619u;
				}
			}
		};
		for (const Xeno::FSurface& Surface : *Surfaces)
		{
			Mix({static_cast<float>(Surface.Blend), static_cast<float>(Surface.Vram)});
			Mix(Surface.Mesh.Pos);
			Mix(Surface.Mesh.Color);
			Mix(Surface.Mesh.Uv);
			Mix(Surface.Mesh.C0);
			Mix(Surface.Mesh.C1);
			Mix(Surface.Mesh.C2);
			Mix(Surface.Mesh.C3);
		}
		std::printf("%s hash %08x\n", Surfaces == &World ? "world" : "screen", Hash);
	}
	for (int Source = 0; Source < Xeno::VramSourceCount; ++Source)
	{
		uint32_t Hash = 2166136261u;
		if (const uint16_t* Units = Session.VramOf(Source))
		{
			for (int Unit = 0; Unit < 1024 * Session.VramRows(); ++Unit)
			{
				Hash = (Hash ^ Units[Unit]) * 16777619u;
			}
		}
		std::printf("vram %d hash %08x stamp %llx\n", Source, Hash, static_cast<unsigned long long>(Session.VramStamp(Source)));
	}
	std::printf("tallies: sprite pieces %d (pack %d, partial %d, VRAM %d); scenery pack pages %d, VRAM %d (mixed %d); 2D textured %d, from pack %d\n",
		Built.SpritePieces, Built.SpriteHd, Built.SpritePartial, Built.SpriteVram, Built.SceneryHd, Built.SceneryVram, Built.SceneryHdMixed,
		AfterScreen.ScreenTextured, AfterScreen.ScreenHd);
	if (AfterScreen.bWorldMap)
	{
		std::printf("world map: scene %d travel %d place %d yaw %d tick %d; polygons %d (terrain %d sky %d horizon %d sprite %d model %d shadow %d tree %d cloud %d "
					"particle %d gear %d effect %d), one-sided triangles dropped %d\n",
			AfterScreen.WorldScene, AfterScreen.TravelMode, AfterScreen.MapPlace, AfterScreen.CameraYaw, AfterScreen.Tick, AfterScreen.MapPolygons,
			AfterScreen.MapLayers[0], AfterScreen.MapLayers[1], AfterScreen.MapLayers[2], AfterScreen.MapLayers[3], AfterScreen.MapLayers[4], AfterScreen.MapLayers[5],
			AfterScreen.MapLayers[6], AfterScreen.MapLayers[7], AfterScreen.MapLayers[8], AfterScreen.MapLayers[9], AfterScreen.MapLayers[10],
			AfterScreen.MapOneSidedDropped);
		std::printf("world map: animated scenery pieces %d, from the pack %d\n", AfterScreen.MapAnimatedPieces, AfterScreen.MapAnimatedHd);
	}
	if (AfterScreen.bWorldMap && std::getenv("XENO_MAP_PAGES") != nullptr)
	{
		std::printf("%s", Session.DebugMap().c_str());
	}
	std::printf("%s", Session.DebugBattle().c_str());
	if (AfterScreen.bBattling)
	{
		std::printf("%s", Session.DebugArena().c_str());
	}
	// XENO_CHARACTERS=1: the field's character views (for the shadows of actors the original does not show).
	if (std::getenv("XENO_CHARACTERS") != nullptr)
	{
		std::printf("%s", Session.DebugCharacters().c_str());
	}
	// XENO_ACTOR_PIECES=<actor>:<file>: that actor's sprite pieces in the last frame, as the pack lookup judges each (JSON lines).
	if (const char* Pieces = std::getenv("XENO_ACTOR_PIECES"))
	{
		const char* Colon = std::strchr(Pieces, ':');
		if (Colon != nullptr)
		{
			if (std::FILE* File = std::fopen(Colon + 1, "w"))
			{
				const std::string Lines = Session.DebugActorPieces(std::atoi(Pieces));
				std::fwrite(Lines.data(), 1, Lines.size(), File);
				std::fclose(File);
			}
		}
	}
	std::printf("%s", Session.DebugPlacements(Argc > 4 ? std::atoi(Argv[4]) : 20).c_str());
	// XENO_STATE=<file>: save the game here, load it into a fresh session, and say where the leader stands in both.
	if (const char* State = std::getenv("XENO_STATE"))
	{
		std::printf("save state: '%s'\n", Session.SaveState(State).c_str());
		Xeno::FSession Loaded;
		const std::string Opened = Loaded.Open(Argv[1], Translation != nullptr ? Translation : "");
		std::printf("open: '%s', load state: '%s'\n", Opened.c_str(), Loaded.LoadState(State).c_str());
		for (int Frame = 0; Frame < 60; ++Frame)
		{
			Loaded.Step(0, 128, 128, false);
		}
		const Xeno::FFrameInfo Again = Loaded.Info();
		std::printf("loaded: map %d leader at %d %d %d (saved at %d %d %d)\n", Again.Map, Again.LeaderPosition[0], Again.LeaderPosition[1],
			Again.LeaderPosition[2], Info.LeaderPosition[0], Info.LeaderPosition[1], Info.LeaderPosition[2]);
	}
	return 0;
}
