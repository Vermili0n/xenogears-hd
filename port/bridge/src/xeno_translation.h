// A translation's disc the core does not know by itself (the Russian translation of disc 1): how the bridge recognizes it
// and what of its program the core's reading of its data needs. Weltall headers here: only the bridge's .cpp files include it.
#pragma once

#include "Foundation/Result.h"
#include "Media/DiscIdentification.h"
#include "Media/DiscModFiles.h"
#include "Text/MesFontSheet.h"

#include <memory>
#include <string>
#include <vector>

namespace Weltall
{
	class FCdImage;
	class FGameFileIndex;
	class FIso9660;
	class FPsxExecutable;
}

namespace Xeno
{
	/** What a translation's disc plays with. */
	struct FTranslation
	{
		/** "ru". */
		std::string Language;
		/** Who it is to the core: the USA release's disc 1, patched (its own file index; every table where the USA's program has it). */
		Weltall::FDiscIdentity Identity;
		/** Its program's glyph widths as a font sheet without a picture (the glyphs stay the disc's own). */
		std::shared_ptr<const Weltall::FMesFontSheet> Widths;
		/** The one-byte codes its program advances as narrow besides the font's own: [NarrowFirst, NarrowEnd). */
		uint32_t NarrowFirst = 0;
		uint32_t NarrowEnd = 0;
	};

	/**
	 * The disc's boot program hashed as RecognizeTranslation hashes it (IdentifyExecutable's CodeSha1: SHA-1 of the file
	 * with the file index and the boot notice's picture zeroed); "file " and the whole file's SHA-1 where the program is
	 * not of that shape; empty when it cannot be read.
	 */
	std::string BootCodeSha1(const Weltall::FIso9660& Disc);

	/** The translation Disc (its boot executable Executable) holds; an error for any other disc. */
	Weltall::TResult<FTranslation> RecognizeTranslation(const Weltall::FIso9660& Disc, const Weltall::FPsxExecutable& Executable);

	/**
	 * The field maps' archives (directory 4, file B8h + 2N) whose header gives a section more bytes than its packed stream
	 * holds, each as a file in memory with the header giving the stream's own size; Mended counts them. The console's
	 * program trusts its data and reads what the stream holds; the core's reader (UnpackLzssPrefix) refuses more bytes
	 * than the stream's, and so would not enter the map at all. The Russian translation's tool wrote 77 maps' message
	 * sections one byte longer than their streams; no USA map has such a section.
	 */
	std::vector<Weltall::FModFile> MendedMapArchives(const Weltall::FCdImage& Image, const Weltall::FGameFileIndex& Index, int& Mended);
}
