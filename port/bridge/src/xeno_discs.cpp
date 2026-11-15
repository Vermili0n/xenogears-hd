#include "xeno_discs.h"

#include "xeno_translation.h"

#include "Media/CdImage.h"
#include "Media/DiscIdentification.h"
#include "Media/GameFileIndex.h"
#include "Media/GameLibrary.h"
#include "Media/Iso9660.h"
#include "Media/PsxExecutable.h"

#include <algorithm>
#include <cctype>
#include <string_view>

using namespace Weltall;

namespace Xeno
{
	namespace
	{
		/**
		 * The Russian translation's disc 2 (the user's xenogears_rus_xz2), its boot program's code hashed as
		 * RecognizeTranslation hashes disc 1's (BootCodeSha1), measured on the user's copy 13.11.2026.
		 */
		constexpr std::string_view RussianDisc2CodeSha1 = "fc330b2c67889e9c22311c4645d5b2e589cda7b0";

		std::string LowerExtension(const std::filesystem::path& Path)
		{
			std::string Extension = Path.extension().string();
			std::transform(Extension.begin(), Extension.end(), Extension.begin(), [](char C) { return static_cast<char>(std::tolower(static_cast<unsigned char>(C))); });
			return Extension;
		}

		bool IsDiscImage(const std::filesystem::path& Path)
		{
			const std::string Extension = LowerExtension(Path);
			return Extension == ".cue" || Extension == ".bin" || Extension == ".iso" || Extension == ".img" || Extension == ".chd";
		}

		/**
		 * Whether the image holds every file of the game's disc, as FGameLibrary::Scan checks the discs it knows
		 * (GameLibrary.cpp, HoldsEveryFile): one still being copied, or a rip cut short, ends early.
		 */
		bool HoldsEveryFile(const FIso9660& Disc, const FGameFileIndex& Index)
		{
			uint64 End = 0;
			for (const FIsoEntry& Entry : Disc.Entries())
			{
				End = std::max(End, static_cast<uint64>(Entry.Lba) + Entry.SectorCount());
			}
			for (const FIndexRecord& Record : Index.Records())
			{
				if (Record.IsFile())
				{
					End = std::max(End, Record.Lba + (static_cast<uint64>(Record.Size) + CdSector::Form1DataSize - 1) / CdSector::Form1DataSize);
				}
			}
			if (End > Disc.Image().SectorCount())
			{
				return false;
			}
			if (!Disc.Image().IsRaw() || End == 0)
			{
				return true;
			}
			const TResult<FCdSectorHeader> Last = Disc.Image().ReadHeader(static_cast<uint32>(End - 1));
			return Last && Last->Mode != 0;
		}

		/** An image Weltall's identification does not know: the Russian translation's discs, or why it is not played. */
		FFoundDisc ClassifyUnknown(const std::filesystem::path& File, const FIso9660& Disc)
		{
			FFoundDisc Found{File, EDiscKind::Other, {}};
			const TResult<std::string> Boot = FindBootExecutable(Disc);
			if (!Boot)
			{
				Found.Note = "Not a PlayStation disc.";
				return Found;
			}
			const TResult<FPsxExecutable> Executable = ReadBootExecutable(Disc);
			if (!Executable)
			{
				Found.Note = "Its boot program (" + *Boot + ") cannot be read.";
				return Found;
			}
			if (const TResult<FTranslation> Translation = RecognizeTranslation(Disc, *Executable))
			{
				const TResult<FGameFileIndex> Index = FGameFileIndex::Read(*Executable);
				if (!Index || !HoldsEveryFile(Disc, *Index))
				{
					Found.Note = "The Russian translation's disc 1, but it ends too soon: still being copied, or a rip cut short.";
					return Found;
				}
				Found.Kind = EDiscKind::RussianDisc1;
				return Found;
			}
			const std::string Code = BootCodeSha1(Disc);
			if (Code == RussianDisc2CodeSha1)
			{
				// Its movies are read once the story reaches it, perhaps while the image is still being copied in: whole first.
				const TResult<FGameFileIndex> Index = FGameFileIndex::Read(*Executable);
				if (!Index || !HoldsEveryFile(Disc, *Index))
				{
					Found.Note = "The Russian translation's disc 2, but it ends too soon: still being copied, or a rip cut short.";
					return Found;
				}
				Found.Kind = EDiscKind::RussianDisc2;
				return Found;
			}
			if (*Boot == "SLUS_006.64" || *Boot == "SLUS_006.69")
			{
				Found.Note = "A USA disc of Xenogears, but changed (patched, or damaged in the rip).";
			}
			else if (*Boot == "SLPS_011.60" || *Boot == "SLPS_011.61")
			{
				Found.Note = "A Japanese disc of Xenogears: the game plays the USA release.";
			}
			else
			{
				Found.Note = "Not a disc of Xenogears' USA release (its program is " + *Boot + (Code.empty() ? "" : ", code " + Code) + ").";
			}
			return Found;
		}

		EDiscKind KindOfRelease(EDiscRelease Release)
		{
			return Release == EDiscRelease::UsaDisc1 ? EDiscKind::UsaDisc1 : Release == EDiscRelease::UsaDisc2 ? EDiscKind::UsaDisc2 : EDiscKind::Other;
		}
	}

	std::filesystem::path FDiscSurvey::First(EDiscKind Kind) const
	{
		for (const FFoundDisc& Disc : Discs)
		{
			if (Disc.Kind == Kind)
			{
				return Disc.File;
			}
		}
		return {};
	}

	FFoundDisc ClassifyImage(const std::filesystem::path& File)
	{
		FFoundDisc Found{File, EDiscKind::Other, {}};
		if (!IsDiscImage(File))
		{
			Found.Note = "Not a disc image the game reads (BIN/CUE, CHD, ISO, IMG).";
			return Found;
		}
		auto Image = FCdImage::Open(File);
		if (!Image)
		{
			Found.Note = "Cannot be read: " + Image.Error().Message + ".";
			return Found;
		}
		auto Disc = FIso9660::Open(std::move(*Image));
		if (!Disc)
		{
			Found.Note = "Not a CD's image the game can read.";
			return Found;
		}
		if (const TResult<FDiscIdentity> Identity = IdentifyDisc(*Disc))
		{
			Found.Kind = KindOfRelease(Identity->Release);
			if (Found.Kind == EDiscKind::Other)
			{
				Found.Note = std::string(Identity->Title) + ": the game plays the USA release.";
			}
			return Found;
		}
		return ClassifyUnknown(File, *Disc);
	}

	FDiscSurvey SurveyDiscs(const std::filesystem::path& Folder)
	{
		FDiscSurvey Survey;
		const FGameLibrary Library = FGameLibrary::Scan(Folder);
		for (const EDiscRelease Release : Library.Releases())
		{
			FFoundDisc Found{Library.FileOf(Release), KindOfRelease(Release), {}};
			if (Found.Kind == EDiscKind::Other)
			{
				Found.Note = std::string(DiscReleaseId(Release)) + ": the game plays the USA release.";
			}
			Survey.Discs.push_back(std::move(Found));
		}
		for (const FLibraryNote& Note : Library.Notes())
		{
			if (Note.bPlays)
			{
				// A disc the library keeps after all (a patched copy, an image without the movies' sound): listed above.
				continue;
			}
			// What the library does not know may be the Russian translation's: looked at again by its own rule.
			if (IsDiscImage(Note.File) &&
				(Note.Text.rfind("Not a disc of Xenogears' USA release", 0) == 0 || Note.Text.rfind("A USA disc of Xenogears, but changed", 0) == 0))
			{
				auto Image = FCdImage::Open(Note.File);
				auto Disc = Image ? FIso9660::Open(std::move(*Image)) : TResult<FIso9660>(MakeError("unreadable"));
				if (Disc)
				{
					Survey.Discs.push_back(ClassifyUnknown(Note.File, *Disc));
					continue;
				}
			}
			Survey.Discs.push_back({Note.File, EDiscKind::Other, Note.Text});
		}
		return Survey;
	}
}
