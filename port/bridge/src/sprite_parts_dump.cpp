// Every frame of a party member's field sprite file as WeltallCore's sprite system builds it, one JSON line per frame:
// each piece's place (X, Y), size, texel origin (U, V), its flags and whether it is drawn mirrored. Built twice, as the
// original places mirrored pieces and with Weltall's fix (bMirroredPartsPlacedByArt), to compare with the user's layouts.
// Usage: sprite_parts_dump <Games folder> <character> <out.jsonl>

#include "Field/FieldPartySprites.h"
#include "Graphics/SpriteFile.h"
#include "Graphics/SpriteSystem.h"
#include "Media/GameFileIndex.h"
#include "Media/GameLibrary.h"
#include "Media/PsxExecutable.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

using namespace Weltall;

namespace
{
	std::vector<FSpritePart> BuiltParts(const FSpriteFile& File, int32 Frame, bool bPlacedByArt)
	{
		FSpriteSystem System;
		System.bMirroredPartsPlacedByArt = bPlacedByArt;
		FSprite Sprite;
		System.Create(Sprite, File, 0x100, 0x1E0, 0x280, 0x100);
		System.SetPartCapacity(Sprite, 16);
		System.SetFrame(Sprite, Frame);
		System.BuildPendingFrames();
		return {Sprite.Parts.begin(), Sprite.Parts.begin() + Sprite.PartCount()};
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: sprite_parts_dump <Games folder> <character> <out.jsonl>\n");
		return 1;
	}
	const FGameLibrary Library = FGameLibrary::Scan(Argv[1]);
	const FIso9660* Disc = Library.Find(EDiscRelease::UsaDisc1);
	if (Disc == nullptr)
	{
		std::fprintf(stderr, "no USA disc 1\n");
		return 1;
	}
	auto Executable = ReadBootExecutable(*Disc);
	auto Index = Executable ? FGameFileIndex::Read(*Executable) : TResult<FGameFileIndex>(MakeError("no executable"));
	if (!Index)
	{
		std::fprintf(stderr, "no file index\n");
		return 1;
	}
	FPartySpriteFiles Party(Disc->Image(), *Index);
	if (auto Error = Party.Unpack(0, std::atoi(Argv[2])))
	{
		std::fprintf(stderr, "unpack: %s\n", Error->Message.c_str());
		return 1;
	}
	const FSpriteFile& File = Party.Buffer(0);
	std::ofstream Out(Argv[3]);
	const int32 Frames = File.FrameCount(File.Tables());
	for (int32 Frame = 1; Frame <= Frames; ++Frame)
	{
		Out << "{\"frame\":" << Frame;
		for (const bool bPlacedByArt : {false, true})
		{
			Out << (bPlacedByArt ? ",\"aligned\":[" : ",\"original\":[");
			const std::vector<FSpritePart> Parts = BuiltParts(File, Frame, bPlacedByArt);
			for (std::size_t Part = 0; Part < Parts.size(); ++Part)
			{
				const FSpritePart& P = Parts[Part];
				Out << (Part ? "," : "") << "{\"x\":" << static_cast<int>(P.X) << ",\"y\":" << static_cast<int>(P.Y) << ",\"w\":" << static_cast<int>(P.Width)
					<< ",\"h\":" << static_cast<int>(P.Height) << ",\"gw\":" << static_cast<int>(static_cast<int8>(P.GrowWidth))
					<< ",\"gh\":" << static_cast<int>(static_cast<int8>(P.GrowHeight)) << ",\"u\":" << static_cast<int>(P.U) << ",\"v\":" << static_cast<int>(P.V)
					<< ",\"flags\":" << static_cast<uint32>(P.Flags) << "}";
			}
			Out << "]";
		}
		Out << "}\n";
	}
	std::printf("%d frames\n", Frames);
	return 0;
}
