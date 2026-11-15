// The player's disc images in a folder, found by their content (not their names): which of them the game plays, and
// why the others are not played. Weltall headers here: only the bridge's .cpp files include it.
#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace Xeno
{
	/** What a disc image holds, as the bridge plays it. */
	enum class EDiscKind
	{
		/** Xenogears' USA release, disc 1 (or a patched copy Weltall knows, FGameLibrary): the English game. */
		UsaDisc1,
		/** The USA release's disc 2: its movies, once the story reaches it (the session's disc drive takes it then). */
		UsaDisc2,
		/** The Russian translation's disc 1 (RecognizeTranslation): the Russian game, its sound its own. */
		RussianDisc1,
		/** The Russian translation's disc 2 (the boot program's code measured on the user's copy): its movies, as the USA's. */
		RussianDisc2,
		/** Anything else: Note says what and why it is not played. */
		Other,
	};

	struct FFoundDisc
	{
		std::filesystem::path File;
		EDiscKind Kind = EDiscKind::Other;
		/** For Other: why it is not played, Weltall's words (FGameLibrary's notes) or the bridge's. */
		std::string Note;
	};

	struct FDiscSurvey
	{
		/** Every image found (a .cue stands for the files it names), in the order found. */
		std::vector<FFoundDisc> Discs;

		/** The first image of that kind, or an empty path. */
		std::filesystem::path First(EDiscKind Kind) const;
	};

	/**
	 * Every disc image in Folder and its subfolders as Weltall's library scans them (FGameLibrary::Scan: .cue sheets,
	 * .chd, and .bin/.iso/.img no sheet names; a disc recognized by its boot program's hash, whatever the file is
	 * called; images cut short, of other games or releases, or of kinds the core does not read, noted), and among the
	 * images it does not know, the Russian translation's discs (RecognizeTranslation's rule: the boot program's code).
	 */
	FDiscSurvey SurveyDiscs(const std::filesystem::path& Folder);

	/** One image (a .cue, .chd, .bin, .iso or .img) by itself, as SurveyDiscs would take it. */
	FFoundDisc ClassifyImage(const std::filesystem::path& File);
}
