// Every frame of the party's field sprite sets drawn as the bridge draws them from the texture pack: for each piece of
// each frame, whether it comes wholly from the pack, partly or from VRAM, and why (FSession::ClassifySpriteQuad, the
// same lookup BuildWorld runs on a field sprite's piece), under each palette the game was seen drawing the set with.
//
// Usage: sprite_coverage <Games folder> <pack folder> <out folder> [first character=0] [last character=10] [palettes.csv]
//
// A character's set is its party sprite file (directory 4, file 5 + character), unpacked as the field unpacks it
// (FPartySpriteFiles), its frames built and their cells uploaded by the core's own sprite system (FSpriteSystem, as
// sprite_parts_dump builds them, the CLUT at 256,480 and the texture at 640,256), its pieces drawn by the core's own
// sprite drawing (DrawSpriteParts). Each frame is built alone on an empty VRAM: names by upload do not depend on what
// lies around a cell, a drawn rectangle's name (the fallback for 4-bit pieces) does (here the cell's neighbours are empty).
//
// Animations: each one started (SetAnimation) at each of 8 facings and run 240 logic ticks (TickAnimation); the frames it
// showed are its frames. A frame no animation reached is listed with animation "-".
//
// Palettes: "own" is the file's palettes as Create uploads them (palette set 0). palettes.csv (story_walk's
// sprite_palettes.csv with XENO_SPRITE_PALETTES=1: upload, palette, CLUT place, colours) adds every other palette seen
// over an upload of this set at the field's party CLUTs (rows 224-226, x 256-287), put at the CLUT place it was seen at
// (relative to the slot's), each judged after the own
// palettes have been seen (the bridge's agreeing-palette pictures known, as in a scene where the set was drawn before).
//
// Writes into <out folder>, per character c: frames_<c>.csv (a row per palette and frame), pieces_<c>.csv (a row per
// piece), animations_<c>.csv, draws_<c>.jsonl (each frame's pieces: cell, the original texels as RGBA, what is drawn
// where, for the contact sheets of tools/sprite_coverage.py).

#include "xeno_session.h"

#include "Field/FieldPartySprites.h"
#include "Foundation/Crc32.h"
#include "Game/PsxRandom.h"
#include "Graphics/Gte.h"
#include "Graphics/GteMatrix.h"
#include "Graphics/Sprite.h"
#include "Graphics/SpriteDrawing.h"
#include "Graphics/SpriteFile.h"
#include "Graphics/SpriteSystem.h"
#include "Graphics/Texture.h"
#include "Graphics/Vram.h"
#include "Media/GameFileIndex.h"
#include "Media/GameLibrary.h"
#include "Media/PsxExecutable.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <span>
#include <sstream>
#include <string>
#include <vector>

using namespace Weltall;

namespace
{
	constexpr int32 ClutX = 0x100, ClutY = 0x1E0, TextureX = 0x280, TextureY = 0x100;
	constexpr int32 AnimationTicks = 240;
	constexpr int32 Facings = 8;

	/** A sprite of the file made as the field makes a party member's (sprite_parts_dump's BuiltParts). */
	struct FMade
	{
		FSpriteSystem System;
		FPsxRandom Random{1};
		FSprite Sprite;

		explicit FMade(const FSpriteFile& File)
		{
			System.Random = &Random;
			System.Create(Sprite, File, ClutX, ClutY, TextureX, TextureY);
			System.SetPartCapacity(Sprite, 16);
		}
	};

	/** The frames each animation shows, over every facing. */
	std::map<int32, std::set<int32>> AnimationFrames(const FSpriteFile& File)
	{
		std::map<int32, std::set<int32>> Shown;
		const int32 Count = File.AnimationCount(File.Tables());
		for (int32 Animation = 0; Animation < Count; ++Animation)
		{
			for (int32 Facing = 0; Facing < Facings; ++Facing)
			{
				auto Made = std::make_unique<FMade>(File);
				Made->System.SetFacing(Made->Sprite, Facing * 4096 / Facings);
				Made->System.SetAnimation(Made->Sprite, Animation);
				for (int32 Tick = 0; Tick < AnimationTicks && Made->System.Fault() == ESpriteFault::None; ++Tick)
				{
					Made->System.TickAnimation(Made->Sprite);
					if (Made->Sprite.Frame > 0)
					{
						Shown[Animation].insert(Made->Sprite.Frame);
					}
				}
			}
		}
		return Shown;
	}

	/** A palette to judge the set with: the colours put at each CLUT place it was seen at (none: the file's own). */
	struct FPaletteVariant
	{
		std::string Name;
		std::map<int32, std::vector<uint16>> ColoursAt; // CLUT x offset from the slot's -> colours
	};

	std::string Hex(const std::vector<uint8>& Bytes)
	{
		static const char Digits[] = "0123456789abcdef";
		std::string Out;
		Out.reserve(Bytes.size() * 2);
		for (const uint8 Byte : Bytes)
		{
			Out += Digits[Byte >> 4];
			Out += Digits[Byte & 15];
		}
		return Out;
	}

	/** The piece's original texels, first to last, through its CLUT as RGBA (alpha 0 where the colour is 0). */
	std::vector<uint8> Texels(const FVram& Vram, const Xeno::FSpritePieceVerdict& Piece)
	{
		std::vector<uint8> Rgba;
		const int Per = Piece.Depth == 0 ? 4 : Piece.Depth == 1 ? 2 : 1;
		for (int V = Piece.V; V < Piece.V + Piece.Height; ++V)
		{
			for (int U = Piece.U; U < Piece.U + Piece.Width; ++U)
			{
				const uint16 Word = Vram.TexelAt(Piece.PageX + U / Per, Piece.PageY + V);
				const uint16 Colour = Per == 4 ? Vram.TexelAt(Piece.ClutX + (Word >> ((U & 3) * 4) & 15), Piece.ClutY)
					: Per == 2 ? Vram.TexelAt(Piece.ClutX + (Word >> ((U & 1) * 8) & 255), Piece.ClutY) : Word;
				Rgba.push_back(static_cast<uint8>((Colour & 31) * 255 / 31));
				Rgba.push_back(static_cast<uint8>((Colour >> 5 & 31) * 255 / 31));
				Rgba.push_back(static_cast<uint8>((Colour >> 10 & 31) * 255 / 31));
				Rgba.push_back(Colour == 0 ? 0 : 255);
			}
		}
		return Rgba;
	}

	std::string Joined(const std::set<int32>& Values)
	{
		std::string Out;
		for (const int32 Value : Values)
		{
			Out += (Out.empty() ? "" : " ") + std::to_string(Value);
		}
		return Out.empty() ? "-" : Out;
	}
}

int main(int Argc, char** Argv)
{
	if (Argc < 4)
	{
		std::fprintf(stderr, "usage: sprite_coverage <Games folder> <pack folder> <out folder> [first=0] [last=10] [palettes.csv]\n");
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
	Xeno::FSession Bridge;
	if (const std::string Error = Bridge.SetPack(Argv[2]); !Error.empty())
	{
		std::fprintf(stderr, "pack: %s\n", Error.c_str());
		return 1;
	}
	const std::filesystem::path Out = Argv[3];
	std::filesystem::create_directories(Out);
	const int First = Argc > 4 ? std::atoi(Argv[4]) : 0, Last = Argc > 5 ? std::atoi(Argv[5]) : 10;
	// Palettes seen on the walk: upload -> (palette, CLUT x, colours).
	struct FSeen
	{
		uint32 Palette = 0;
		int32 ClutX = 0;
		std::vector<uint16> Colours;
	};
	std::multimap<uint32, FSeen> SeenPalettes;
	if (Argc > 6)
	{
		std::ifstream Csv(Argv[6]);
		std::string Line;
		std::getline(Csv, Line);
		while (std::getline(Csv, Line))
		{
			std::stringstream Fields(Line);
			std::string Upload, Palette, X, Y, Depth, Pieces, Colours;
			std::getline(Fields, Upload, ',');
			std::getline(Fields, Palette, ',');
			std::getline(Fields, X, ',');
			std::getline(Fields, Y, ',');
			std::getline(Fields, Depth, ',');
			std::getline(Fields, Pieces, ',');
			std::getline(Fields, Colours, ',');
			// Only palettes seen where the field keeps the party's CLUTs (rows 224-226 from x 256, a slot's 16 or 32 colours):
			// elsewhere an upload of a few texels (a 4 x 1 cell) matches other sprites' cells by its crc alone.
			if (std::atoi(Y.c_str()) < 224 || std::atoi(Y.c_str()) > 226 || std::atoi(X.c_str()) < 256 || std::atoi(X.c_str()) > 287)
			{
				continue;
			}
			FSeen Seen;
			Seen.Palette = static_cast<uint32>(std::strtoul(Palette.c_str(), nullptr, 16));
			Seen.ClutX = std::atoi(X.c_str());
			for (std::size_t At = 0; At + 4 <= Colours.size(); At += 4)
			{
				Seen.Colours.push_back(static_cast<uint16>(std::strtoul(Colours.substr(At, 4).c_str(), nullptr, 16)));
			}
			SeenPalettes.emplace(static_cast<uint32>(std::strtoul(Upload.c_str(), nullptr, 16)), Seen);
		}
		std::printf("palettes seen: %zu (upload, palette) pairs\n", SeenPalettes.size());
	}

	for (int Character = First; Character <= Last; ++Character)
	{
		FPartySpriteFiles Party(Disc->Image(), *Index);
		if (auto Error = Party.Unpack(0, Character))
		{
			std::fprintf(stderr, "character %d: unpack: %s\n", Character, Error->Message.c_str());
			continue;
		}
		const FSpriteFile& File = Party.Buffer(0);
		const int32 Frames = File.FrameCount(File.Tables());
		const std::map<int32, std::set<int32>> Shown = AnimationFrames(File);
		std::map<int32, std::set<int32>> AnimationsOf;
		{
			std::ofstream Animations(Out / ("animations_" + std::to_string(Character) + ".csv"), std::ios::trunc);
			Animations << "character,animation,frames\n";
			for (const auto& [Animation, FramesShown] : Shown)
			{
				Animations << Character << ',' << Animation << ',' << Joined(FramesShown) << '\n';
				for (const int32 Frame : FramesShown)
				{
					AnimationsOf[Frame].insert(Animation);
				}
			}
		}
		std::ofstream FrameRows(Out / ("frames_" + std::to_string(Character) + ".csv"), std::ios::trunc);
		std::ofstream PieceRows(Out / ("pieces_" + std::to_string(Character) + ".csv"), std::ios::trunc);
		std::ofstream Draws(Out / ("draws_" + std::to_string(Character) + ".jsonl"), std::ios::trunc);
		FrameRows << "character,set,palette_variant,palettes,frame,animations,pieces,whole,partial,vram,texels,texels_vram,verdict\n";
		PieceRows << "character,set,palette_variant,frame,animations,piece,kind,miss,texels,texels_vram,page_x,page_y,clut_x,clut_y,u,v,w,h,names,tried\n";
		std::vector<FPaletteVariant> Variants{{"own", {}}};
		std::set<uint32> Uploads;
		std::set<uint32> OwnPalettes;
		Bridge.ForgetSamePalettes();
		int Totals[3][3] = {};
		for (std::size_t Variant = 0; Variant < Variants.size(); ++Variant)
		{
			int Verdicts[3] = {};
			for (int32 Frame = 1; Frame <= Frames; ++Frame)
			{
				auto Made = std::make_unique<FMade>(File);
				Made->System.SetFrame(Made->Sprite, Frame);
				Made->System.BuildPendingFrames();
				// XENO_UPLOADS=1: the frame's uploads as the core's sprite system asks for them (rectangle, file offset, cell).
				if (std::getenv("XENO_UPLOADS") != nullptr && Variant == 0)
				{
					for (const FSpriteUpload& Upload : Made->System.Uploads())
					{
						// The crc32 of the file's bytes the upload takes (its units row by row, as Beetle hashes an upload).
						const std::span<const uint8> Bytes = File.From(Upload.Offset);
						const std::size_t Size = std::min<std::size_t>(Bytes.size(), static_cast<std::size_t>(Upload.Rect.Width) * Upload.Rect.Height * 2);
						std::printf("character %d frame %d upload %d,%d %dx%d offset %u crc %x%s%s\n", Character, Frame, Upload.Rect.X, Upload.Rect.Y, Upload.Rect.Width,
							Upload.Rect.Height, Upload.Offset, Upload.File != nullptr ? Crc32(Bytes.first(Size)) : 0u, Upload.File == nullptr ? " clear" : "",
							Upload.bCell ? " cell" : "");
					}
				}
				auto Vram = std::make_unique<FVram>();
				Made->System.FlushUploads(*Vram);
				for (const auto& [Offset, Colours] : Variants[Variant].ColoursAt)
				{
					FVramImage Clut;
					Clut.Rect = {static_cast<int16>(ClutX + Offset), static_cast<int16>(ClutY), static_cast<int16>(Colours.size()), 1};
					Clut.Units = Colours;
					Vram->Upload(Clut);
				}
				std::vector<FSpriteQuad> Quads;
				DrawSpriteParts(Made->Sprite, FGteMatrix::Identity(), 0, &Quads);
				const std::string Animations = AnimationsOf.count(Frame) != 0 ? Joined(AnimationsOf[Frame]) : "-";
				int Kinds[3] = {}, Texels = 0;
				double FromVram = 0.0;
				std::set<uint32> PalettesUsed;
				std::string Json = "{\"character\":" + std::to_string(Character) + ",\"variant\":\"" + Variants[Variant].Name + "\",\"frame\":" + std::to_string(Frame)
					+ ",\"animations\":\"" + Animations + "\",\"pieces\":[";
				for (std::size_t Piece = 0; Piece < Quads.size(); ++Piece)
				{
					const FSpriteQuad& Quad = Quads[Piece];
					const Xeno::FSpritePieceVerdict Verdict = Bridge.ClassifySpriteQuad(*Vram, Quad);
					const int Kind = std::clamp(Verdict.Kind, 0, 2);
					++Kinds[Kind];
					Texels += Verdict.Texels;
					FromVram += Verdict.TexelsFromVram;
					std::string Names;
					for (const auto& Name : Verdict.Names)
					{
						char Text[24];
						std::snprintf(Text, sizeof(Text), "%s%x-%x", Names.empty() ? "" : " ", Name[0], Name[1]);
						Names += Text;
						PalettesUsed.insert(Name[1]);
						if (Variant == 0)
						{
							Uploads.insert(Name[0]);
							OwnPalettes.insert(Name[1]);
						}
					}
					PieceRows << Character << ',' << 427 + Character << "_0," << Variants[Variant].Name << ',' << Frame << ',' << Animations << ',' << Piece << ','
							  << Verdict.Kind << ',' << Verdict.Miss << ',' << Verdict.Texels << ',' << Verdict.TexelsFromVram << ',' << Verdict.PageX << ','
							  << Verdict.PageY << ',' << Verdict.ClutX << ',' << Verdict.ClutY << ',' << Verdict.U << ',' << Verdict.V << ',' << Verdict.Width << ','
							  << Verdict.Height << ',' << Names << ",\"" << Verdict.Tried << "\"\n";
					// The piece's cell in the sprite's own units (corners 0 and 3), its texels, and what is drawn where.
					const std::array<float, 3> C0 = ViewPoint(Quad.Matrix, Quad.Corners[0]), C3 = ViewPoint(Quad.Matrix, Quad.Corners[3]);
					char Head[256];
					std::snprintf(Head, sizeof(Head), "%s{\"x0\":%g,\"y0\":%g,\"x1\":%g,\"y1\":%g,\"u\":%d,\"v\":%d,\"w\":%d,\"h\":%d,\"kind\":%d,\"miss\":\"%s\",\"texels\":\"",
						Piece ? "," : "", C0[0], C0[1], C3[0], C3[1], Verdict.U, Verdict.V, Verdict.Width, Verdict.Height, Verdict.Kind, Verdict.Miss.c_str());
					Json += Head + Hex(::Texels(*Vram, Verdict)) + "\",\"draws\":[";
					for (std::size_t Draw = 0; Draw < Verdict.Draws.size(); ++Draw)
					{
						const Xeno::FSpritePieceDraw& D = Verdict.Draws[Draw];
						std::string Path = D.Texture;
						std::replace(Path.begin(), Path.end(), '\\', '/');
						char Body[160];
						std::snprintf(Body, sizeof(Body), "\",\"cell\":[%g,%g,%g,%g],\"src\":[%g,%g,%g,%g]}", D.Cell[0], D.Cell[1], D.Cell[2], D.Cell[3], D.Source[0],
							D.Source[1], D.Source[2], D.Source[3]);
						Json += std::string(Draw ? "," : "") + "{\"t\":\"" + Path + Body;
					}
					Json += "]}";
				}
				Json += "]}\n";
				Draws << Json;
				const int Verdict = Kinds[1] == 0 && Kinds[2] == 0 ? 0 : Kinds[0] == 0 && Kinds[1] == 0 ? 2 : 1;
				++Verdicts[Verdict];
				++Totals[std::min<std::size_t>(Variant, 1)][Verdict];
				std::string Palettes;
				for (const uint32 Palette : PalettesUsed)
				{
					char Text[12];
					std::snprintf(Text, sizeof(Text), "%s%x", Palettes.empty() ? "" : " ", Palette);
					Palettes += Text;
				}
				static const char* const VerdictNames[] = {"hd", "partly", "not"};
				FrameRows << Character << ',' << 427 + Character << "_0," << Variants[Variant].Name << ',' << Palettes << ',' << Frame << ',' << Animations << ','
						  << Quads.size() << ',' << Kinds[0] << ',' << Kinds[1] << ',' << Kinds[2] << ',' << Texels << ',' << FromVram << ',' << VerdictNames[Verdict]
						  << '\n';
			}
			std::printf("character %d (set %d_0) palettes %s: %d frames, %d animations; frames wholly HD %d, partly %d, not %d\n", Character, 427 + Character,
				Variants[Variant].Name.c_str(), Frames, static_cast<int>(Shown.size()), Verdicts[0], Verdicts[1], Verdicts[2]);
			if (Variant == 0)
			{
				// The other palettes seen over this set's uploads, each a variant at the CLUT place it was seen at.
				std::map<std::string, FPaletteVariant> Others;
				std::map<std::string, std::set<uint32>> SeenOver;
				for (const uint32 Upload : Uploads)
				{
					const auto [From, To] = SeenPalettes.equal_range(Upload);
					for (auto Seen = From; Seen != To; ++Seen)
					{
						if (OwnPalettes.count(Seen->second.Palette) != 0)
						{
							continue;
						}
						char Name[16];
						std::snprintf(Name, sizeof(Name), "%x", Seen->second.Palette);
						FPaletteVariant& Other = Others[Name];
						Other.Name = Name;
						Other.ColoursAt[Seen->second.ClutX - ClutX] = Seen->second.Colours;
						SeenOver[Name].insert(Upload);
					}
				}
				// A palette the game draws the set with is seen over many of its uploads; one seen over a cell or two only is
				// another sprite's whose few-texel cells have the same crc (a 4 x 1 block of one colour): not this set's.
				constexpr std::size_t MostCoincidences = 4;
				for (auto& [Name, Other] : Others)
				{
					std::printf("character %d: palette %s seen over %zu of the set's uploads%s\n", Character, Name.c_str(), SeenOver[Name].size(),
						SeenOver[Name].size() > MostCoincidences ? "" : " (another sprite's: not judged)");
					if (SeenOver[Name].size() > MostCoincidences)
					{
						Variants.push_back(std::move(Other));
					}
				}
			}
		}
		FrameRows.flush();
		PieceRows.flush();
		Draws.flush();
	}
	return 0;
}
