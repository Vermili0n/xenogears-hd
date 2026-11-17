XENOGEARS HD — how to play
==========================

The HD pack. If the pack folder here is empty (the build was downloaded without the pack), download
XenogearsHD_pack.zip (9.8 GB) and unpack it into this folder, so that its pack folder lies next to Play.cmd:
   https://drive.google.com/file/d/1YDdp8Z_BPnRCgyAuMYRyH30flTckT9Gc/view?usp=sharing
If the link no longer works, the current one is on the project's page: https://github.com/Vermili0n/xenogears-hd
Without the pack the game runs with the original PlayStation graphics.

1. Put a disc image of the game into the Games folder (next to this file).
   No disc images are included: they may not be shared, you need an image of your own disc.
   One of these two will do (the file name can be anything — the game knows a disc by its contents):
     - Xenogears (USA), DISC 1 (the American release, Square EA, 1998) — the game will be in English.
       Checked with the image Xenogears (USA) (Disc 1).bin (+ .cue): 718,738,272 bytes,
       SHA-1 12db8ccb93516c391630f046a143762337cc21f4
     - Xenogears, the Russian fan translation, DISC 1 — the game will be in Russian.
       Checked with the image xenogears_rus_xz.BIN (+ .CUE): 718,792,368 bytes,
       SHA-1 23819e084229d04aad4bf5ce6d18c9935f04e202
   Format: BIN + CUE (both files side by side) or CHD. ISO/IMG are read too, but the movies will have no sound.
   Unpack archives (ZIP, 7Z, RAR) first. If both discs 1 are there, the game will be in Russian.
   Disc 2 goes into the same Games folder: of the same release as disc 1 (Xenogears (USA), DISC 2 for the American
   one; disc 2 of the Russian translation for the Russian one). It is needed only at the end of the first disc and
   can be added later, even while the game is running.

2. Run "Play.cmd" (double-click it).
   A black window first checks the Games folder and says which language the game will be in, or what is
   missing. It prints its lines in Russian; what they mean is listed at the end of this file.
   On the first run the game prepares itself once (from a few seconds to a minute).
   While the game runs the black window stays open — it closes by itself after you quit the game.
   The game starts as on the console: the publisher's notice, the opening movie, the title screen.
   On the title: X opens the menu, Up — New Game, X — choose. Continue loads a saved game.

What the computer needs
-----------------------
Windows 10 or 11, 64-bit. A video card with Vulkan or DirectX 12 and a recent driver for it
(NVIDIA, AMD or Intel, from the maker's site). About 10 GB of disk space (nearly all of it is the HD textures
in the pack folder). Nothing has to be installed.

Controls
--------
Keyboard: arrows — move; X — Cross (yes, action); Z — Circle (back);
          A — Square; S — Triangle; Enter — Start; Backspace — Select;
          Q / W — L1 / R1; E / R — L2 / R2.
Gamepad:  A / B / X / Y — Cross / Circle / Square / Triangle; the D-pad or the left stick;
          LB / RB — L1 / R1; the triggers — L2 / R2; Start / Back — Start / Select.
F1  — the cheat panel (the game pauses; its labels are in Russian): levels, money, items, HP/EP, deathblows,
      random battles on/off, turbo.
Tab — hold: the game runs 4 times faster (battles, walking; movies and menus stay as they are).
F4  — win the current battle.
F2  — light and shadows on/off;  F3 — HD textures on/off;  F11 — full screen / window.
F7  — dark places brighter: off / weak / stronger ("weak" by default, the choice is remembered).
F8  — battle flashes (the whole screen lights up as a blow or a Deathblow lands): as in the game / weak / off
      ("as in the game" by default, the choice is remembered).
F5  — quick save (where you control the hero);  F9 — load the last quick save.
F6  — a "frame report": if you see something wrong in the picture (at any moment, in a cutscene too), press F6 —
      a folder named by date and time appears in the reports folder: the screenshot, the data of that frame and
      a save beside them. That folder is what to send.

Where the saves are
-------------------
The game's own saves (the File menu at save points, Continue on the title) — in the saves folder.
The F5 quick saves — in the states folder. The F6 frame reports — in the reports folder.
Logs (if something went wrong) — in the logs folder.
To move the game to another computer, copy the whole folder.

What does not work yet
----------------------
- Disc 2: at the end of the first disc the game asks for disc 2 and offers to save. If the image of
  disc 2 already lies in Games, press X — the game goes on. If not, a line over the game says which image to put
  and where: put it into Games (no need to close the game), the line goes away — press X.
  A save from the second disc (and an F5 quick save) loads as usual afterwards; the game finds disc 2 by itself.
  The game has been played to the end with this port on the Russian translation's discs; the American discs
  were played far less, and disc 2 of the American release was not tried at all.
- Some characters and monsters are in the original pixels in places: the HD texture pack has no pictures for them.
  The gear shop does not draw the gear's model.
- The opening movie plays in HD with either disc, without the Russian subtitles (the HD video has none).

If the game does not start
--------------------------
Read what the black window said. Most often: no image in the Games folder, an image of the wrong disc,
or the video card needs a newer driver. Details are in the logs folder (godot.log).

The black window's lines (it prints them in Russian)
----------------------------------------------------
"Найден английский диск 1 (Xenogears USA): <file>" / "... игра будет НА АНГЛИЙСКОМ" — the American disc 1 is
    found, the game will be in English (the lines after it only say how to get Russian text: ignore them).
"Найден диск 1 русского перевода: <file>" / "Игра будет на русском языке." — the Russian translation's disc 1
    is found, the game will be in Russian.
"Найден диск 2 ...: <file>" — disc 2 is found, the game will take it by itself at the end of the first disc.
"Диска 2 ... в папке нет." — no disc 2 in the folder yet: it is needed only at the end of the first disc.
"ОБРАЗ ДИСКА ИГРЫ НЕ НАЙДЕН." — no disc image of the game is found: put a disc 1 image into the Games folder.
"Не подходит: <file> — ..." / "Не подойдёт: <file> — ..." — this file will not do; the reason follows (a disc of
    another release or region, a broken or cut image, an archive, a format the game does not read).
"Папки pack с HD-текстурами нет ..." — the pack folder is missing or empty: the game will run with the original
    PlayStation graphics.
"Первый запуск: игра готовится к работе ..." — the first run, the game is preparing itself (once, about a minute).
"Не удалось подготовить игру к первому запуску." — the first-run preparation failed: see logs\import.log.
"Запускаю игру... Это окно закроется само ..." — the game is starting; this window closes when you quit the game.

Credits and licenses
--------------------
The game logic is the open-source Weltall core (MIT), the engine is Godot (MIT): see the LICENSES folder.
The HD texture pack and the HD opening video are fan-made material for personal use. Xenogears belongs to
Square Enix; this folder holds no part of the game itself.
