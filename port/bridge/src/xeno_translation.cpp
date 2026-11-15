#include "xeno_translation.h"

#include "Field/FieldMap.h"
#include "Foundation/LittleEndian.h"
#include "Foundation/Sha1.h"
#include "Media/CdImage.h"
#include "Media/GameFileIndex.h"
#include "Media/Iso9660.h"
#include "Media/PsxExecutable.h"

#include <algorithm>
#include <cstdio>
#include <string_view>

using namespace Weltall;

namespace Xeno
{
	namespace
	{
		/**
		 * The Russian translation of disc 1 (the user's xenogears_rus_xz): its data is the USA release's with its own text,
		 * font and pictures in the same files, and its boot executable (XENOGEAR.EXE) is the USA's program but for its file
		 * index and 119 bytes of code of its own. Weltall's IdentifyDisc does not know it (the code differs), so the bridge
		 * knows it the way IdentifyExecutable knows a patched USA disc: the SHA-1 of the whole file with the file index and
		 * the boot notice's picture zeroed (DiscIdentification.cpp, CodeSha1), measured on the user's disc 13.11.2026.
		 */
		constexpr std::string_view RussianCodeSha1 = "03db102ee76d52aca3e4287de14cf96551e780a6";
		constexpr uint32 FileIndexAddress = 0x80010004;
		constexpr uint32 FileIndexEnd = 0x80018004;
		constexpr uint32 BootPictureAddress = 0x8004EABC;
		/**
		 * Its code that the core's reading of the data lacks: the kernel's glyph widths' routine (80034F98h, which the core
		 * reads as FMesFont::WidthUnits) jumps to code of its own at 800180FCh, which also takes the one-byte codes from
		 * First to End (not included) as narrow, its Cyrillic letters (the USA's kana there are wide): two
		 * "slti v1,a1,imm" at these addresses give First and End.
		 */
		constexpr uint32 RussianNarrowFirstAt = 0x80018104;
		constexpr uint32 RussianNarrowEndAt = 0x80018110;
		constexpr uint32 SltiV1A1 = 0x28A30000;
		/** The font sheet's first code (MesFontSheet: cell n is code 10h + n on the first page). */
		constexpr uint32 SheetFirstCode = 0x10;

		/** A field map's archive (FieldArchive.cpp): directory 4, file B8h + 2N; nine sections' sizes and offsets in its header. */
		constexpr int32 MapDirectory = 4;
		constexpr int32 FirstMapFile = 0xB8;
		constexpr std::size_t SectionSizesAt = 0x10C;
		constexpr std::size_t SectionOffsetsAt = 0x130;
		constexpr std::size_t Sections = 9;

		/** IdentifyExecutable's CodeSha1 of a boot executable's file: empty where it is not a program of the game's shape. */
		std::string CodeSha1(std::span<const uint8> File)
		{
			const TResult<FPsxExecutable> Parsed = FPsxExecutable::Parse(std::vector<uint8>(File.begin(), File.end()));
			if (!Parsed || !Parsed->Contains(FileIndexAddress, FileIndexEnd - FileIndexAddress) || !Parsed->Contains(BootPictureAddress, 4))
			{
				return {};
			}
			std::vector<uint8> Code(File.begin(), File.end());
			const uint32 Load = Parsed->LoadAddress();
			const auto Clear = [&Code, Load](uint32 From, uint32 To)
			{
				std::fill(Code.begin() + FPsxExecutable::HeaderSize + (From - Load), Code.begin() + FPsxExecutable::HeaderSize + (To - Load), uint8{0});
			};
			Clear(FileIndexAddress, FileIndexEnd);
			Clear(BootPictureAddress, Load + static_cast<uint32>(Parsed->Body().size()));
			return FSha1::ToHex(FSha1::Hash(Code));
		}
	}

	std::string BootCodeSha1(const FIso9660& Disc)
	{
		const TResult<std::string> BootPath = FindBootExecutable(Disc);
		const TResult<std::vector<uint8>> File = BootPath ? Disc.ReadFile(*BootPath) : TResult<std::vector<uint8>>(MakeError("no boot program"));
		if (!File)
		{
			return {};
		}
		const std::string Code = CodeSha1(*File);
		return Code.empty() ? "file " + FSha1::ToHex(FSha1::Hash(*File)) : Code;
	}

	TResult<FTranslation> RecognizeTranslation(const FIso9660& Disc, const FPsxExecutable& Executable)
	{
		const TResult<std::string> BootPath = FindBootExecutable(Disc);
		if (!BootPath)
		{
			return BootPath.Error();
		}
		const TResult<std::vector<uint8>> File = Disc.ReadFile(*BootPath);
		if (!File)
		{
			return File.Error();
		}
		const std::string Code = CodeSha1(*File);
		if (Code != RussianCodeSha1)
		{
			return MakeError("not the Russian translation's disc 1 (" + *BootPath + ", code " + Code + ")");
		}
		FTranslation Translation;
		Translation.Language = "ru";
		Translation.Identity = FDiscIdentity{EDiscRelease::UsaDisc1, 1, "Xenogears (Russian translation) Disc 1", true, false, false};
		const uint32 First = Executable.ReadU32(RussianNarrowFirstAt);
		const uint32 End = Executable.ReadU32(RussianNarrowEndAt);
		if ((First & 0xFFFF0000u) != SltiV1A1 || (End & 0xFFFF0000u) != SltiV1A1)
		{
			return MakeError("the Russian program's narrow letters are not where its code was read");
		}
		Translation.NarrowFirst = First & 0xFFFFu;
		Translation.NarrowEnd = End & 0xFFFFu;
		// Its widths as a font sheet without a picture (Docs/Modding.md, "The font": a cell's width 8 = narrow).
		std::string Table = "code\tcell\twidth\n";
		for (uint32 Glyph = Translation.NarrowFirst; Glyph < Translation.NarrowEnd; ++Glyph)
		{
			char Line[32];
			std::snprintf(Line, sizeof(Line), "%02X\t%u\t8\n", Glyph, Glyph - SheetFirstCode);
			Table += Line;
		}
		std::string Problems;
		TResult<std::shared_ptr<const FMesFontSheet>> Sheet = FMesFontSheet::Read(Table, nullptr, [&Problems](const std::string& Problem) { Problems += Problem + "; "; });
		if (!Sheet)
		{
			return Sheet.Error();
		}
		if (!Problems.empty())
		{
			return MakeError("the Russian widths' sheet: " + Problems);
		}
		Translation.Widths = std::move(*Sheet);
		return Translation;
	}

	std::vector<FModFile> MendedMapArchives(const FCdImage& Image, const FGameFileIndex& Index, int& Mended)
	{
		std::vector<FModFile> Files;
		Mended = 0;
		for (int32 Map = 0; Map < FieldMapCount; ++Map)
		{
			const FIndexRecord* Record = Index.Find(MapDirectory, FirstMapFile + 2 * Map);
			if (Record == nullptr || !Record->IsFile())
			{
				continue;
			}
			TResult<std::vector<uint8>> Sectors = ReadFileSectors(Image, *Record);
			if (!Sectors || Sectors->size() < SectionOffsetsAt + Sections * 4)
			{
				continue;
			}
			std::vector<uint8>& Bytes = *Sectors;
			bool bChanged = false;
			for (std::size_t Section = 0; Section < Sections; ++Section)
			{
				const uint32 Size = LittleEndian::ReadU32(Bytes, SectionSizesAt + Section * 4);
				const uint32 Offset = LittleEndian::ReadU32(Bytes, SectionOffsetsAt + Section * 4);
				if (Offset + 4 > Bytes.size())
				{
					continue;
				}
				const uint32 Holds = LittleEndian::ReadU32(Bytes, Offset);
				if (Size > Holds)
				{
					LittleEndian::WriteU32(Bytes, SectionSizesAt + Section * 4, Holds);
					bChanged = true;
				}
			}
			if (bChanged)
			{
				FModFile File;
				File.Record = static_cast<int32>(Record - Index.Records().data());
				File.Bytes = std::make_shared<const std::vector<uint8>>(std::move(Bytes));
				Files.push_back(std::move(File));
				++Mended;
			}
		}
		return Files;
	}
}
