// A disc's movies as the core decodes them (FMovieStream, DecodeStrBitstream, DecodeMdecPicture, ToRgb24), headless: to
// match a replacement video to the movie it stands for, by measurement.
//
//   movie_dump <image> list                         each movie of the disc's movie group: number, sectors, frames, size
//   movie_dump <image> <N> <out folder> [every]     movie N: thumbs.bin (every picture, 64 wide, grey, 8 bits) and
//                                                   frames.csv; f<frame>.ppm of every <every>-th picture (0: none)
#include "Formats/StrBitstream.h"
#include "Graphics/Mdec.h"
#include "Media/CdImage.h"
#include "Media/GameFileIndex.h"
#include "Media/GameMovies.h"
#include "Media/Iso9660.h"
#include "Media/MovieStream.h"
#include "Media/PsxExecutable.h"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

using namespace Weltall;

namespace
{
	constexpr int ThumbWidth = 64;

	/** The picture's luminance averaged into ThumbWidth x (Height * ThumbWidth / Width) cells. */
	std::vector<uint8> Thumb(const std::vector<uint8>& Rgb, int Width, int Height, int& ThumbHeight)
	{
		ThumbHeight = Height * ThumbWidth / Width;
		std::vector<uint8> Out(static_cast<std::size_t>(ThumbWidth) * ThumbHeight);
		for (int Y = 0; Y < ThumbHeight; ++Y)
		{
			for (int X = 0; X < ThumbWidth; ++X)
			{
				const int X0 = X * Width / ThumbWidth, X1 = (X + 1) * Width / ThumbWidth;
				const int Y0 = Y * Height / ThumbHeight, Y1 = (Y + 1) * Height / ThumbHeight;
				double Sum = 0;
				int Count = 0;
				for (int Py = Y0; Py < Y1; ++Py)
				{
					for (int Px = X0; Px < X1; ++Px)
					{
						const uint8* P = &Rgb[(static_cast<std::size_t>(Py) * Width + Px) * 3];
						Sum += 0.299 * P[0] + 0.587 * P[1] + 0.114 * P[2];
						++Count;
					}
				}
				Out[static_cast<std::size_t>(Y) * ThumbWidth + X] = static_cast<uint8>(Count > 0 ? Sum / Count + 0.5 : 0);
			}
		}
		return Out;
	}
}

int main(int Count, char** Arguments)
{
	if (Count < 3)
	{
		std::fprintf(stderr, "movie_dump <image> list | <N> <out folder> [every]\n");
		return 2;
	}
	auto Image = FCdImage::Open(std::filesystem::u8path(Arguments[1]));
	if (!Image)
	{
		std::fprintf(stderr, "image: %s\n", Image.Error().Message.c_str());
		return 1;
	}
	auto Disc = FIso9660::Open(std::move(*Image));
	if (!Disc)
	{
		std::fprintf(stderr, "disc: %s\n", Disc.Error().Message.c_str());
		return 1;
	}
	const auto Executable = ReadBootExecutable(*Disc);
	const auto Index = Executable ? FGameFileIndex::Read(*Executable) : TResult<FGameFileIndex>(MakeError("no boot program"));
	if (!Index)
	{
		std::fprintf(stderr, "index: %s\n", Index.Error().Message.c_str());
		return 1;
	}
	const std::string What = Arguments[2];
	const bool bList = What == "list";
	const int First = bList ? 0 : std::atoi(What.c_str());
	for (int Number = First; const auto Location = FindMovie(*Index, Number); ++Number)
	{
		FMovieStream Stream(Disc->Image(), Location->FirstLba, Location->SectorCount);
		std::vector<int16> Sound;
		int Frames = 0;
		uint32 FirstFrame = 0, LastFrame = 0;
		int Width = 0, Height = 0;
		std::FILE* Thumbs = nullptr;
		std::FILE* Csv = nullptr;
		std::filesystem::path Out;
		int Every = 0;
		if (!bList)
		{
			Out = std::filesystem::u8path(Count > 3 ? Arguments[3] : ".");
			std::filesystem::create_directories(Out);
			Every = Count > 4 ? std::atoi(Arguments[4]) : 0;
			Thumbs = std::fopen((Out / "thumbs.bin").string().c_str(), "wb");
			Csv = std::fopen((Out / "frames.csv").string().c_str(), "w");
			std::fprintf(Csv, "index,frame,width,height,thumb_height,sound_frames_before\n");
		}
		while (true)
		{
			const std::size_t SoundBefore = Sound.size() / 2;
			auto Frame = Stream.NextFrame(Sound);
			if (!Frame)
			{
				std::fprintf(stderr, "movie %d: %s\n", Number, Frame.Error().Message.c_str());
				break;
			}
			if (!*Frame)
			{
				break;
			}
			if (Frames == 0)
			{
				FirstFrame = (*Frame)->FrameNumber;
			}
			LastFrame = (*Frame)->FrameNumber;
			Width = (*Frame)->Width;
			Height = (*Frame)->Height;
			if (!bList)
			{
				const auto Codes = DecodeStrBitstream((*Frame)->Bitstream, (*Frame)->Width, (*Frame)->Height);
				const auto Picture = Codes ? DecodeMdecPicture(*Codes, (*Frame)->Width, (*Frame)->Height, FMdecTables::Standard())
										   : TResult<FMdecPicture>(Codes.Error());
				if (!Picture)
				{
					std::fprintf(stderr, "frame %u: %s\n", (*Frame)->FrameNumber, Picture.Error().Message.c_str());
					++Frames;
					continue;
				}
				const std::vector<uint8> Rgb = ToRgb24(*Picture);
				int ThumbHeight = 0;
				const std::vector<uint8> Small = Thumb(Rgb, Picture->Width, Picture->Height, ThumbHeight);
				std::fwrite(Small.data(), 1, Small.size(), Thumbs);
				std::fprintf(Csv, "%d,%u,%d,%d,%d,%zu\n", Frames, (*Frame)->FrameNumber, Picture->Width, Picture->Height, ThumbHeight, SoundBefore);
				if (Every > 0 && Frames % Every == 0)
				{
					char Name[32];
					std::snprintf(Name, sizeof(Name), "f%05u.ppm", (*Frame)->FrameNumber);
					if (std::FILE* Ppm = std::fopen((Out / Name).string().c_str(), "wb"))
					{
						std::fprintf(Ppm, "P6\n%d %d\n255\n", Picture->Width, Picture->Height);
						std::fwrite(Rgb.data(), 1, Rgb.size(), Ppm);
						std::fclose(Ppm);
					}
				}
			}
			++Frames;
		}
		std::printf("movie %d: lba %u, sectors %u, pictures %d, frames %u..%u, %dx%d, %.2f s at 15/s, sound %.2f s\n", Number, Location->FirstLba,
			Location->SectorCount, Frames, FirstFrame, LastFrame, Width, Height, Frames / 15.0, Sound.size() / 2 / 44100.0);
		if (Thumbs != nullptr)
		{
			std::fclose(Thumbs);
			std::fclose(Csv);
		}
		if (!bList)
		{
			break;
		}
	}
	return 0;
}
