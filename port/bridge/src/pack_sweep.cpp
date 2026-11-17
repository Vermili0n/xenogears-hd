// Every field map of disc 1 with a new game's state, headless: how much of what it draws comes from the texture pack.
// Usage: pack_sweep <Games folder> <pack folder> <out.csv> [first=0] [last=FieldMapCount-1] [frames=90]
// Per map: power on again, enter it, run the frames with no buttons, build the world and the 2D layer after every 30th frame
// and after the last, add up the counts. One CSV row per map (appended, so a crashed run can go on from the next map) and
// <out.csv>.missing.txt: each upload name the pack lacks, the number of maps it was seen on and up to five of them.
// XENO_TRANSLATION=<image>: the maps of that translation's disc (FSession::Open).

#include "xeno_session.h"

#include "Field/FieldMap.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace
{
	/** The builds: every 30th frame and the last (XENO_BUILD_EVERY=<n>: every n-th instead, for the palette counts' finer steps). */
	const int BuildEvery = std::getenv("XENO_BUILD_EVERY") != nullptr && std::atoi(std::getenv("XENO_BUILD_EVERY")) > 0 ? std::atoi(std::getenv("XENO_BUILD_EVERY")) : 30;
	constexpr std::size_t MapsKept = 5;

	struct FSeen
	{
		int Maps = 0;
		std::vector<int> First;
	};

	struct FTotals
	{
		long long SceneryHd = 0, SceneryVram = 0, SceneryHdMixed = 0;
		long long SpritePieces = 0, SpriteHd = 0, SpritePartial = 0, SpriteVram = 0, NoUpload = 0, AllInPack = 0, SplitGaps = 0;
		long long ScreenTextured = 0, ScreenHd = 0;
		/** The fixes of 13.11 (stdout only, the CSV keeps its columns): pieces past their picture, semi pictures with plain texels. */
		long long SpriteBeyond = 0, ScreenBeyond = 0, KindsPlain = 0;
		/** Since 13.11 afternoon: semi pictures' rims over transparent texels beside blending ones (primitives, texels). */
		long long KindsRim = 0, KindsRimTexels = 0, KindsRimScenery = 0;
		int Builds = 0;

		void Add(const Xeno::FFrameInfo& Info)
		{
			SceneryHd += Info.SceneryHd;
			SceneryVram += Info.SceneryVram;
			SceneryHdMixed += Info.SceneryHdMixed;
			SpritePieces += Info.SpritePieces;
			SpriteHd += Info.SpriteHd;
			SpritePartial += Info.SpritePartial;
			SpriteVram += Info.SpriteVram;
			NoUpload += Info.SpriteNoUpload + Info.ScreenNoUpload;
			AllInPack += Info.SpriteAllInPack + Info.ScreenAllInPack;
			SplitGaps += Info.SpriteSplitGaps;
			ScreenTextured += Info.ScreenTextured;
			ScreenHd += Info.ScreenHd;
			SpriteBeyond += Info.SpriteBeyond;
			ScreenBeyond += Info.ScreenBeyond;
			KindsPlain += Info.KindsPlainDrawn;
			KindsRim += Info.KindsRimDrawn;
			KindsRimTexels += Info.KindsRimTexels;
			KindsRimScenery += Info.KindsRimScenery;
			++Builds;
		}
	};

	/** A CSV field: quoted, quotes doubled, line breaks flattened (the core's error texts are free text). */
	std::string Field(const std::string& Text)
	{
		std::string Out = "\"";
		for (const char Character : Text)
		{
			Out += Character == '"' ? std::string("\"\"") : Character == '\n' || Character == '\r' ? std::string(" ") : std::string(1, Character);
		}
		return Out + "\"";
	}

	/** What a resumed run found before: "name<TAB>maps seen<TAB>first maps, comma-separated". */
	void ReadMissing(const std::string& Path, std::map<std::string, FSeen>& Missing)
	{
		std::ifstream File(Path);
		std::string Line;
		while (std::getline(File, Line))
		{
			std::istringstream Columns(Line);
			std::string Name, Count, Maps;
			if (!std::getline(Columns, Name, '\t') || !std::getline(Columns, Count, '\t'))
			{
				continue;
			}
			std::getline(Columns, Maps, '\t');
			FSeen& Seen = Missing[Name];
			Seen.Maps += std::atoi(Count.c_str());
			std::istringstream Each(Maps);
			std::string Map;
			while (std::getline(Each, Map, ',') && Seen.First.size() < MapsKept)
			{
				Seen.First.push_back(std::atoi(Map.c_str()));
			}
		}
	}

	void WriteMissing(const std::string& Path, const std::map<std::string, FSeen>& Missing)
	{
		// Written beside and then moved over: a crash mid-write leaves the last whole file.
		const std::string Temporary = Path + ".tmp";
		{
			std::ofstream File(Temporary, std::ios::trunc);
			for (const auto& [Name, Seen] : Missing)
			{
				File << Name << '\t' << Seen.Maps << '\t';
				for (std::size_t Map = 0; Map < Seen.First.size(); ++Map)
				{
					File << (Map != 0 ? "," : "") << Seen.First[Map];
				}
				File << '\n';
			}
		}
		std::error_code Error;
		std::filesystem::rename(Temporary, Path, Error);
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: pack_sweep <Games folder> <pack folder> <out.csv> [first=0] [last=%d] [frames=90]\n", Weltall::FieldMapCount - 1);
		return 1;
	}
	const std::string OutPath = Argv[3];
	const int First = Argc > 4 ? std::atoi(Argv[4]) : 0;
	const int Last = Argc > 5 ? std::atoi(Argv[5]) : Weltall::FieldMapCount - 1;
	const int Frames = Argc > 6 ? std::atoi(Argv[6]) : 90;

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
	std::printf("pack: %d pictures; maps %d..%d, %d frames each\n", Session.PackPictures(), First, Last, Frames);

	const std::string MissingPath = OutPath + ".missing.txt";
	std::map<std::string, FSeen> Missing;
	ReadMissing(MissingPath, Missing);
	std::error_code SizeError;
	const bool bNew = !std::filesystem::exists(OutPath) || std::filesystem::file_size(OutPath, SizeError) == 0;
	std::FILE* Csv = std::fopen(OutPath.c_str(), "ab");
	if (Csv == nullptr)
	{
		std::fprintf(stderr, "cannot write %s\n", OutPath.c_str());
		return 1;
	}
	if (bNew)
	{
		std::fprintf(Csv, "map,entered,error,frames_run,final_map,final_program,scenery_hd,scenery_vram,sprite_pieces,sprite_hd,sprite_partial,"
			"sprite_vram,no_upload,screen_textured,screen_hd,missing_names,scenery_hd_mixed,all_in_pack,split_gaps,builds\n");
		std::fflush(Csv);
	}

	const char* SweepState = std::getenv("XENO_SWEEP_STATE");
	// XENO_SPRITE_PALETTES=1: per map, the (upload, palette) pairs under its sprite pieces and the pieces not wholly from the
	// pack by class and name (FSession::TakeSpritePalettes / TakeSpriteMisses), into <out>.palettes.csv and <out>.misses.csv.
	const bool bPalettes = std::getenv("XENO_SPRITE_PALETTES") != nullptr;
	std::FILE* Palettes = bPalettes ? std::fopen((OutPath + ".palettes.csv").c_str(), "ab") : nullptr;
	std::FILE* Misses = bPalettes ? std::fopen((OutPath + ".misses.csv").c_str(), "ab") : nullptr;
	const auto Started = std::chrono::steady_clock::now();
	std::vector<Xeno::FSurface> World, Screen;
	for (int Map = First; Map <= Last; ++Map)
	{
		// Marks the map for what the session logs on stderr (XENO_TALLY_LOG).
		std::fprintf(stderr, "== map %d\n", Map);
		FTotals Totals;
		std::string Error;
		bool bEntered = false;
		int Run = 0;
		if (!Session.HoldsFieldMap(Map))
		{
			Error = "not on this disc (a stand-in file)";
		}
		else if (SweepState != nullptr)
		{
			// XENO_SWEEP_STATE=<state>: each map entered from that point of the story (its flags, party), not a new game.
			Error = Session.LoadState(SweepState);
			if (Error.empty())
			{
				Error = Session.EnterFieldKeeping(Map);
			}
			bEntered = Error.empty();
		}
		else if (Error = Session.Restart(); Error.empty())
		{
			Error = Session.EnterField(Map);
			bEntered = Error.empty();
		}
		if (bEntered)
		{
			int Built = -1;
			const auto Build = [&] {
				Session.BuildWorld(World);
				Session.BuildScreen(Screen);
				Totals.Add(Session.Info());
				Built = Run;
			};
			for (int Frame = 0; Frame < Frames; ++Frame)
			{
				Error = Session.Step(0, 128, 128, false);
				if (!Error.empty())
				{
					break;
				}
				++Run;
				if (Run % BuildEvery == 0)
				{
					Build();
				}
			}
			// After the last frame run (when an error stopped the game, the last one it drew).
			if (Run > 0 && Built != Run)
			{
				Build();
			}
		}
		if (Palettes != nullptr && Misses != nullptr)
		{
			const auto Prefixed = [Map](std::FILE* Into, const std::string& Lines) {
				std::size_t From = 0;
				while (From < Lines.size())
				{
					const std::size_t To = std::min(Lines.find('\n', From), Lines.size());
					std::fprintf(Into, "%d,%s\n", Map, Lines.substr(From, To - From).c_str());
					From = To + 1;
				}
				std::fflush(Into);
			};
			Prefixed(Palettes, Session.TakeSpritePalettes());
			Prefixed(Misses, Session.TakeSpriteMisses());
		}
		const std::vector<std::string> Names = Session.TakeMissingNames();
		for (const std::string& Name : Names)
		{
			FSeen& Seen = Missing[Name];
			++Seen.Maps;
			if (Seen.First.size() < MapsKept)
			{
				Seen.First.push_back(Map);
			}
		}
		const Xeno::FFrameInfo Info = Session.Info();
		const bool bRan = bEntered && Run > 0;
		std::fprintf(Csv, "%d,%d,%s,%d,%d,%d,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%zu,%lld,%lld,%lld,%d\n", Map, bEntered ? 1 : 0, Field(Error).c_str(),
			Run, bRan ? Info.Map : -1, bEntered ? Info.Program : -1, Totals.SceneryHd, Totals.SceneryVram, Totals.SpritePieces, Totals.SpriteHd,
			Totals.SpritePartial, Totals.SpriteVram, Totals.NoUpload, Totals.ScreenTextured, Totals.ScreenHd, Names.size(), Totals.SceneryHdMixed,
			Totals.AllInPack, Totals.SplitGaps, Totals.Builds);
		std::fflush(Csv);
		if (!Names.empty())
		{
			WriteMissing(MissingPath, Missing);
		}
		const double Seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - Started).count();
		std::printf("map %d: entered %d, %d frames, sprites %lld (hd %lld), screen %lld (hd %lld), missing %zu%s%s [%.0f s]\n", Map, bEntered ? 1 : 0, Run,
			Totals.SpritePieces, Totals.SpriteHd, Totals.ScreenTextured, Totals.ScreenHd, Names.size(), Error.empty() ? "" : " - ", Error.c_str(), Seconds);
		std::printf("  map %d past their picture: sprites %lld, 2D %lld; semi-transparent from a picture with plain texels %lld; rim beside blending texels %lld "
					"(%lld texels; scenery %lld)\n",
			Map, Totals.SpriteBeyond, Totals.ScreenBeyond, Totals.KindsPlain, Totals.KindsRim, Totals.KindsRimTexels, Totals.KindsRimScenery);
		std::fflush(stdout);
	}
	std::fclose(Csv);
	WriteMissing(MissingPath, Missing);
	return 0;
}
