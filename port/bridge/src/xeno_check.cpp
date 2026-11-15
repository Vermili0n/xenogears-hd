// The mod folder's start-up check, for its batch file (a batch cannot look inside a disc image): the disc images in
// <root>\Games found by their content (SurveyDiscs, as the game finds them, lang=auto), the HD pack's folder, and the
// batch's own lines, all said in Russian through the console's wide-character API (any code page), or as UTF-8 when
// the output is redirected to a file.
//
//   xeno_check check <root>          what the game will play; exit code 0 Russian, 1 English, 2 nothing playable
//   xeno_check say <line> [arg...]   one of the batch's lines: firstrun, firstrun_failed <log>, nopack, starting,
//                                    failed <exit code> <log>
//   xeno_check image <file>          (for checks) how one image is taken, its boot program's code hash
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

	/** The images the user plays with, measured 13.11.2026: what to tell someone looking for the right one. */
	constexpr const char* RussianDiscFacts = "образ этой игры, с которым всё проверено: xenogears_rus_xz.BIN (+ .CUE), 718 792 368 байт,\n"
											 "     SHA-1 23819e084229d04aad4bf5ce6d18c9935f04e202";
	constexpr const char* UsaDiscFacts = "образ, с которым всё проверено: Xenogears (USA) (Disc 1).bin (+ .cue), 718 738 272 байт,\n"
										 "     SHA-1 12db8ccb93516c391630f046a143762337cc21f4";
	constexpr const char* RussianDisc2Facts = "образ, с которым всё проверено: xenogears_rus_xz2.BIN (+ .CUE), 688 726 752 байт,\n"
											  "     SHA-1 40f9437e4201d3dbc3402f126277461051ec9596";

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

	/** Why an image is not played, in Russian (Weltall's notes and the bridge's, FGameLibrary / SurveyDiscs). */
	std::string WhyNot(const std::string& Note)
	{
		if (StartsWith(Note, "A PSP eboot"))
			return "образ PSP (PBP): игра его не читает — нужен BIN/CUE.";
		if (StartsWith(Note, "An ECM-packed image"))
			return "образ сжат ECM: сначала распакуйте его в .bin (программа unecm).";
		if (StartsWith(Note, "An archive"))
			return "это архив: достаньте из него образ диска (BIN и CUE) в эту же папку.";
		if (StartsWith(Note, "An Alcohol 120% image"))
			return "образ Alcohol 120% (MDS/MDF): игра его не читает — переведите в BIN/CUE.";
		if (StartsWith(Note, "A Nero image"))
			return "образ Nero (NRG): игра его не читает — переведите в BIN/CUE.";
		if (StartsWith(Note, "A DiscJuggler image"))
			return "образ DiscJuggler (CDI): игра его не читает — переведите в BIN/CUE.";
		if (StartsWith(Note, "The file it names, "))
		{
			const std::string Rest = Note.substr(std::string_view("The file it names, ").size());
			const std::size_t Comma = Rest.find(", is not beside it");
			return "в этом .cue указан файл «" + Rest.substr(0, Comma) + "», а рядом его нет: положите .bin в ту же папку.";
		}
		if (StartsWith(Note, "Cannot be read"))
			return "файл не читается (" + Note + ").";
		if (StartsWith(Note, "Not a CD's image"))
			return "это не образ компакт-диска, который игра умеет читать.";
		if (StartsWith(Note, "Not a PlayStation disc"))
			return "это не диск PlayStation.";
		if (StartsWith(Note, "A USA disc of Xenogears, but changed"))
			return "это американский диск Xenogears, но изменённый (патч, или ошибка при снятии образа).";
		if (StartsWith(Note, "A Japanese disc"))
			return "японский диск: нужен американский (USA) или русский перевод.";
		if (StartsWith(Note, "Not a disc of Xenogears' USA release"))
			return "это не Xenogears (USA) и не русский перевод (" + Note + ").";
		if (Note.find("ends too soon") != std::string::npos || StartsWith(Note, "Ends too soon"))
			return "образ обрывается раньше конца диска: он недокопирован или снят с ошибкой.";
		if (StartsWith(Note, "Not played: a patched copy"))
			return "не нужен: в папке есть его переведённая копия, играет она.";
		if (Note.find("the game plays the USA release") != std::string::npos)
			return "этот выпуск игры не подходит: нужен американский (USA) или русский перевод.";
		return Note;
	}

	int Check(const std::filesystem::path& Root)
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
		int Verdict = Nothing;
		SayLine("Xenogears HD — проверка перед запуском");
		SayLine("Папка с образами дисков: " + Text(Games));
		SayLine();
		if (!Russian1.empty())
		{
			SayLine("Найден диск 1 русского перевода: " + Text(Russian1.filename()));
			SayLine("Игра будет на русском языке.");
			Verdict = Russian;
		}
		else if (!Usa1.empty())
		{
			SayLine("Найден английский диск 1 (Xenogears USA): " + Text(Usa1.filename()));
			SayLine("Русского перевода в папке нет, поэтому игра будет НА АНГЛИЙСКОМ.");
			SayLine("Для русского текста положите в ту же папку образ диска 1 русского перевода Xenogears");
			SayLine(std::string("  (") + RussianDiscFacts + ").");
			Verdict = English;
		}
		// Disc 2 of the kind played is taken by the game itself once the story reaches it (the bridge's disc drive, the same survey).
		const Xeno::EDiscKind Second = Verdict == Russian ? Xeno::EDiscKind::RussianDisc2 : Xeno::EDiscKind::UsaDisc2;
		if (Verdict != Nothing)
		{
			const std::filesystem::path Disc2 = Survey.First(Second);
			if (!Disc2.empty())
			{
				SayLine("Найден диск 2" + std::string(Verdict == Russian ? " русского перевода" : " (USA)") + ": " + Text(Disc2.filename())
					+ " — игра возьмёт его сама в конце первого диска.");
			}
			else
			{
				SayLine("Диска 2" + std::string(Verdict == Russian ? " русского перевода" : " (USA)") + " в папке нет. Он нужен только в конце первого диска:");
				SayLine("  положите его сюда же, можно и во время игры, когда она попросит «ВСТАВЬ ДИСК 2».");
				if (Verdict == Russian)
				{
					SayLine(std::string("  (") + RussianDisc2Facts + ").");
				}
			}
		}
		for (const Xeno::FFoundDisc& Disc : Survey.Discs)
		{
			if ((Disc.Kind == Xeno::EDiscKind::UsaDisc2 || Disc.Kind == Xeno::EDiscKind::RussianDisc2) && Disc.Kind != Second)
			{
				SayLine("Не подойдёт: " + Text(Disc.File.filename()) + " — диск 2 другого выпуска" + std::string(Verdict == Russian
					? ": к русскому диску 1 нужен диск 2 русского перевода." : Verdict == English ? ": к диску 1 USA нужен диск 2 USA." : "."));
			}
			else if (Disc.Kind == Xeno::EDiscKind::Other)
			{
				SayLine("Не подходит: " + Text(Disc.File.filename()) + " — " + WhyNot(Disc.Note));
			}
		}
		if (Verdict == Nothing)
		{
			SayLine("ОБРАЗ ДИСКА ИГРЫ НЕ НАЙДЕН.");
			SayLine();
			SayLine("Образов дисков в этой папке нет (их нельзя раздавать): положите образ со своего диска сюда:");
			SayLine("  " + Text(Games));
			SayLine();
			SayLine("Нужен один из двух (имя файла может быть любым, игра узнаёт диск по содержимому):");
			SayLine("  1) Xenogears, русский перевод, ДИСК 1 — игра будет на русском;");
			SayLine(std::string("     ") + RussianDiscFacts + ".");
			SayLine("  2) Xenogears (USA), ДИСК 1 (американский, Square EA, 1998) — игра будет на английском;");
			SayLine(std::string("     ") + UsaDiscFacts + ".");
			SayLine();
			SayLine("Формат образа: BIN + CUE (оба файла рядом) или CHD. ISO/IMG тоже читаются, но ролики будут без звука.");
			SayLine("Архивы (ZIP, 7Z, RAR), ECM, PBP, MDS/MDF, NRG, CDI игра не читает: распакуйте или переведите в BIN/CUE.");
			SayLine("Диск 2 нужен только в конце первого диска: его можно положить сюда же сразу или потом (игра найдёт сама).");
		}
		else
		{
			const std::filesystem::path Pack = Root / "pack";
			if (!std::filesystem::is_directory(Pack, Error) || std::filesystem::directory_iterator(Pack, Error) == std::filesystem::directory_iterator())
			{
				SayLine();
				SayLine("Папки pack с HD-текстурами нет (или она пуста): игра пойдёт с оригинальной графикой PlayStation.");
			}
		}
		return Verdict;
	}

	int SayLineOf(int Count, wchar_t** Arguments)
	{
		const std::string Line = Utf8Of(Arguments[2]);
		const std::string First = Count > 3 ? Utf8Of(Arguments[3]) : std::string();
		const std::string Second = Count > 4 ? Utf8Of(Arguments[4]) : std::string();
		if (Line == "firstrun")
		{
			SayLine("Первый запуск: игра готовится к работе (это делается один раз, около минуты)...");
		}
		else if (Line == "firstrun_failed")
		{
			SayLine("Не удалось подготовить игру к первому запуску. Подробности в файле:");
			SayLine("  " + First);
		}
		else if (Line == "starting")
		{
			SayLine();
			SayLine("Запускаю игру... Это окно закроется само, когда вы выйдете из игры.");
		}
		else if (Line == "failed")
		{
			SayLine();
			SayLine("Игра закрылась с ошибкой (код " + First + ").");
			SayLine("Чаще всего причина — видеокарта: нужна видеокарта с поддержкой Vulkan (или DirectX 12)");
			SayLine("и свежий драйвер к ней (NVIDIA, AMD или Intel, с сайта производителя).");
			SayLine("Подробности в журнале игры:");
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
		return Check(PathArgument(Arguments[2]));
	}
	if (Count >= 3 && std::wstring_view(Arguments[1]) == L"say")
	{
		return SayLineOf(Count, Arguments);
	}
	if (Count >= 3 && std::wstring_view(Arguments[1]) == L"image")
	{
		return DescribeImage(PathArgument(Arguments[2]));
	}
	SayLine("xeno_check check <root> | say <line> [args] | image <file>");
	return Misused;
}
