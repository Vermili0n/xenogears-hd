// Every text of a disc as the core's readers take it (ReadGameText for each file of the text export: every field map,
// the names, menus, battle, world map, arena, chapters), decoded without drawing: how many messages load, how many decode
// without unknown codes, how many type the translation's own letters.
// Usage: text_sweep <image .cue/.bin> <out.tsv> [raw]
// A translation's disc the bridge knows (xeno_translation.h) is read as the bridge gives it to the core: its map archives
// mended (MendedMapArchives) unless "raw"; its narrow letters' range from its program (else 93h-B6h, the Russian's).
// The TSV has a line per message: kind, map, table, number, flags, codes (hex). Unknown codes:
//   an unknown control (a byte below 10h that is no mark, MesTextOfCodes writes it raw as {0N}; an extended code with no
//   mark, {xNN}), or a glyph the disc's font has no picture for. "Kana" counts glyphs past the narrow range on the first
//   page or on the second (FE): the USA font draws kana there, the Russian too, and no text of either should type them.

#include "xeno_translation.h"

#include "Game/GameText.h"
#include "Media/CdImage.h"
#include "Media/DiscModFiles.h"
#include "Media/GameFileIndex.h"
#include "Media/Iso9660.h"
#include "Media/PsxExecutable.h"
#include "Text/MesResident.h"
#include "Text/MesText.h"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <map>
#include <string>

using namespace Weltall;

namespace
{
	const char* KindName(EGameTextFile Kind)
	{
		switch (Kind)
		{
		case EGameTextFile::Field: return "field";
		case EGameTextFile::Names: return "names";
		case EGameTextFile::Menu: return "menu";
		case EGameTextFile::MenuHelp: return "menu-help";
		case EGameTextFile::Battle: return "battle";
		case EGameTextFile::BattleHelp: return "battle-help";
		case EGameTextFile::Enemies: return "enemies";
		case EGameTextFile::BattleEvents: return "battle-events";
		case EGameTextFile::WorldMap: return "worldmap";
		case EGameTextFile::Battling: return "battling";
		case EGameTextFile::Chapters: return "chapters";
		}
		return "?";
	}

	struct FCount
	{
		int Files = 0, FilesFailed = 0, Messages = 0, Empty = 0, Clean = 0, Unknown = 0, Cyrillic = 0, Latin = 0, Kana = 0;
	};
}

int main(int Argc, char** Argv)
{
	if (Argc < 3)
	{
		std::fprintf(stderr, "usage: text_sweep <image> <out.tsv> [narrow first hex] [narrow end hex]\n");
		return 1;
	}
	const bool bRaw = Argc > 3 && std::string(Argv[3]) == "raw";
	uint32 NarrowFirst = 0x93;
	uint32 NarrowEnd = 0xB7;
	auto Image = FCdImage::Open(std::filesystem::u8path(Argv[1]));
	if (!Image)
	{
		std::printf("image: %s\n", Image.Error().Message.c_str());
		return 1;
	}
	auto Disc = FIso9660::Open(std::move(*Image));
	if (!Disc)
	{
		std::printf("disc: %s\n", Disc.Error().Message.c_str());
		return 1;
	}
	auto Executable = ReadBootExecutable(*Disc);
	if (!Executable)
	{
		std::printf("executable: %s\n", Executable.Error().Message.c_str());
		return 1;
	}
	auto Index = FGameFileIndex::Read(*Executable);
	if (!Index)
	{
		std::printf("index: %s\n", Index.Error().Message.c_str());
		return 1;
	}
	if (const TResult<Xeno::FTranslation> Translation = Xeno::RecognizeTranslation(*Disc, *Executable))
	{
		NarrowFirst = Translation->NarrowFirst;
		NarrowEnd = Translation->NarrowEnd;
		int Mended = 0;
		const std::vector<FModFile> Files = Xeno::MendedMapArchives(Disc->Image(), *Index, Mended);
		if (!bRaw)
		{
			Disc->Image().SetModFiles(FDiscModFiles::Make(*Index, 1, Files));
		}
		std::printf("translation %s: narrow %02X-%02X, map archives to mend %d%s\n", Translation->Language.c_str(), NarrowFirst, NarrowEnd - 1, Mended,
			bRaw ? " (left as the disc has them)" : " (mended)");
	}
	else
	{
		std::printf("not a translation the bridge knows: %s\n", Translation.Error().Message.c_str());
	}
	auto Resident = LoadMesResident(Disc->Image(), *Index, *Executable);
	if (!Resident)
	{
		std::printf("font: %s\n", Resident.Error().Message.c_str());
		return 1;
	}
	const FMesFont& Font = Resident->Font;
	std::FILE* Out = std::fopen(Argv[2], "wb");
	if (Out == nullptr)
	{
		std::printf("cannot write %s\n", Argv[2]);
		return 1;
	}
	std::fprintf(Out, "kind\tmap\ttable\tnumber\tflags\tcodes\n");
	std::map<std::string, FCount> Counts;
	int Failures = 0;
	for (const FGameTextFile& File : GameTextFiles())
	{
		FCount& Count = Counts[KindName(File.Kind)];
		++Count.Files;
		const TResult<std::vector<FGameTextTable>> Tables = ReadGameText(Disc->Image(), *Index, *Executable, File);
		if (!Tables)
		{
			++Count.FilesFailed;
			std::printf("fail %s %d: %s\n", KindName(File.Kind), File.Map, Tables.Error().Message.c_str());
			continue;
		}
		for (const FGameTextTable& Table : *Tables)
		{
			for (std::size_t Number = 0; Number < Table.Messages.size(); ++Number)
			{
				const std::vector<uint8>& Codes = Table.Messages[Number].Codes;
				++Count.Messages;
				const std::string Text = MesTextOfCodes(Codes);
				bool bUnknown = Text.find("{x") != std::string::npos;
				for (std::size_t At = Text.find("{0"); At != std::string::npos && !bUnknown; At = Text.find("{0", At + 1))
				{
					bUnknown = At + 3 < Text.size() && Text[At + 3] == '}';
				}
				bool bCyrillic = false, bLatin = false, bKana = false, bNoPicture = false;
				const std::vector<FMesCode> Glyphs = MesGlyphsOfCodes(Codes);
				for (const FMesCode& Glyph : Glyphs)
				{
					bNoPicture = bNoPicture || !Font.Rows(Glyph).has_value();
					bCyrillic = bCyrillic || (Glyph.Lead == 0 && Glyph.Code >= NarrowFirst && Glyph.Code < NarrowEnd);
					bLatin = bLatin || (Glyph.Lead == 0 && Glyph.Code >= 0x20 && Glyph.Code <= 0x56 && Glyph.Code != 0x3A && Glyph.Code != 0x3B && Glyph.Code != 0x3C);
					bKana = bKana || (Glyph.Lead == 0 && Glyph.Code >= NarrowEnd && Glyph.Code < 0xFE) || (Glyph.Lead == 0xFE);
				}
				bUnknown = bUnknown || bNoPicture;
				Count.Empty += Glyphs.empty() ? 1 : 0;
				Count.Unknown += bUnknown ? 1 : 0;
				Count.Clean += bUnknown ? 0 : 1;
				Count.Cyrillic += bCyrillic ? 1 : 0;
				Count.Latin += !bCyrillic && bLatin ? 1 : 0;
				Count.Kana += bKana ? 1 : 0;
				std::string Flags = std::string(bUnknown ? "U" : "") + (bNoPicture ? "P" : "") + (bCyrillic ? "C" : "") + (!bCyrillic && bLatin ? "L" : "") + (bKana ? "K" : "");
				std::fprintf(Out, "%s\t%d\t%s\t%zu\t%s\t", KindName(File.Kind), File.Map, Table.Table.c_str(), Number + static_cast<std::size_t>(Table.First), Flags.c_str());
				for (const uint8 Code : Codes)
				{
					std::fprintf(Out, "%02x", Code);
				}
				std::fprintf(Out, "\n");
				if (bUnknown && Failures++ < 40)
				{
					std::printf("unknown %s %d %s #%zu: %s\n", KindName(File.Kind), File.Map, Table.Table.c_str(), Number, Text.substr(0, 160).c_str());
				}
			}
		}
	}
	std::fclose(Out);
	std::printf("kind\tfiles\tfailed\tmessages\tempty\tclean\tunknown\twith_narrow_letters\tlatin_only\tkana\n");
	for (const auto& [Kind, Count] : Counts)
	{
		std::printf("%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n", Kind.c_str(), Count.Files, Count.FilesFailed, Count.Messages, Count.Empty, Count.Clean, Count.Unknown,
			Count.Cyrillic, Count.Latin, Count.Kana);
	}
	return 0;
}
