// The mod folder's start-up check, for its batch file (a batch cannot look inside a disc image): the disc images in
// <root>\Games found by their content (SurveyDiscs, as the game finds them, lang=auto), the HD pack's folder, and the
// batch's own lines, all said in Russian or English (the shell's rule, ChooseLanguage) through the console's
// wide-character API (any code page), or as UTF-8 when the output is redirected to a file.
//
//   xeno_check check <root> [ui=ru|en] [...]   what the game will play; exit code 0 Russian, 1 English, 2 nothing playable
//   xeno_check say <line> [arg...] [game=ru|en] [ui=ru|en] [...]
//                                    one of the batch's lines: firstrun, firstrun_failed <log>, nopack, starting,
//                                    failed <exit code> <log>; game= is what check said (exit code 0: ru)
//   xeno_check image <file>          (for checks) how one image is taken, its boot program's code hash
// Arguments it does not know (the game's own, which the batch passes on with %*) are left alone.
#include "xeno_discs.h"
#include "xeno_translation.h"

#include "Media/CdImage.h"
#include "Media/Iso9660.h"

#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace
{
	/** What the batch is told: 0 the Russian game, 1 the English, 2 nothing to play, 3 the tool used wrongly. */
	constexpr int Russian = 0;
	constexpr int English = 1;
	constexpr int Nothing = 2;
	constexpr int Misused = 3;

	/** A line in both languages, side by side where it is said (tools/ui_text_check.py checks each Russian has its English). */
	struct FLine
	{
		const char* Ru;
		const char* En;
	};

	/** The lines' language (ChooseLanguage). */
	bool InEnglish = false;

	std::string L(const FLine& Line)
	{
		return InEnglish ? Line.En : Line.Ru;
	}

	/** The images the user plays with, measured 13.11.2026: what to tell someone looking for the right one. */
	constexpr FLine RussianDiscFacts = {"образ этой игры, с которым всё проверено: xenogears_rus_xz.BIN (+ .CUE), 718 792 368 байт,\n"
										"     SHA-1 23819e084229d04aad4bf5ce6d18c9935f04e202",
										"the image everything was checked with: xenogears_rus_xz.BIN (+ .CUE), 718,792,368 bytes,\n"
										"     SHA-1 23819e084229d04aad4bf5ce6d18c9935f04e202"};
	constexpr FLine UsaDiscFacts = {"образ, с которым всё проверено: Xenogears (USA) (Disc 1).bin (+ .cue), 718 738 272 байт,\n"
									"     SHA-1 12db8ccb93516c391630f046a143762337cc21f4",
									"the image everything was checked with: Xenogears (USA) (Disc 1).bin (+ .cue), 718,738,272 bytes,\n"
									"     SHA-1 12db8ccb93516c391630f046a143762337cc21f4"};
	constexpr FLine RussianDisc2Facts = {"образ, с которым всё проверено: xenogears_rus_xz2.BIN (+ .CUE), 688 726 752 байт,\n"
										 "     SHA-1 40f9437e4201d3dbc3402f126277461051ec9596",
										 "the image everything was checked with: xenogears_rus_xz2.BIN (+ .CUE), 688,726,752 bytes,\n"
										 "     SHA-1 40f9437e4201d3dbc3402f126277461051ec9596"};

	/** Text to the console: wide characters when it is one, UTF-8 bytes when the output goes to a file or a pipe. */
	void Say(std::string_view Utf8)
	{
		const HANDLE Out = GetStdHandle(STD_OUTPUT_HANDLE);
		DWORD Mode = 0;
		if (GetConsoleMode(Out, &Mode))
		{
			const int Length = MultiByteToWideChar(CP_UTF8, 0, Utf8.data(), static_cast<int>(Utf8.size()), nullptr, 0);
			std::wstring Wide(static_cast<std::size_t>(Length), L'\0');
			MultiByteToWideChar(CP_UTF8, 0, Utf8.data(), static_cast<int>(Utf8.size()), Wide.data(), Length);
			DWORD Written = 0;
			WriteConsoleW(Out, Wide.data(), static_cast<DWORD>(Wide.size()), &Written, nullptr);
		}
		else
		{
			DWORD Written = 0;
			WriteFile(Out, Utf8.data(), static_cast<DWORD>(Utf8.size()), &Written, nullptr);
		}
	}

	void SayLine(const std::string& Utf8 = {})
	{
		Say(Utf8 + "\r\n");
	}

	std::string Text(const std::filesystem::path& Path)
	{
		const std::u8string Name = Path.u8string();
		return std::string(Name.begin(), Name.end());
	}

	/** A command-line argument (wide, as Windows gives it) as a path. */
	std::filesystem::path PathArgument(const wchar_t* Argument)
	{
		return std::filesystem::path(Argument);
	}

	std::string Utf8Of(const wchar_t* Wide)
	{
		const int Length = WideCharToMultiByte(CP_UTF8, 0, Wide, -1, nullptr, 0, nullptr, nullptr);
		std::string Out(static_cast<std::size_t>(std::max(Length - 1, 0)), '\0');
		WideCharToMultiByte(CP_UTF8, 0, Wide, -1, Out.data(), Length, nullptr, nullptr);
		return Out;
	}

	bool StartsWith(const std::string& Text, std::string_view Prefix)
	{
		return Text.rfind(Prefix, 0) == 0;
	}

	/** The value of <key>=<value> among the arguments after the command's first (the last one given), "" if none. */
	std::string Option(int Count, wchar_t** Arguments, std::string_view Key)
	{
		std::string Found;
		for (int Index = 3; Index < Count; ++Index)
		{
			const std::string Argument = Utf8Of(Arguments[Index]);
			if (StartsWith(Argument, Key))
			{
				Found = Argument.substr(Key.size());
			}
		}
		return Found;
	}

	/** The shell's rule (main.gd _choose_ui) without the player's choice kept by the game: ui=ru|en; else Russian where the
	 *  Russian translation's disc 1 is played or Windows' own language (GetUserDefaultUILanguage) is Russian; else English. */
	void ChooseLanguage(int Count, wchar_t** Arguments, bool RussianGame)
	{
		const std::string Ui = Option(Count, Arguments, "ui=");
		const bool WindowsRussian = PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_RUSSIAN;
		InEnglish = Ui == "en" || (Ui != "ru" && !RussianGame && !WindowsRussian);
	}

	/** Why an image is not played (Weltall's notes and the bridge's, FGameLibrary / SurveyDiscs). */
	std::string WhyNot(const std::string& Note)
	{
		if (StartsWith(Note, "A PSP eboot"))
			return L({"образ PSP (PBP): игра его не читает — нужен BIN/CUE.", "a PSP image (PBP): the game does not read it, BIN/CUE is needed."});
		if (StartsWith(Note, "An ECM-packed image"))
			return L({"образ сжат ECM: сначала распакуйте его в .bin (программа unecm).", "an ECM-packed image: unpack it into a .bin first (the unecm program)."});
		if (StartsWith(Note, "An archive"))
			return L({"это архив: достаньте из него образ диска (BIN и CUE) в эту же папку.", "an archive: take the disc image (BIN and CUE) out of it into this folder."});
		if (StartsWith(Note, "An Alcohol 120% image"))
			return L({"образ Alcohol 120% (MDS/MDF): игра его не читает — переведите в BIN/CUE.", "an Alcohol 120% image (MDS/MDF): the game does not read it, convert it to BIN/CUE."});
		if (StartsWith(Note, "A Nero image"))
			return L({"образ Nero (NRG): игра его не читает — переведите в BIN/CUE.", "a Nero image (NRG): the game does not read it, convert it to BIN/CUE."});
		if (StartsWith(Note, "A DiscJuggler image"))
			return L({"образ DiscJuggler (CDI): игра его не читает — переведите в BIN/CUE.", "a DiscJuggler image (CDI): the game does not read it, convert it to BIN/CUE."});
		if (StartsWith(Note, "The file it names, "))
		{
			const std::string Rest = Note.substr(std::string_view("The file it names, ").size());
			const std::size_t Comma = Rest.find(", is not beside it");
			return L({"в этом .cue указан файл «", "this .cue names the file \""}) + Rest.substr(0, Comma)
				+ L({"», а рядом его нет: положите .bin в ту же папку.", "\", which is not beside it: put the .bin into the same folder."});
		}
		if (StartsWith(Note, "Cannot be read"))
			return L({"файл не читается (", "the file cannot be read ("}) + Note + ").";
		if (StartsWith(Note, "Not a CD's image"))
			return L({"это не образ компакт-диска, который игра умеет читать.", "not an image of a CD the game can read."});
		if (StartsWith(Note, "Not a PlayStation disc"))
			return L({"это не диск PlayStation.", "not a PlayStation disc."});
		if (StartsWith(Note, "A USA disc of Xenogears, but changed"))
			return L({"это американский диск Xenogears, но изменённый (патч, или ошибка при снятии образа).",
					  "an American disc of Xenogears, but changed (a patch, or an error when the image was made)."});
		if (StartsWith(Note, "A Japanese disc"))
			return L({"японский диск: нужен американский (USA) или русский перевод.", "a Japanese disc: the American (USA) one or the Russian translation is needed."});
		if (StartsWith(Note, "Not a disc of Xenogears' USA release"))
			return L({"это не Xenogears (USA) и не русский перевод (", "neither Xenogears (USA) nor the Russian translation ("}) + Note + ").";
		if (Note.find("ends too soon") != std::string::npos || StartsWith(Note, "Ends too soon"))
			return L({"образ обрывается раньше конца диска: он недокопирован или снят с ошибкой.",
					  "the image ends before the disc does: it was not copied whole, or made with an error."});
		if (StartsWith(Note, "Not played: a patched copy"))
			return L({"не нужен: в папке есть его переведённая копия, играет она.", "not needed: its translated copy is in the folder, that one is played."});
		if (Note.find("the game plays the USA release") != std::string::npos)
			return L({"этот выпуск игры не подходит: нужен американский (USA) или русский перевод.",
					  "this release of the game will not do: the American (USA) one or the Russian translation is needed."});
		return Note;
	}

	int Check(const std::filesystem::path& Root, int Count, wchar_t** Arguments)
	{
		const std::filesystem::path Games = Root / "Games";
		std::error_code Error;
		if (!std::filesystem::is_directory(Games, Error))
		{
			std::filesystem::create_directories(Games, Error);
		}
		const Xeno::FDiscSurvey Survey = Xeno::SurveyDiscs(Games);
		const std::filesystem::path Russian1 = Survey.First(Xeno::EDiscKind::RussianDisc1);
		const std::filesystem::path Usa1 = Survey.First(Xeno::EDiscKind::UsaDisc1);
		ChooseLanguage(Count, Arguments, !Russian1.empty());
		int Verdict = Nothing;
		SayLine(L({"Xenogears HD — проверка перед запуском", "Xenogears HD: pre-launch check"}));
		SayLine(L({"Папка с образами дисков: ", "The disc images folder: "}) + Text(Games));
		SayLine();
		if (!Russian1.empty())
		{
			SayLine(L({"Найден диск 1 русского перевода: ", "Found disc 1 of the Russian translation: "}) + Text(Russian1.filename()));
			SayLine(L({"Игра будет на русском языке.", "The game's text will be Russian."}));
			Verdict = Russian;
		}
		else if (!Usa1.empty())
		{
			SayLine(L({"Найден английский диск 1 (Xenogears USA): ", "Found the English disc 1 (Xenogears USA): "}) + Text(Usa1.filename()));
			SayLine(L({"Русского перевода в папке нет, поэтому игра будет НА АНГЛИЙСКОМ.", "No Russian translation in the folder, so the game will be IN ENGLISH."}));
			SayLine(L({"Для русского текста положите в ту же папку образ диска 1 русского перевода Xenogears",
					   "For the Russian text, put the image of disc 1 of Xenogears' Russian translation into the same folder"}));
			SayLine("  (" + L(RussianDiscFacts) + ").");
			Verdict = English;
		}
		// Disc 2 of the kind played is taken by the game itself once the story reaches it (the bridge's disc drive, the same survey).
		const Xeno::EDiscKind Second = Verdict == Russian ? Xeno::EDiscKind::RussianDisc2 : Xeno::EDiscKind::UsaDisc2;
		if (Verdict != Nothing)
		{
			const std::filesystem::path Disc2 = Survey.First(Second);
			if (!Disc2.empty())
			{
				SayLine((Verdict == Russian ? L({"Найден диск 2 русского перевода: ", "Found disc 2 of the Russian translation: "})
											: L({"Найден диск 2 (USA): ", "Found disc 2 (USA): "})) + Text(Disc2.filename())
					+ L({" — игра возьмёт его сама в конце первого диска.", ": the game takes it by itself at the end of disc 1."}));
			}
			else
			{
				SayLine(Verdict == Russian
					? L({"Диска 2 русского перевода в папке нет. Он нужен только в конце первого диска:",
						 "Disc 2 of the Russian translation is not in the folder. It is needed only at the end of disc 1:"})
					: L({"Диска 2 (USA) в папке нет. Он нужен только в конце первого диска:", "Disc 2 (USA) is not in the folder. It is needed only at the end of disc 1:"}));
				SayLine(L({"  положите его сюда же, можно и во время игры, когда она попросит «ВСТАВЬ ДИСК 2».",
						   "  put it here too, even while playing, once the game asks for disc 2."}));
				if (Verdict == Russian)
				{
					SayLine("  (" + L(RussianDisc2Facts) + ").");
				}
			}
		}
		for (const Xeno::FFoundDisc& Disc : Survey.Discs)
		{
			if ((Disc.Kind == Xeno::EDiscKind::UsaDisc2 || Disc.Kind == Xeno::EDiscKind::RussianDisc2) && Disc.Kind != Second)
			{
				SayLine(L({"Не подойдёт: ", "Not usable: "}) + Text(Disc.File.filename()) + L({" — диск 2 другого выпуска", ": disc 2 of another release"})
					+ (Verdict == Russian ? L({": к русскому диску 1 нужен диск 2 русского перевода.", "; the Russian disc 1 needs disc 2 of the Russian translation."})
						: Verdict == English ? L({": к диску 1 USA нужен диск 2 USA.", "; the USA disc 1 needs the USA disc 2."}) : std::string(".")));
			}
			else if (Disc.Kind == Xeno::EDiscKind::Other)
			{
				SayLine(L({"Не подходит: ", "Not usable: "}) + Text(Disc.File.filename()) + " — " + WhyNot(Disc.Note));
			}
		}
		if (Verdict == Nothing)
		{
			SayLine(L({"ОБРАЗ ДИСКА ИГРЫ НЕ НАЙДЕН.", "NO DISC IMAGE OF THE GAME FOUND."}));
			SayLine();
			SayLine(L({"Образов дисков в этой папке нет (их нельзя раздавать): положите образ со своего диска сюда:",
					   "This folder holds no disc images (they may not be given away): put the image of your own disc here:"}));
			SayLine("  " + Text(Games));
			SayLine();
			SayLine(L({"Нужен один из двух (имя файла может быть любым, игра узнаёт диск по содержимому):",
					   "One of these two is needed (any file name: the game knows a disc by its content):"}));
			SayLine(L({"  1) Xenogears, русский перевод, ДИСК 1 — игра будет на русском;", "  1) Xenogears, the Russian translation, DISC 1: the game in Russian;"}));
			SayLine("     " + L(RussianDiscFacts) + ".");
			SayLine(L({"  2) Xenogears (USA), ДИСК 1 (американский, Square EA, 1998) — игра будет на английском;",
					   "  2) Xenogears (USA), DISC 1 (American, Square EA, 1998): the game in English;"}));
			SayLine("     " + L(UsaDiscFacts) + ".");
			SayLine();
			SayLine(L({"Формат образа: BIN + CUE (оба файла рядом) или CHD. ISO/IMG тоже читаются, но ролики будут без звука.",
					   "The image's format: BIN + CUE (both files side by side) or CHD. ISO/IMG are read too, but the movies have no sound."}));
			SayLine(L({"Архивы (ZIP, 7Z, RAR), ECM, PBP, MDS/MDF, NRG, CDI игра не читает: распакуйте или переведите в BIN/CUE.",
					   "Archives (ZIP, 7Z, RAR), ECM, PBP, MDS/MDF, NRG, CDI the game does not read: unpack them or convert to BIN/CUE."}));
			SayLine(L({"Диск 2 нужен только в конце первого диска: его можно положить сюда же сразу или потом (игра найдёт сама).",
					   "Disc 2 is needed only at the end of disc 1: put it here now or later (the game finds it by itself)."}));
		}
		else
		{
			const std::filesystem::path Pack = Root / "pack";
			if (!std::filesystem::is_directory(Pack, Error) || std::filesystem::directory_iterator(Pack, Error) == std::filesystem::directory_iterator())
			{
				SayLine();
				SayLine(L({"Папки pack с HD-текстурами нет (или она пуста): игра пойдёт с оригинальной графикой PlayStation.",
						   "No pack folder with the HD textures (or it is empty): the game runs with the original PlayStation graphics."}));
			}
		}
		return Verdict;
	}

	int SayLineOf(int Count, wchar_t** Arguments)
	{
		const std::string Line = Utf8Of(Arguments[2]);
		const std::string First = Count > 3 ? Utf8Of(Arguments[3]) : std::string();
		const std::string Second = Count > 4 ? Utf8Of(Arguments[4]) : std::string();
		ChooseLanguage(Count, Arguments, Option(Count, Arguments, "game=") == "ru");
		if (Line == "firstrun")
		{
			SayLine(L({"Первый запуск: игра готовится к работе (это делается один раз, около минуты)...",
					   "The first start: the game gets ready to run (once only, about a minute)..."}));
		}
		else if (Line == "firstrun_failed")
		{
			SayLine(L({"Не удалось подготовить игру к первому запуску. Подробности в файле:", "The game could not be made ready for its first start. Details in the file:"}));
			SayLine("  " + First);
		}
		else if (Line == "starting")
		{
			SayLine();
			SayLine(L({"Запускаю игру... Это окно закроется само, когда вы выйдете из игры.", "Starting the game... This window closes by itself once you quit the game."}));
		}
		else if (Line == "failed")
		{
			SayLine();
			SayLine(L({"Игра закрылась с ошибкой (код ", "The game closed with an error (code "}) + First + ").");
			SayLine(L({"Чаще всего причина — видеокарта: нужна видеокарта с поддержкой Vulkan (или DirectX 12)",
					   "Most often it is the graphics card: it has to support Vulkan (or DirectX 12)"}));
			SayLine(L({"и свежий драйвер к ней (NVIDIA, AMD или Intel, с сайта производителя).", "and have a recent driver (NVIDIA, AMD or Intel, from the maker's site)."}));
			SayLine(L({"Подробности в журнале игры:", "Details in the game's log:"}));
			SayLine("  " + Second);
		}
		else
		{
			return Misused;
		}
		return 0;
	}

	int DescribeImage(const std::filesystem::path& File)
	{
		const Xeno::FFoundDisc Found = Xeno::ClassifyImage(File);
		const char* Kinds[] = {"usa disc 1", "usa disc 2", "russian disc 1", "russian disc 2", "other"};
		std::string Code;
		if (auto Image = Weltall::FCdImage::Open(File))
		{
			if (auto Disc = Weltall::FIso9660::Open(std::move(*Image)))
			{
				Code = Xeno::BootCodeSha1(*Disc);
			}
		}
		SayLine(Text(File) + ": " + Kinds[static_cast<int>(Found.Kind)] + (Found.Note.empty() ? "" : " (" + Found.Note + ")") + "; boot code " + Code);
		return 0;
	}
}

int wmain(int Count, wchar_t** Arguments)
{
	if (Count >= 3 && std::wstring_view(Arguments[1]) == L"check")
	{
		return Check(PathArgument(Arguments[2]), Count, Arguments);
	}
	if (Count >= 3 && std::wstring_view(Arguments[1]) == L"say")
	{
		return SayLineOf(Count, Arguments);
	}
	if (Count >= 3 && std::wstring_view(Arguments[1]) == L"image")
	{
		return DescribeImage(PathArgument(Arguments[2]));
	}
	SayLine("xeno_check check <root> [ui=ru|en] | say <line> [args] [game=ru|en] [ui=ru|en] | image <file>");
	return Misused;
}
