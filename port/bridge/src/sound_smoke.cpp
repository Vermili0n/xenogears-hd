// The game's sound heard headless, exactly as the live game takes it (game/main.gd): the sound is made ahead of the device
// by FSession::SoundLeadFrames, topped up after every game frame while a device that plays in real time (one game frame's
// time per frame stepped) takes it. What is made in the recorded frames goes to a 16-bit stereo WAV; per second: RMS and peak.
// Usage: sound_smoke <Games folder> <map> <frames> <out.wav | -> [mash=0] [record from=0] [record to=frames] [heard=1]
//   map -1: the console powered on (notice, opening movie, title).
//   mash: buttons held every other frame (0x4000 = Cross, as session_smoke's fifth argument); heard=0 keeps the sound
//   unheard as every scripted run does (no WAV), to compare the game's state in both.

#include "xeno_session.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace
{
	void PutU32(std::FILE* File, uint32_t Value)
	{
		const uint8_t Bytes[4] = {static_cast<uint8_t>(Value), static_cast<uint8_t>(Value >> 8), static_cast<uint8_t>(Value >> 16), static_cast<uint8_t>(Value >> 24)};
		std::fwrite(Bytes, 1, 4, File);
	}

	void PutU16(std::FILE* File, uint16_t Value)
	{
		const uint8_t Bytes[2] = {static_cast<uint8_t>(Value), static_cast<uint8_t>(Value >> 8)};
		std::fwrite(Bytes, 1, 2, File);
	}

	bool WriteWav(const std::string& Path, const std::vector<int16_t>& Stereo, int Rate)
	{
		std::FILE* File = std::fopen(Path.c_str(), "wb");
		if (File == nullptr)
		{
			return false;
		}
		const uint32_t Data = static_cast<uint32_t>(Stereo.size() * sizeof(int16_t));
		std::fwrite("RIFF", 1, 4, File);
		PutU32(File, 36 + Data);
		std::fwrite("WAVEfmt ", 1, 8, File);
		PutU32(File, 16);
		PutU16(File, 1);
		PutU16(File, 2);
		PutU32(File, static_cast<uint32_t>(Rate));
		PutU32(File, static_cast<uint32_t>(Rate) * 4);
		PutU16(File, 4);
		PutU16(File, 16);
		std::fwrite("data", 1, 4, File);
		PutU32(File, Data);
		std::fwrite(Stereo.data(), 1, Data, File);
		return std::fclose(File) == 0;
	}

	double Dbfs(double Level)
	{
		return Level > 0.0 ? 20.0 * std::log10(Level / 32768.0) : -999.0;
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 5)
	{
		std::fprintf(stderr, "usage: sound_smoke <Games folder> <map> <frames> <out.wav | -> [mash=0] [from=0] [to=frames] [heard=1]\n");
		return 1;
	}
	const int Map = std::atoi(Argv[2]);
	const int Frames = std::atoi(Argv[3]);
	const std::string WavPath = Argv[4];
	const uint16_t Mash = static_cast<uint16_t>(Argc > 5 ? std::strtol(Argv[5], nullptr, 0) : 0);
	const int From = Argc > 6 ? std::atoi(Argv[6]) : 0;
	const int To = Argc > 7 ? std::atoi(Argv[7]) : Frames;
	const bool bHeard = Argc > 8 ? std::atoi(Argv[8]) != 0 : true;

	Xeno::FSession Session;
	// XENO_TRANSLATION=<image>: the translation's disc (FSession::Open), its sound its own; XENO_USA_SOUND=1: its sound
	// from USA disc 1 in the folder, as before (to compare the two).
	const char* Translation = std::getenv("XENO_TRANSLATION");
	std::printf("open: '%s' language %s\n", Session.Open(Argv[1], Translation != nullptr ? Translation : "").c_str(), Session.Language().c_str());
	// Map -1: the console powered on (the kernel's notice, the opening movie with its sound from the disc, the title).
	// XENO_CARD=<memory card image>:<slot>: that save loaded instead (the user's world map save, for one).
	const char* Card = std::getenv("XENO_CARD");
	const std::string CardText = Card != nullptr ? Card : "";
	const std::size_t CardColon = CardText.rfind(':');
	std::string Listing;
	// XENO_LOAD=<save state>: the game goes on from it instead (the map argument is then ignored).
	const char* Load = std::getenv("XENO_LOAD");
	std::printf("enter: '%s'\n", (Card != nullptr && CardColon != std::string::npos
			? Session.LoadCard(CardText.substr(0, CardColon), std::atoi(CardText.c_str() + CardColon + 1), Listing)
			: Load != nullptr ? Session.LoadState(Load) : Map < 0 ? Session.PowerOn() : Session.EnterField(Map)).c_str());
	const int Rate = Xeno::FSession::SoundRate();
	const int Lead = Xeno::FSession::SoundLeadFrames();
	std::printf("sound: %s, %d Hz, made %d frames (%.1f ms) ahead of the device\n", bHeard ? "heard" : "unheard", Rate, Lead, Lead * 1000.0 / Rate);

	std::vector<int16_t> Recorded;
	std::vector<int16_t> Chunk;
	// Where each recorded second's first sample was made: the game frame, the map then and what the screen showed (EScreenKind).
	std::vector<std::array<int, 3>> SecondStarts;
	// Per recorded second: the voices sounding after each top-up, summed by kind (music, effect, voice), and how many top-ups.
	std::vector<std::array<int, 4>> SecondVoices;
	long long Made = 0;
	double Taken = 0.0;
	int Frame = 0;
	auto TopUp = [&]() {
		const long long Want = Lead - (Made - static_cast<long long>(Taken));
		if (Want <= 0)
		{
			return;
		}
		Chunk.resize(static_cast<std::size_t>(Want) * 2);
		Session.RenderSound(Chunk.data(), static_cast<int>(Want));
		Made += Want;
		if (Frame >= From && Frame < To)
		{
			for (long long Sample = 0; Sample < Want; ++Sample)
			{
				if ((Recorded.size() / 2) % static_cast<std::size_t>(Rate) == 0)
				{
					SecondStarts.push_back({Frame, Session.Info().Map, static_cast<int>(Session.Info().Screen)});
				}
				Recorded.push_back(Chunk[static_cast<std::size_t>(Sample) * 2]);
				Recorded.push_back(Chunk[static_cast<std::size_t>(Sample) * 2 + 1]);
			}
			const std::size_t Second = (Recorded.size() / 2 - 1) / static_cast<std::size_t>(Rate);
			SecondVoices.resize(std::max(SecondVoices.size(), Second + 1));
			const std::array<int, 3> Voices = Session.SoundingVoices();
			for (std::size_t Kind = 0; Kind < 3; ++Kind)
			{
				SecondVoices[Second][Kind] += Voices[Kind];
			}
			++SecondVoices[Second][3];
		}
	};
	if (bHeard)
	{
		std::printf("hear: '%s'\n", Session.Hear(Lead).c_str());
		TopUp();
	}
	// XENO_SCRIPT=<frames>:<buttons hex>,...: the buttons held for so many frames each, before the mash takes over (as session_smoke).
	std::vector<std::pair<int, uint16_t>> Script;
	if (const char* Steps = std::getenv("XENO_SCRIPT"))
	{
		for (const char* At = Steps; *At != '\0';)
		{
			char* End = nullptr;
			const int Count = static_cast<int>(std::strtol(At, &End, 10));
			const uint16_t Buttons = static_cast<uint16_t>(*End == ':' ? std::strtol(End + 1, &End, 16) : 0);
			Script.emplace_back(Count, Buttons);
			if (End == At)
			{
				break;
			}
			At = *End == ',' ? End + 1 : End;
		}
	}
	std::size_t ScriptStep = 0;
	int ScriptLeft = Script.empty() ? 0 : Script[0].first;
	for (; Frame < Frames; ++Frame)
	{
		const int Vblanks = Session.VblanksPerFrame();
		uint16_t Held = Frame % 2 == 0 ? Mash : 0;
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
		// XENO_MOVIE=<frame>:<movie>:<end frame>: the running field asks for that movie there (as session_smoke).
		if (const char* Movie = std::getenv("XENO_MOVIE"); Movie != nullptr && std::atoi(Movie) == Frame && std::strchr(Movie, ':') != nullptr)
		{
			char* End = nullptr;
			const int Number = static_cast<int>(std::strtol(std::strchr(Movie, ':') + 1, &End, 10));
			const int EndFrame = *End == ':' ? std::atoi(End + 1) : 1;
			std::printf("movie %d asked before frame %d: '%s'\n", Number, Frame, Session.AskFieldMovie(Number, EndFrame).c_str());
		}
		const std::string Error = Session.Step(Held, 128, 128, false);
		if (!Error.empty())
		{
			std::printf("step %d: %s\n", Frame, Error.c_str());
			break;
		}
		if (bHeard)
		{
			// The device has played this frame's time meanwhile; the live game tops the sound up after its frames.
			Taken += Vblanks * Xeno::FSession::VblankSeconds() * Rate;
			TopUp();
		}
	}
	const Xeno::FFrameInfo Info = Session.Info();
	std::printf("after %d frames: program %d map %d tick %d running %d leader %d at %d %d %d\n", Frame, Info.Program, Info.Map, Info.Tick, Info.bRunning,
		Info.Leader, Info.LeaderPosition[0], Info.LeaderPosition[1], Info.LeaderPosition[2]);
	if (!bHeard)
	{
		return 0;
	}
	std::printf("made %lld frames, device took %.0f (game time %.3f s)\n", Made, Taken, Taken / Rate);
	const std::size_t RecordedFrames = Recorded.size() / 2;
	std::printf("recorded frames %d..%d: %zu sample frames (%.2f s)\n", From, To, RecordedFrames, static_cast<double>(RecordedFrames) / Rate);
	// Per second: RMS and peak of both channels, and how many of its 50 ms windows rise above -60 dBFS (sound present).
	std::printf("second  frame  map  screen   rms dBFS  peak  peak dBFS  active/20  at full scale  voices sounding (mean): music effect voice\n");
	const std::size_t Window = static_cast<std::size_t>(Rate) / 20;
	double TotalSquares = 0.0;
	for (std::size_t Second = 0; Second * Rate < RecordedFrames; ++Second)
	{
		const std::size_t First = Second * Rate;
		const std::size_t Last = std::min(RecordedFrames, First + static_cast<std::size_t>(Rate));
		double Squares = 0.0;
		int Peak = 0;
		int Active = 0;
		int Full = 0;
		for (std::size_t WindowFirst = First; WindowFirst < Last; WindowFirst += Window)
		{
			double WindowSquares = 0.0;
			const std::size_t WindowLast = std::min(Last, WindowFirst + Window);
			for (std::size_t Sample = WindowFirst * 2; Sample < WindowLast * 2; ++Sample)
			{
				const double Value = Recorded[Sample];
				WindowSquares += Value * Value;
				Peak = std::max(Peak, std::abs(static_cast<int>(Recorded[Sample])));
				Full += std::abs(static_cast<int>(Recorded[Sample])) >= 32766 ? 1 : 0;
			}
			Squares += WindowSquares;
			if (Dbfs(std::sqrt(WindowSquares / ((WindowLast - WindowFirst) * 2.0))) > -60.0)
			{
				++Active;
			}
		}
		TotalSquares += Squares;
		const double Rms = std::sqrt(Squares / ((Last - First) * 2.0));
		const std::array<int, 4> Voices = Second < SecondVoices.size() ? SecondVoices[Second] : std::array<int, 4>{};
		const double Samples = std::max(Voices[3], 1);
		std::printf("%6zu  %5d  %3d  %6d  %8.1f  %5d  %8.1f  %5d  %12d      %5.1f  %5.1f  %5.1f\n", Second, SecondStarts[Second][0], SecondStarts[Second][1], SecondStarts[Second][2],
			Dbfs(Rms), Peak, Dbfs(Peak), Active, Full, Voices[0] / Samples, Voices[1] / Samples, Voices[2] / Samples);
	}
	if (RecordedFrames > 0)
	{
		std::printf("whole: rms %.1f dBFS\n", Dbfs(std::sqrt(TotalSquares / (RecordedFrames * 2.0))));
	}
	if (WavPath != "-")
	{
		std::printf("wav: %s %s\n", WavPath.c_str(), WriteWav(WavPath, Recorded, Rate) ? "written" : "NOT written");
	}
	return 0;
}
