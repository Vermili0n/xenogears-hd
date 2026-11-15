// The story walked by algorithm, seen through the bridge: Weltall's own test explorer (Tests/Support/StorySweepExplore.h,
// the same as WeltallStorySweep -explore=N, built here from the weltall sources) plays a new game on with its floor
// path-finding, talks and zones; the bridge looks on at every frame it plays (FStorySweepOptions::Watch, FSession::Observe).
//
// Usage: story_walk <Games folder> <pack folder|-> <out folder> [places=400] [minutes=20] [build_every=10]
//
// Writes into <out folder>:
// - explore.txt: the explorer's line for each stretch (the place it began at, what began it, how it ended, its path), as
//   WeltallStorySweep prints them (fewer columns);
// - live.csv: one row a segment of play, a segment being frames with the same program, field map (world map: 1000 + its
//   scene) and story progress, in the order played: its frames, the bridge's tallies summed over the builds of the world and
//   the 2D layer (one every build_every frames and at each segment's first), and for each class of FSession::Unhandled the
//   frames it was in and its summed count (build-based classes: over the builds);
// - states\raw\: a save state (FSaveState, the bridge's F5 format) at the first quiet moment of every new
//   (program, map, story), again every 60 s of play in one up to twice more, and the last quiet moment before each battle;
//   at the end they are copied in story order to <states folder> = <out folder>\..\..\states\story\NNN_story<k>_map<m>_<why>.state.
// The walk stops after `places` places or `minutes` of machine time, whichever comes first (then it writes what it has).
// The discs are USA disc 1 of the Games folder (the explorer plays the discs it identifies itself).

#include "xeno_session.h"

#include "Game/GameLoop.h"
#include "Game/GameSession.h"
#include "Game/PlayerSettings.h"
#include "Game/SaveState.h"
#include "Media/GameLibrary.h"
#include "Mods/ExpansionMods.h"
#include "Story/StoryPacks.h"
#include "Support/PlayedGame.h"
#include "Support/StorySweepExplore.h"
#include "Support/StorySweepRun.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

using namespace Weltall;
using namespace Weltall::Testing;

namespace
{
	/** As WeltallStorySweep explores (Tools/StorySweep.cpp): three hours a stretch, a battle fought for 24000 frames. */
	constexpr int32 ExploredStretchFrames = 360000;
	constexpr int32 ExploredBattleFrames = 24000;
	/** A new state of the same segment key after this many frames of play in it, at most this many more. */
	constexpr int PeriodFrames = 1800;
	constexpr int PeriodStatesMost = 2;
	/** The rolling quiet state kept for "before a battle", tried every so many frames. */
	constexpr int RollingEvery = 30;
	/** The classes counted over builds (the bridge's tallies of the last BuildWorld / BuildScreen), not over frames. */
	const std::set<std::string> BuiltClasses{"battle_scene_blended", "world_soft_blend", "sprites_from_vram", "screen_2d_from_vram", "scenery_from_vram",
		"waiting_textures"};

	using FKey = std::tuple<int, int, int>; // program, map, story

	struct FSegment
	{
		int Number = 0;
		FKey Key{-1, -1, -1};
		long long FirstFrame = 0;
		int Frames = 0;
		int Builds = 0;
		long long SpritePieces = 0, SpriteHd = 0, SpritePartial = 0, SpriteVram = 0, SceneryHd = 0, SceneryVram = 0, SceneryHdMixed = 0;
		long long ScreenTextured = 0, ScreenHd = 0;
		std::vector<long long> With, Sum;
		std::string Screens; // the screen kinds seen, as letters in the order first seen
	};

	struct FKeptState
	{
		int Sequence = 0;
		int Story = 0, Map = 0, Program = 0;
		std::string Why;
		std::string Raw;
	};

	class FWalk
	{
	public:
		FWalk(Xeno::FSession& InBridge, const std::filesystem::path& InOut, const std::filesystem::path& InStates, int InBuildEvery)
			: Bridge(InBridge), Out(InOut), States(InStates), BuildEvery(InBuildEvery), Names(Xeno::FSession::UnhandledNames())
		{
			std::filesystem::create_directories(Out / "states" / "raw");
			Live.open(Out / "live.csv", std::ios::trunc);
			Live << "segment,story,map,program,first_frame,frames,screens,builds,sprite_pieces,sprite_hd,sprite_partial,sprite_vram,"
					"scenery_hd,scenery_vram,scenery_hd_mixed,screen_textured,screen_hd";
			for (const char* Name : Names)
			{
				Live << ',' << Name << "_frames," << Name;
			}
			Live << '\n';
			Started = std::chrono::steady_clock::now();
		}

		void Watch(FGameSession& Session, FGameLoop* Loop)
		{
			if (Loop == nullptr)
			{
				// A session powered on anew (the explorer begins from a state again): let go of the last, and give this one the
				// bridge's drawing settings (Xeno::FSession's PowerOn): sprites' mirrored pieces as the original lays them, gears
				// as sprites. Drawing alone: what the game does is the explorer's.
				Bridge.Observe(nullptr, nullptr);
				FPlayerSettings Settings = Session.Settings();
				Settings.Fixes.Field.bSpriteFramesAligned = false;
				Settings.Field.GearModels = EFieldGearModels::Off;
				Session.SetSettings(Settings);
				Rolling.reset();
				return;
			}
			Bridge.Observe(&Session, Loop);
			++Played;
			const Xeno::FFrameInfo Info = Bridge.Info();
			const int Map = Info.bField ? Info.Map : Info.bWorldMap ? 1000 + Info.WorldScene : -1;
			const FKey Key{Info.Program, Map, Info.Story};
			const bool bNewSegment = Key != Segment.Key;
			if (bNewSegment)
			{
				// Before a battle: the last quiet moment of what led to it.
				if (Info.Program == static_cast<int>(EGameProgram::Battle) && Rolling && Played - RollingFrame < 600)
				{
					Keep(*Rolling, std::get<2>(Segment.Key), std::get<1>(Segment.Key), std::get<0>(Segment.Key), "prebattle");
				}
				Rolling.reset();
				Flush();
				Segment = {};
				Segment.Number = ++Segments;
				Segment.Key = Key;
				Segment.FirstFrame = Played;
				Segment.With.assign(Names.size(), 0);
				Segment.Sum.assign(Names.size(), 0);
				bPending = Kept.count(Key) == 0;
				PendingWhy = "new";
			}
			++Segment.Frames;
			const char Letter = static_cast<char>('0' + static_cast<int>(Info.Screen));
			if (Segment.Screens.find(Letter) == std::string::npos)
			{
				Segment.Screens += Letter;
			}
			const bool bBuild = bNewSegment || (Played % BuildEvery) == 0;
			if (bBuild)
			{
				Bridge.BuildWorld(World);
				Bridge.BuildScreen(Screen);
				(void)Bridge.TakeMissingNames();
				if (bLogMisses)
				{
					// The pieces not wholly from the pack in this build, by segment key, class and name (summed over builds).
					std::stringstream Lines(Bridge.TakeSpriteMisses());
					for (std::string Line; std::getline(Lines, Line);)
					{
						const std::size_t Last = Line.rfind(',');
						Misses[{std::get<2>(Key), std::get<1>(Key), std::get<0>(Key), Line.substr(0, Last)}] += std::atoll(Line.c_str() + Last + 1);
					}
				}
				const Xeno::FFrameInfo Built = Bridge.Info();
				++Segment.Builds;
				Segment.SpritePieces += Built.SpritePieces;
				Segment.SpriteHd += Built.SpriteHd;
				Segment.SpritePartial += Built.SpritePartial;
				Segment.SpriteVram += Built.SpriteVram;
				Segment.SceneryHd += Built.SceneryHd;
				Segment.SceneryVram += Built.SceneryVram;
				Segment.SceneryHdMixed += Built.SceneryHdMixed;
				Segment.ScreenTextured += Built.ScreenTextured;
				Segment.ScreenHd += Built.ScreenHd;
			}
			const std::vector<Xeno::FUnhandled> Found = Bridge.Unhandled();
			for (std::size_t Index = 0; Index < Found.size(); ++Index)
			{
				if (BuiltClasses.count(Found[Index].Name) != 0 && !bBuild)
				{
					continue;
				}
				Segment.With[Index] += Found[Index].Count > 0 ? 1 : 0;
				Segment.Sum[Index] += Found[Index].Count;
			}
			// States: at the first quiet moment of a new key, then every PeriodFrames of play in it; a rolling one for battles.
			const int Since = static_cast<int>(Played - LastKeptFrame[Key]);
			const bool bPeriodic = !bPending && Kept.count(Key) != 0 && Since >= PeriodFrames && Periodic[Key] < PeriodStatesMost;
			const bool bRoll = (Played % RollingEvery) == 0;
			if (bPending || bPeriodic || bRoll)
			{
				auto Captured = CaptureSaveState(*Loop, Session);
				if (Captured && *Captured)
				{
					if (bPending || bPeriodic)
					{
						if (bPeriodic)
						{
							++Periodic[Key];
						}
						Keep(**Captured, Info.Story, Map, Info.Program, bPending ? PendingWhy : "later");
						bPending = false;
					}
					Rolling = std::move(**Captured);
					RollingFrame = Played;
				}
			}
		}

		void Report(int32 Map, uint16 Story, const std::string& Start, const FStorySweepRun& Run, const FStorySweepStretch& Stretch)
		{
			if (!Explore.is_open())
			{
				Explore.open(Out / "explore.txt", std::ios::trunc);
			}
			Explore << Map << '\t' << Story << '\t' << Start << '\t' << Run.SaveStory() << '\t' << Run.Party() << '\t' << StorySweepEndName(Stretch.End)
					<< '\t' << Stretch.Map << '\t' << Stretch.Story << '\t' << Stretch.Frames << '\t' << Stretch.Path << '\t' << Stretch.Detail << '\t'
					<< Stretch.Changed << '\t' << Played << '\n';
			Explore.flush();
			++Stretches;
			if (Stretch.End == EStorySweepEnd::Stops)
			{
				++Errors;
			}
		}

		double Minutes() const { return std::chrono::duration<double>(std::chrono::steady_clock::now() - Started).count() / 60.0; }

		/** The last segment written, the states copied in story order, a summary printed. */
		void Finish(const char* Why)
		{
			Flush();
			std::filesystem::create_directories(States);
			std::vector<FKeptState> Sorted = KeptStates;
			std::stable_sort(Sorted.begin(), Sorted.end(), [](const FKeptState& A, const FKeptState& B)
				{ return A.Story != B.Story ? A.Story < B.Story : A.Sequence < B.Sequence; });
			for (std::size_t Index = 0; Index < Sorted.size(); ++Index)
			{
				const FKeptState& State = Sorted[Index];
				char Name[160];
				std::snprintf(Name, sizeof(Name), "%03d_story%d_map%d_p%d_%s.state", static_cast<int>(Index), State.Story, State.Map, State.Program,
					State.Why.c_str());
				std::error_code Error;
				std::filesystem::copy_file(State.Raw, States / Name, std::filesystem::copy_options::overwrite_existing, Error);
			}
			// XENO_SPRITE_PALETTES=1: every (upload, palette) the sprite pieces were drawn with on the walk, and the CLUT's colours.
			if (std::getenv("XENO_SPRITE_PALETTES") != nullptr)
			{
				std::ofstream Palettes(Out / "sprite_palettes.csv", std::ios::trunc);
				Palettes << "upload,palette,clut_x,clut_y,depth,pieces,colours\n" << Bridge.TakeSpritePalettes();
				std::ofstream Missed(Out / "sprite_misses.csv", std::ios::trunc);
				Missed << "story,map,program,class,name,pieces\n";
				for (const auto& [Where, Count] : Misses)
				{
					Missed << std::get<0>(Where) << ',' << std::get<1>(Where) << ',' << std::get<2>(Where) << ',' << std::get<3>(Where) << ',' << Count << '\n';
				}
			}
			std::printf("story walk ended (%s): %.1f min, %lld frames, %d stretches, %d stopped with an error, %d segments, %zu states\n", Why, Minutes(),
				Played, Stretches, Errors, Segments, KeptStates.size());
			std::fflush(stdout);
			Live.flush();
			Explore.flush();
		}

	private:
		void Keep(const FSaveState& State, int Story, int Map, int Program, const std::string& Why)
		{
			const FKey Key{Program, Map, Story};
			Kept.insert(Key);
			LastKeptFrame[Key] = Played;
			FKeptState Entry;
			Entry.Sequence = static_cast<int>(KeptStates.size());
			Entry.Story = Story;
			Entry.Map = Map;
			Entry.Program = Program;
			Entry.Why = Why;
			char Name[96];
			std::snprintf(Name, sizeof(Name), "%04d.state", Entry.Sequence);
			Entry.Raw = (Out / "states" / "raw" / Name).string();
			const std::vector<uint8> Bytes = WriteSaveState(State);
			std::ofstream File(Entry.Raw, std::ios::binary | std::ios::trunc);
			File.write(reinterpret_cast<const char*>(Bytes.data()), static_cast<std::streamsize>(Bytes.size()));
			KeptStates.push_back(Entry);
		}

		void Flush()
		{
			if (Segment.Number == 0)
			{
				return;
			}
			Live << Segment.Number << ',' << std::get<2>(Segment.Key) << ',' << std::get<1>(Segment.Key) << ',' << std::get<0>(Segment.Key) << ','
				 << Segment.FirstFrame << ',' << Segment.Frames << ',' << Segment.Screens << ',' << Segment.Builds << ',' << Segment.SpritePieces << ','
				 << Segment.SpriteHd << ',' << Segment.SpritePartial << ',' << Segment.SpriteVram << ',' << Segment.SceneryHd << ',' << Segment.SceneryVram
				 << ',' << Segment.SceneryHdMixed << ',' << Segment.ScreenTextured << ',' << Segment.ScreenHd;
			for (std::size_t Index = 0; Index < Names.size(); ++Index)
			{
				Live << ',' << Segment.With[Index] << ',' << Segment.Sum[Index];
			}
			Live << '\n';
			Live.flush();
			Segment.Number = 0;
		}

		Xeno::FSession& Bridge;
		std::filesystem::path Out;
		std::filesystem::path States;
		int BuildEvery = 10;
		std::vector<const char*> Names;
		std::ofstream Live, Explore;
		std::chrono::steady_clock::time_point Started;
		long long Played = 0;
		int Segments = 0, Stretches = 0, Errors = 0;
		FSegment Segment;
		std::vector<Xeno::FSurface> World, Screen;
		std::set<FKey> Kept;
		std::map<FKey, long long> LastKeptFrame;
		std::map<FKey, int> Periodic;
		bool bPending = false;
		std::string PendingWhy;
		std::optional<FSaveState> Rolling;
		long long RollingFrame = 0;
		std::vector<FKeptState> KeptStates;
		/** XENO_SPRITE_PALETTES=1: sprite pieces not wholly from the pack, by (story, map, program, "class,name"). */
		const bool bLogMisses = std::getenv("XENO_SPRITE_PALETTES") != nullptr;
		std::map<std::tuple<int, int, int, std::string>, long long> Misses;
	};
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: story_walk <Games folder> <pack folder|-> <out folder> [places=400] [minutes=20] [build_every=10]\n");
		return 1;
	}
	const std::filesystem::path Games = Argv[1];
	const std::string Pack = Argv[2];
	const std::filesystem::path Out = Argv[3];
	const int Places = Argc > 4 ? std::atoi(Argv[4]) : 400;
	const double Minutes = Argc > 5 ? std::atof(Argv[5]) : 20.0;
	const int BuildEvery = Argc > 6 ? std::max(1, std::atoi(Argv[6])) : 10;
	// The states for play go beside the player's: out\states\story (the tool is run with <out folder> = out\sweep_story).
	const std::filesystem::path States = std::filesystem::absolute(Out).parent_path().parent_path() / "out" / "states" / "story";

	Xeno::FSession Bridge;
	if (const std::string Error = Bridge.Open(Games.string()); !Error.empty())
	{
		std::fprintf(stderr, "open: %s\n", Error.c_str());
		return 1;
	}
	if (Pack != "-")
	{
		if (const std::string Error = Bridge.SetPack(Pack); !Error.empty())
		{
			std::fprintf(stderr, "pack: %s\n", Error.c_str());
			return 1;
		}
	}

	const FGameLibrary Library = FGameLibrary::Scan(Games);
	auto Opened = FPlayedGame::Open(Library);
	if (!Opened)
	{
		std::fprintf(stderr, "discs: %s\n", Opened.Error().Message.c_str());
		return 1;
	}
	const FPlayedGame& Game = *Opened;
	// The port's story documents and its example scenes, as WeltallStorySweep reads them (its WELTALL_STORY_DIR, WELTALL_EXAMPLES_DIR).
	const std::filesystem::path Content = Games.parent_path() / "Content";
	auto Story = FStoryPacks::Read(Content / "Story");
	if (!Story)
	{
		std::fprintf(stderr, "story: %s\n", Story.Error().Message.c_str());
		return 1;
	}
	if (std::optional<FError> Error = Story->ReadExpansion(Content / "Examples" / "disc2", ExamplesFolder))
	{
		std::fprintf(stderr, "examples: %s\n", Error->Message.c_str());
		return 1;
	}

	FWalk Walk(Bridge, Out, States, BuildEvery);
	FStorySweepOptions Options;
	Options.bForcesTriggers = false;
	Options.StretchFrames = ExploredStretchFrames;
	Options.BattleFrames = ExploredBattleFrames;
	const std::vector<FOriginalSave> Saves;
	Options.Watch = [&](FGameSession& Session, FGameLoop* Loop)
	{
		Walk.Watch(Session, Loop);
		if (Loop != nullptr && Walk.Minutes() >= Minutes)
		{
			Walk.Finish("time");
			std::fflush(nullptr);
			std::_Exit(0);
		}
	};
	FStorySweepRun Run(Game, Saves, &*Story, Options);
	FStorySweepExplorer Explorer(Run, Options, [&](int32 Map, uint16 Value, const std::string& Start, const FStorySweepRun& Played, const FStorySweepStretch& Stretch)
		{
			Walk.Report(Map, Value, Start, Played, Stretch);
		});
	for (const FGameState& Root : StorySweepRoots(Game, Saves))
	{
		Explorer.Explore(Root, Places);
	}
	Walk.Finish("places");
	std::fflush(nullptr);
	// The bridge must let go of the run's game before either goes.
	Bridge.Observe(nullptr, nullptr);
	return 0;
}
