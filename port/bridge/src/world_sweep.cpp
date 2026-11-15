// The world map entered directly, headless: each era of disc 1 at every arrival of its playable scene, and each cutscene
// scene, as Weltall's sorting audit enters them (Tests/Tools/SortingAudit.cpp: EraStarts, the playable scene 1; its world
// map run: the story at the era's first value, the place 400h at the arrival). Per entry: power on again, enter, run the
// frames with no buttons, build the world and the 2D layer after every 30th frame and after the last; one CSV row: the
// core's error (if it stopped), the program at the end, the polygons by layer, the pack's tallies (sums over the builds).
// Usage: world_sweep <Games folder> <pack folder|-> <out.csv> [frames=150]
// XENO_TRANSLATION=<image>: the translation's disc (FSession::Open).

#include "xeno_session.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace
{
	constexpr int BuildEvery = 30;
	/** The story values eras 1 to 8 begin at (SortingAudit.cpp, EraStarts); era 8 plays on disc 2, which is not here. */
	constexpr std::array<int, 7> EraStarts = {24, 54, 135, 149, 186, 198, 204};
	constexpr int PlayableScene = 1;
	/** The world map's cutscene scenes (FWorldMapRuntime: 8-18). */
	constexpr int FirstCutscene = 8, LastCutscene = 18;

	std::string Field(const std::string& Text)
	{
		std::string Out = "\"";
		for (const char Letter : Text)
		{
			Out += Letter == '"' ? std::string("\"\"") : Letter == '\n' || Letter == '\r' ? std::string(" ") : std::string(1, Letter);
		}
		return Out + "\"";
	}

	struct FEntry
	{
		std::string Place;
		int Story = 0, Scene = 0, Entrance = 0;
	};
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: world_sweep <Games folder> <pack folder|-> <out.csv> [frames=150]\n");
		return 2;
	}
	const int Frames = Argc > 4 ? std::atoi(Argv[4]) : 150;
	Xeno::FSession Session;
	const char* Translation = std::getenv("XENO_TRANSLATION");
	const std::string Opened = Session.Open(Argv[1], Translation != nullptr ? Translation : "");
	if (!Opened.empty())
	{
		std::fprintf(stderr, "open: %s\n", Opened.c_str());
		return 1;
	}
	if (std::string(Argv[2]) != "-")
	{
		const std::string Pack = Session.SetPack(Argv[2]);
		std::printf("pack: '%s' %d pictures\n", Pack.c_str(), Session.PackPictures());
	}
	// The eras' arrivals, read from each era's playable scene as it is entered.
	std::vector<FEntry> Entries;
	for (std::size_t Era = 0; Era < EraStarts.size(); ++Era)
	{
		Session.Restart();
		const std::string Entered = Session.EnterWorldMap(EraStarts[Era], PlayableScene, 0);
		const std::vector<int> Arrivals = Session.WorldMapArrivals();
		std::printf("era %zu story %d: '%s', %zu arrivals\n", Era + 1, EraStarts[Era], Entered.c_str(), Arrivals.size());
		for (const int Arrival : Arrivals)
		{
			Entries.push_back({"w" + std::to_string(Era + 1) + "." + std::to_string(Arrival), EraStarts[Era], PlayableScene, Arrival});
		}
		if (Arrivals.empty())
		{
			Entries.push_back({"w" + std::to_string(Era + 1) + ".-", EraStarts[Era], PlayableScene, 0});
		}
	}
	for (int Scene = FirstCutscene; Scene <= LastCutscene; ++Scene)
	{
		Entries.push_back({"c" + std::to_string(Scene), EraStarts[0], Scene, 0});
	}
	std::ofstream Out(Argv[3]);
	Out << "place,story,scene,entrance,enter_error,stopped_at,error,program_end,world_map_frames,polygons,terrain,sky,horizon,sprite,model,shadow,tree,cloud,"
		   "particle,gear,effect,one_sided_dropped,sprite_pieces,sprite_hd,scenery_hd,scenery_vram,animated,animated_hd,screen_textured,screen_hd,"
		   "x,y,z,builds\n";
	int Failed = 0;
	for (const FEntry& Entry : Entries)
	{
		Session.Restart();
		const std::string Entered = Session.EnterWorldMap(Entry.Story, Entry.Scene, Entry.Entrance);
		std::string Error;
		int StoppedAt = -1, MapFrames = 0, Builds = 0;
		std::array<long long, 11> Layers{};
		long long Polygons = 0, Dropped = 0, SpritePieces = 0, SpriteHd = 0, SceneryHd = 0, SceneryVram = 0, Animated = 0, AnimatedHd = 0;
		long long ScreenTextured = 0, ScreenHd = 0;
		std::vector<Xeno::FSurface> World, Screen;
		Xeno::FFrameInfo Last;
		for (int Frame = 0; Entered.empty() && Frame < Frames; ++Frame)
		{
			Error = Session.Step(0, 128, 128, false);
			if (!Error.empty())
			{
				StoppedAt = Frame + 1;
				break;
			}
			Last = Session.Info();
			MapFrames += Last.bWorldMap && Last.bSceneDrawn ? 1 : 0;
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
				SpritePieces += Built.SpritePieces;
				SpriteHd += Built.SpriteHd;
				SceneryHd += Built.SceneryHd;
				SceneryVram += Built.SceneryVram;
				Animated += Built.MapAnimatedPieces;
				AnimatedHd += Built.MapAnimatedHd;
				ScreenTextured += Built.ScreenTextured;
				ScreenHd += Built.ScreenHd;
			}
		}
		Failed += !Entered.empty() || !Error.empty() ? 1 : 0;
		Out << Entry.Place << ',' << Entry.Story << ',' << Entry.Scene << ',' << Entry.Entrance << ',' << Field(Entered) << ',' << StoppedAt << ','
			<< Field(Error) << ',' << Last.Program << ',' << MapFrames << ',' << Polygons;
		for (const long long Count : Layers)
		{
			Out << ',' << Count;
		}
		Out << ',' << Dropped << ',' << SpritePieces << ',' << SpriteHd << ',' << SceneryHd << ',' << SceneryVram << ',' << Animated << ',' << AnimatedHd << ','
			<< ScreenTextured << ',' << ScreenHd << ',' << Last.LeaderPosition[0] << ',' << Last.LeaderPosition[1] << ',' << Last.LeaderPosition[2] << ',' << Builds
			<< '\n';
		Out.flush();
		std::printf("%s: enter '%s', %s%s, program %d, map frames %d, polygons %lld\n", Entry.Place.c_str(), Entered.c_str(), Error.empty() ? "ran" : "stopped: ",
			Error.c_str(), Last.Program, MapFrames, Polygons);
	}
	std::printf("entries %zu, failed %d\n", Entries.size(), Failed);
	return 0;
}
