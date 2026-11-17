// The Battling arena entered directly, headless, as Weltall's arena audit enters it (Tests/Tools/SortingAuditArenaRun.cpp):
// a new game on the forest map 15, the field running, then its requests asking for the arena with the six bytes of FE BF;
// the pad of a player who walks at the opponent and strikes. Per bout: the core's error (if it stopped), the frames in the
// arena by stage, the program at the end, the polygons by layer, the 2D layer, the pack's tallies (sums over the builds
// made every 30th frame and at the last), each side's HP at the start and the lowest it fell to, the bout's result.
// Usage: arena_sweep <Games folder> <pack folder|-> <out.csv> [frames=2400] [first gear=0] [last gear=48]
//        arena_sweep <Games folder> sites [first map=0] [last map=729]   (every FE BF of the maps' event scripts)
// XENO_TRANSLATION=<image>: the translation's disc (FSession::Open). XENO_ARENA_KINDS=<list>: the bouts per opponent, from
// c (against the computer), p (practice), t (the tutorial), s (the story's scripted bout), m (the arena's menus); default c.

#include "xeno_session.h"

#include <algorithm>
#include <array>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace
{
	/** The builds: every 30th frame and the last (XENO_BUILD_EVERY=<n>: every n-th instead, for the palette counts' finer steps). */
	const int BuildEvery = std::getenv("XENO_BUILD_EVERY") != nullptr && std::atoi(std::getenv("XENO_BUILD_EVERY")) > 0 ? std::atoi(std::getenv("XENO_BUILD_EVERY")) : 30;
	/** The forest map Weltall's arena audit asks from: its scripts ask for nothing as the arena is asked for. */
	constexpr int ForestMap = 15;
	constexpr int FeiGear = 0;
	constexpr int BattlingProgram = 4;
	constexpr int GearCount = 49;

	/** The pad of a player who walks at the opponent and strikes (SortingAuditArenaRun.cpp, Striking): right held, a button a few passes. */
	uint16_t Striking(int Pass)
	{
		constexpr std::array<uint16_t, 4> Buttons{0x8000, 0x1000, 0x4000, 0x8000};
		uint16_t Held = 0x0020;
		if (Pass % 6 < 3)
		{
			Held = static_cast<uint16_t>(Held | Buttons[static_cast<std::size_t>(Pass / 6 % 4)]);
		}
		return Held;
	}

	std::string Field(const std::string& Text)
	{
		std::string Out = "\"";
		for (const char Letter : Text)
		{
			Out += Letter == '"' ? std::string("\"\"") : Letter == '\n' || Letter == '\r' ? std::string(" ") : std::string(1, Letter);
		}
		return Out + "\"";
	}

	/** The six bytes of a bout of the kind named by Kind against Opponent. */
	std::array<int, 6> BoutParameters(char Kind, int Opponent)
	{
		switch (Kind)
		{
		case 'p': return {0, 1, FeiGear, Opponent, 1, 0};
		case 't': return {0, 2, FeiGear, Opponent, 1, 0};
		case 's': return {2, 0, FeiGear, Opponent, 1, 0};
		case 'm': return {1, 0, FeiGear, Opponent, 1, 0};
		default: return {0, 0, FeiGear, Opponent, 1, 0};
		}
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 3)
	{
		std::fprintf(stderr, "usage: arena_sweep <Games folder> <pack folder|-> <out.csv> [frames=2400] [first gear] [last gear] | <Games> sites [first] [last]\n");
		return 2;
	}
	Xeno::FSession Session;
	const char* Translation = std::getenv("XENO_TRANSLATION");
	const std::string Opened = Session.Open(Argv[1], Translation != nullptr ? Translation : "");
	if (!Opened.empty())
	{
		std::fprintf(stderr, "open: %s\n", Opened.c_str());
		return 1;
	}
	if (std::string(Argv[2]) == "sites")
	{
		std::printf("%s", Session.DebugBattlingSites(Argc > 3 ? std::atoi(Argv[3]) : 0, Argc > 4 ? std::atoi(Argv[4]) : 729).c_str());
		return 0;
	}
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: arena_sweep <Games folder> <pack folder|-> <out.csv> [frames] [first gear] [last gear]\n");
		return 2;
	}
	if (std::string(Argv[2]) != "-")
	{
		const std::string Pack = Session.SetPack(Argv[2]);
		std::printf("pack: '%s' %d pictures\n", Pack.c_str(), Session.PackPictures());
	}
	const int Frames = Argc > 4 ? std::atoi(Argv[4]) : 2400;
	const int FirstGear = Argc > 5 ? std::atoi(Argv[5]) : 0;
	const int LastGear = Argc > 6 ? std::atoi(Argv[6]) : GearCount - 1;
	const std::string Kinds = std::getenv("XENO_ARENA_KINDS") != nullptr ? std::getenv("XENO_ARENA_KINDS") : "c";
	std::ofstream Out(Argv[3]);
	Out << "bout,kind,opponent,enter_error,arena_at,stopped_at,error,program_end,frames_menus,frames_versus,frames_bout,frames_winner,frames_paused,"
		   "drawn_frames,polygons,terrain,sky,horizon,sprite,model,shadow,tree,cloud,particle,gear,effect,one_sided_dropped,screen_primitives,"
		   "scenery_hd,scenery_vram,effects_hd,screen_textured,screen_hd,hp0_start,hp0_low,hp1_start,hp1_low,rounds,result,left_arena_at,builds\n";
	int Failed = 0, Bouts = 0;
	for (int Opponent = FirstGear; Opponent <= LastGear; ++Opponent)
	{
		for (const char Kind : Kinds)
		{
			++Bouts;
			const std::string Name = std::string(1, Kind) + std::to_string(Opponent);
			Session.Restart();
			std::string Entered = Session.EnterField(ForestMap);
			std::string Error;
			int Frame = 0, ArenaAt = -1, StoppedAt = -1, LeftAt = -1;
			// The field running first (as the audit waits), then the arena asked for.
			for (; Entered.empty() && Frame < 120; ++Frame)
			{
				Error = Session.Step(0, 128, 128, false);
				if (!Error.empty() || (Session.Info().bField && Session.Info().bRunning))
				{
					break;
				}
			}
			if (Entered.empty() && Error.empty())
			{
				Entered = Session.AskBattling(BoutParameters(Kind, Opponent));
			}
			std::array<long long, 5> ByStage{};
			std::array<long long, 11> Layers{};
			long long Drawn = 0, Polygons = 0, Dropped = 0, ScreenPrimitives = 0, SceneryHd = 0, SceneryVram = 0, EffectsHd = 0, ScreenTextured = 0,
					  ScreenHd = 0;
			std::array<int, 2> HpStart{-1, -1}, HpLow{INT_MAX, INT_MAX};
			int Rounds = 0, Result = 0, Builds = 0, Program = -1;
			std::vector<Xeno::FSurface> World, Screen;
			for (int Pass = 0; Entered.empty() && Error.empty() && Frame < Frames; ++Frame)
			{
				const bool bInArena = ArenaAt >= 0;
				// In the arena the striking pad; before it none (the field's own frames to the program's change).
				Error = Session.Step(bInArena ? Striking(Pass++) : 0, 128, 128, false);
				if (!Error.empty())
				{
					StoppedAt = Frame + 1;
					break;
				}
				const Xeno::FFrameInfo Now = Session.Info();
				Program = Now.Program;
				if (Program == BattlingProgram && ArenaAt < 0)
				{
					ArenaAt = Frame + 1;
				}
				if (ArenaAt >= 0 && Program != BattlingProgram)
				{
					LeftAt = Frame + 1;
					break;
				}
				if (!Now.bBattling)
				{
					continue;
				}
				const int Stage = Now.ArenaColumns > 320 ? 3 : Now.ArenaBlurs > 0 ? 4 : std::clamp(Now.ArenaStage, 0, 2);
				++ByStage[static_cast<std::size_t>(Stage)];
				Drawn += Now.bSceneDrawn ? 1 : 0;
				for (std::size_t Side = 0; Side < 2; ++Side)
				{
					if (Now.ArenaStage == 2 && Now.ArenaMaxHp[Side] > 0)
					{
						HpStart[Side] = HpStart[Side] < 0 ? Now.ArenaHp[Side] : HpStart[Side];
						HpLow[Side] = std::min(HpLow[Side], Now.ArenaHp[Side]);
					}
				}
				Rounds = std::max(Rounds, Now.ArenaRound);
				Result = Now.ArenaResult;
				if ((Frame + 1) % BuildEvery == 0 || Frame + 1 == Frames)
				{
					Session.BuildWorld(World);
					Session.BuildScreen(Screen);
					const Xeno::FFrameInfo Built = Session.Info();
					++Builds;
					Polygons += Built.MapPolygons;
					for (std::size_t Layer = 0; Layer < Layers.size(); ++Layer)
					{
						Layers[Layer] += Built.MapLayers[Layer];
					}
					Dropped += Built.MapOneSidedDropped;
					ScreenPrimitives += Built.ScreenPrimitives;
					SceneryHd += Built.SceneryHd;
					SceneryVram += Built.SceneryVram;
					EffectsHd += Built.HdUpload + Built.HdRect;
					ScreenTextured += Built.ScreenTextured;
					ScreenHd += Built.ScreenHd;
				}
			}
			const bool bBad = !Entered.empty() || !Error.empty() || ArenaAt < 0;
			Failed += bBad ? 1 : 0;
			Out << Name << ',' << Kind << ',' << Opponent << ',' << Field(Entered) << ',' << ArenaAt << ',' << StoppedAt << ',' << Field(Error) << ',' << Program;
			for (const long long Count : ByStage)
			{
				Out << ',' << Count;
			}
			Out << ',' << Drawn << ',' << Polygons;
			for (const long long Count : Layers)
			{
				Out << ',' << Count;
			}
			Out << ',' << Dropped << ',' << ScreenPrimitives << ',' << SceneryHd << ',' << SceneryVram << ',' << EffectsHd << ',' << ScreenTextured << ',' << ScreenHd
				<< ',' << HpStart[0] << ',' << (HpLow[0] == INT_MAX ? -1 : HpLow[0]) << ',' << HpStart[1] << ',' << (HpLow[1] == INT_MAX ? -1 : HpLow[1]) << ','
				<< Rounds << ',' << Result << ',' << LeftAt << ',' << Builds << '\n';
			Out.flush();
			std::printf("%s: enter '%s', arena at %d, %s%s, program %d, frames menus/versus/bout/winner/paused %lld/%lld/%lld/%lld/%lld, polygons %lld, "
						"2D %lld, HP %d->%d / %d->%d, rounds %d, result %d, left at %d\n",
				Name.c_str(), Entered.c_str(), ArenaAt, Error.empty() ? "ran" : "stopped: ", Error.c_str(), Program, ByStage[0], ByStage[1], ByStage[2], ByStage[3],
				ByStage[4], Polygons, ScreenPrimitives, HpStart[0], HpLow[0] == INT_MAX ? -1 : HpLow[0], HpStart[1], HpLow[1] == INT_MAX ? -1 : HpLow[1], Rounds,
				Result, LeftAt);
		}
	}
	std::printf("bouts %d, failed %d\n", Bouts, Failed);
	return 0;
}
