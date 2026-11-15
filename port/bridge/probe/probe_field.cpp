// Console probe for stage 0: WeltallCore without Unreal or Godot.
// Opens USA disc 1 from a Games folder, enters a field map as a new game, runs N frames with no buttons
// and writes one JSON line per frame: program, map, camera, party leader, every actor's position and
// the characters the frame draws.
//
// Usage: probe_field <Games folder> <out.jsonl> [map=1] [frames=600] [mash=0: FPadState bits pressed every other frame]

#include "Game/FieldProgram.h"
#include "Game/GameLoop.h"
#include "Game/GameSession.h"
#include "Media/DiscIdentification.h"
#include "Media/GameFileIndex.h"
#include "Media/GameLibrary.h"
#include "Media/PsxExecutable.h"
#include "Sound/GameSoundSession.h"
#include "Sound/UnheardGameSound.h"
#include "Support/NewGameParty.h"
#include "Timing/PsxTiming.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

using namespace Weltall;

static int Fail(const std::string& Message)
{
	std::fprintf(stderr, "probe: %s\n", Message.c_str());
	return 1;
}

static std::string Xyz(const std::array<int32, 3>& V)
{
	return "[" + std::to_string(V[0]) + "," + std::to_string(V[1]) + "," + std::to_string(V[2]) + "]";
}

int main(int Argc, char** Argv)
{
	if (Argc < 3)
	{
		return Fail("usage: probe_field <Games folder> <out.jsonl> [map=1] [frames=600] [mash=0]");
	}
	const uint16 Map = static_cast<uint16>(Argc > 3 ? std::atoi(Argv[3]) : 1);
	const int32 Frames = Argc > 4 ? std::atoi(Argv[4]) : 600;
	const uint16 Mash = static_cast<uint16>(Argc > 5 ? std::strtol(Argv[5], nullptr, 0) : 0);

	const FGameLibrary Library = FGameLibrary::Scan(Argv[1]);
	const FIso9660* Disc = Library.Find(EDiscRelease::UsaDisc1);
	if (Disc == nullptr)
	{
		return Fail("USA disc 1 not found in the Games folder");
	}
	auto Executable = ReadBootExecutable(*Disc);
	if (!Executable)
	{
		return Fail("boot executable unreadable");
	}
	auto Index = FGameFileIndex::Read(*Executable);
	if (!Index)
	{
		return Fail(Index.Error().Message);
	}
	const auto Identity = IdentifyDisc(*Disc);
	if (!Identity)
	{
		return Fail(Identity.Error().Message);
	}
	auto Sound = FGameSoundSession::Start(*Disc);
	if (!Sound)
	{
		return Fail(Sound.Error().Message);
	}
	FUnheardGameSound Unheard(*(*Sound)->Sound());
	auto Session = FGameSession::PowerOn(Disc->Image(), *Index, *Executable, *Identity, **Sound);
	if (!Session)
	{
		return Fail(Session.Error().Message);
	}
	// As the core's own tests play: the game's controls and camera, gears as sprites.
	FPlayerSettings Settings = (*Session)->Settings();
	Settings.Controls.bAlwaysRun = false;
	Settings.Controls.bWalkIntoDoors = false;
	Settings.Controls.DoorPause = NoDoorPause;
	Settings.Camera.bSteadyFollow = false;
	Settings.Field.GearModels = EFieldGearModels::Off;
	(*Session)->SetSettings(Settings);
	if (!Testing::CopyNewGameParty(Disc->Image(), *Index, (*Session)->Game()))
	{
		return Fail("new-game party file missing");
	}

	auto Loop = FGameLoop::EnterField(**Session, Map);
	if (!Loop)
	{
		return Fail(Loop.Error().Message);
	}

	std::ofstream Out(Argv[2], std::ios::binary);
	for (int32 Frame = 0; Frame < Frames; ++Frame)
	{
		FPadState Held;
		Held.Buttons = Frame % 2 == 0 ? Mash : 0;
		const std::vector<FPadState> PerVblank(static_cast<std::size_t>((*Loop)->VblanksPerFrame()), Held);
		Unheard.Advance(PsxTiming::FrameSeconds * static_cast<double>(PerVblank.size()));
		if (auto Error = (*Loop)->Frame(PerVblank))
		{
			Out << "{\"frame\":" << Frame << ",\"stopped\":\"" << Error->Message << "\"}\n";
			return Fail("loop stopped at frame " + std::to_string(Frame) + ": " + Error->Message);
		}
		const FFieldProgram* Field = (*Loop)->Field();
		Out << "{\"frame\":" << Frame << ",\"program\":" << static_cast<int>((*Loop)->Program());
		if (Field != nullptr)
		{
			const FEventContext& Context = Field->Runtime().Context();
			Out << ",\"map\":" << Context.RunningMap << ",\"running\":" << (Context.bFieldRunning ? 1 : 0)
				<< ",\"leader\":" << static_cast<int>(Context.PartyActors[0]) << ",\"msg\":"
				<< (std::any_of(Context.Messages.Windows.begin(), Context.Messages.Windows.end(), [](const FFieldMessageWindow& Window) { return Window.bOpen; }) ? 1 : 0);
			Out << ",\"actors\":[";
			for (std::size_t Actor = 0; Actor < Context.Actors.size(); ++Actor)
			{
				Out << (Actor ? "," : "") << Xyz(Context.Actors[Actor].Position);
			}
			Out << "]";
			if (const FFieldFrame* Drawn = Field->LatestFrame())
			{
				Out << ",\"tick\":" << Drawn->Tick << ",\"scene\":" << (Drawn->bSceneDrawn ? 1 : 0) << ",\"eye\":" << Xyz(Drawn->Eye)
					<< ",\"target\":" << Xyz(Drawn->Target) << ",\"models\":" << Drawn->SceneryWorld.size()
					<< ",\"polys\":" << Drawn->Scenery.Polygons.size() << ",\"quads\":" << Drawn->Quads.size()
					<< ",\"screen_prims\":" << Drawn->Screen.Primitives.size() << ",\"characters\":[";
				for (std::size_t Character = 0; Character < Drawn->Characters.size(); ++Character)
				{
					const FFieldCharacterView& View = Drawn->Characters[Character];
					Out << (Character ? "," : "") << "{\"key\":" << View.BlendKey << ",\"world\":" << Xyz(View.World)
						<< ",\"floor\":" << (View.bOnFloor ? 1 : 0) << "}";
				}
				Out << "]";
			}
		}
		Out << "}\n";
	}
	std::printf("probe: %d frames of map %u written to %s\n", Frames, Map, Argv[2]);
	return 0;
}
