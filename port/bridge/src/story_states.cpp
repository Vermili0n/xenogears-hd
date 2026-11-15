// Every save state of a folder (the story walk's, out\states\story) through the bridge headless, as the game window plays it.
// Usage: story_states <Games folder> <pack folder> <states folder> <out.csv> [frames=120]
// For each state, in file-name order: loaded (FSession::LoadState: the console powered on afresh), then the frames played with
// no buttons, the world and the 2D layer built after each. One CSV row a state: where it ended (program, map, story, the
// screen kinds seen), the core's error if one stopped it, the bridge's tallies summed over the builds, the misses by kind,
// and for each class of FSession::Unhandled the frames it was in and its summed count.
// XENO_TRANSLATION=<image>: the translation's disc (FSession::Open), as the window plays by default.
// XENO_SCRIPT=<frames>:<buttons hex>,...: the buttons held instead of none, the steps over again from the first when they run
// out (session_smoke's form), from each state's first frame: walking about a map with encounters reaches its battles.

#include "xeno_session.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
	std::string Quoted(const std::string& Text)
	{
		std::string Out = "\"";
		for (const char Character : Text)
		{
			Out += Character == '"' ? std::string("\"\"") : Character == '\n' || Character == '\r' ? std::string(" ") : std::string(1, Character);
		}
		return Out + "\"";
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 5)
	{
		std::fprintf(stderr, "usage: story_states <Games folder> <pack folder> <states folder> <out.csv> [frames=120]\n");
		return 1;
	}
	const int Frames = Argc > 5 ? std::max(1, std::atoi(Argv[5])) : 120;
	Xeno::FSession Session;
	const char* Translation = std::getenv("XENO_TRANSLATION");
	if (const std::string Error = Session.Open(Argv[1], Translation != nullptr ? Translation : ""); !Error.empty())
	{
		std::fprintf(stderr, "open: %s\n", Error.c_str());
		return 1;
	}
	if (const std::string Error = Session.SetPack(Argv[2]); !Error.empty() || Session.PackPictures() == 0)
	{
		std::fprintf(stderr, "pack: '%s', %d pictures\n", Error.c_str(), Session.PackPictures());
		return 1;
	}
	std::vector<std::filesystem::path> States;
	for (const auto& Entry : std::filesystem::directory_iterator(Argv[3]))
	{
		if (Entry.path().extension() == ".state")
		{
			States.push_back(Entry.path());
		}
	}
	std::sort(States.begin(), States.end());
	std::vector<uint16_t> Held;
	if (const char* Steps = std::getenv("XENO_SCRIPT"))
	{
		for (const char* At = Steps; *At != '\0';)
		{
			char* End = nullptr;
			const int Count = static_cast<int>(std::strtol(At, &End, 10));
			const uint16_t Buttons = static_cast<uint16_t>(*End == ':' ? std::strtol(End + 1, &End, 16) : 0);
			Held.insert(Held.end(), static_cast<std::size_t>(std::max(0, Count)), Buttons);
			if (*End != ',')
			{
				break;
			}
			At = End + 1;
		}
	}
	const std::vector<const char*> Names = Xeno::FSession::UnhandledNames();
	std::ofstream Csv(Argv[4], std::ios::trunc);
	Csv << "state,load_error,core_error,program,map,story,screens,leader_x,leader_y,leader_z,frames,sprite_pieces,sprite_hd,sprite_partial,sprite_vram,"
		   "sprite_no_upload,sprite_all_in_pack,scenery_hd,scenery_vram,scenery_hd_mixed,screen_textured,screen_hd,screen_no_upload,miss_no_upload,"
		   "miss_split,miss_name,missing_names";
	for (const char* Name : Names)
	{
		Csv << ',' << Name << "_frames," << Name;
	}
	Csv << '\n';
	std::vector<Xeno::FSurface> World, Screen;
	for (const std::filesystem::path& Path : States)
	{
		const std::string Loaded = Session.LoadState(Path.string());
		std::string CoreError;
		long long Pieces = 0, Hd = 0, Partial = 0, FromVram = 0, NoUpload = 0, AllInPack = 0, SceneryHd = 0, SceneryVram = 0, Mixed = 0;
		long long Textured = 0, ScreenHd = 0, ScreenNoUpload = 0;
		long long SpriteBeyond = 0, ScreenBeyond = 0, KindsPlain = 0, Glyphs = 0, KindsRim = 0, KindsRimTexels = 0, KindsRimScenery = 0;
		// The frames a battle showed in, and the rim's tallies in them.
		long long BattleFrames = 0, BattleRim = 0, BattleRimScenery = 0;
		std::vector<long long> With(Names.size(), 0), Sum(Names.size(), 0);
		std::string Screens;
		const Xeno::FFrameInfo Before = Session.Info();
		std::size_t Missing = 0;
		int Played = 0;
		for (; Loaded.empty() && Played < Frames; ++Played)
		{
			CoreError = Session.Step(Held.empty() ? 0 : Held[static_cast<std::size_t>(Played) % Held.size()], 128, 128, false);
			if (!CoreError.empty())
			{
				break;
			}
			Session.BuildWorld(World);
			Session.BuildScreen(Screen);
			Missing += Session.TakeMissingNames().size();
			const Xeno::FFrameInfo Info = Session.Info();
			Pieces += Info.SpritePieces;
			Hd += Info.SpriteHd;
			Partial += Info.SpritePartial;
			FromVram += Info.SpriteVram;
			NoUpload += Info.SpriteNoUpload;
			AllInPack += Info.SpriteAllInPack;
			SceneryHd += Info.SceneryHd;
			SceneryVram += Info.SceneryVram;
			Mixed += Info.SceneryHdMixed;
			Textured += Info.ScreenTextured;
			ScreenHd += Info.ScreenHd;
			ScreenNoUpload += Info.ScreenNoUpload;
			SpriteBeyond += Info.SpriteBeyond;
			ScreenBeyond += Info.ScreenBeyond;
			KindsPlain += Info.KindsPlainDrawn;
			Glyphs += Info.BattleGlyphs;
			KindsRim += Info.KindsRimDrawn;
			KindsRimTexels += Info.KindsRimTexels;
			KindsRimScenery += Info.KindsRimScenery;
			if (Info.Screen == Xeno::EScreenKind::Battle)
			{
				++BattleFrames;
				BattleRim += Info.KindsRimDrawn;
				BattleRimScenery += Info.KindsRimScenery;
			}
			const char Letter = static_cast<char>('0' + static_cast<int>(Info.Screen));
			if (Screens.find(Letter) == std::string::npos)
			{
				Screens += Letter;
			}
			const std::vector<Xeno::FUnhandled> Found = Session.Unhandled();
			for (std::size_t Index = 0; Index < Found.size(); ++Index)
			{
				With[Index] += Found[Index].Count > 0 ? 1 : 0;
				Sum[Index] += Found[Index].Count;
			}
		}
		const Xeno::FFrameInfo Info = Session.Info();
		Csv << Quoted(Path.filename().string()) << ',' << Quoted(Loaded) << ',' << Quoted(CoreError) << ',' << Info.Program << ',' << Info.Map << ','
			<< Info.Story << ',' << Screens << ',' << Info.LeaderPosition[0] << ',' << Info.LeaderPosition[1] << ',' << Info.LeaderPosition[2] << ','
			<< Played << ',' << Pieces << ',' << Hd << ',' << Partial << ',' << FromVram << ',' << NoUpload << ',' << AllInPack << ',' << SceneryHd << ','
			<< SceneryVram << ',' << Mixed << ',' << Textured << ',' << ScreenHd << ',' << ScreenNoUpload << ',' << Info.MissNoUpload - Before.MissNoUpload
			<< ',' << Info.MissSplit - Before.MissSplit << ',' << Info.MissName - Before.MissName << ',' << Missing;
		for (std::size_t Index = 0; Index < Names.size(); ++Index)
		{
			Csv << ',' << With[Index] << ',' << Sum[Index];
		}
		Csv << '\n';
		Csv.flush();
		std::printf("%s: %s%s program %d map %d story %d\n", Path.filename().string().c_str(), Loaded.empty() ? "" : ("load: " + Loaded + "; ").c_str(),
			CoreError.empty() ? "" : ("core: " + CoreError + "; ").c_str(), Info.Program, Info.Map, Info.Story);
		// The fixes of 13.11 (stdout only, the CSV keeps its columns).
		std::printf("  past their picture: sprites %lld, 2D %lld; semi-transparent from a picture with plain texels %lld; battle glyphs %lld; rim beside blending "
					"texels %lld (%lld texels; scenery %lld); battle frames %lld, rim in them %lld (scenery %lld)\n",
			SpriteBeyond, ScreenBeyond, KindsPlain, Glyphs, KindsRim, KindsRimTexels, KindsRimScenery, BattleFrames, BattleRim, BattleRimScenery);
		std::fflush(stdout);
	}
	return 0;
}
