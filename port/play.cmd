@echo off
rem Xenogears in the Godot shell over WeltallCore, HD pack and light on. The text is Russian by default: the
rem Russian translation's disc 1 (a copy in games_ru\, git ignores it) with its own text, font and pictures;
rem the sound and the USA disc 1 still come from weltall\Games. lang=en plays the USA disc 1 as it is.
rem Keyboard: arrows = directions, X = Cross, Z = Circle, A = Square, S = Triangle,
rem           Enter = Start, Backspace = Select, Q/W = L1/R1, E/R = L2/R2.
rem Gamepad:  A/B/X/Y = Cross/Circle/Square/Triangle, d-pad or left stick, LB/RB = L1/R1, Start/Back.
rem F2 = light on/off, F3 = HD pack on/off, F7 = dark places brighter (off / weak / stronger, remembered), F11 = full screen.
rem F8 = battle flashes (the whole screen lit up as a blow lands): as in the game / weak / off, remembered; flash=2|1|0.
rem F5 = save a state (out\states), F9 = load the newest state. The game's own File saves go to out\saves\game.
rem F6 = a report of the frame shown, at any moment (cutscenes too): a folder in out\frame_reports with the shot,
rem       the shot without the pack and the light, frame.txt (what is drawn not from the pack, every primitive),
rem       state.state and inputs.txt (play.cmd script_file=<its inputs.txt> goes that way again). See docs\HOW_IT_WORKS.md, "F6".
rem Disc 2: the Russian translation's disc 2 in games_ru\ (or weltall\Games; lang=en: USA disc 2 in weltall\Games), any
rem       name, found by content, is taken where the game asks for it (the story's "INSERT DISC 2", a save of disc 2);
rem       missing, a line over the game says where to put it, and it is taken from there while the game waits.
rem Cheats, to run through the game quickly (off unless used):
rem   F1  = cheat panel, the game paused while it is open: levels (+1 / +10, by the game's own rule, as a won battle
rem         gives them), EXP, HP/EP full, deathblows ("learn all": every one the hero's level allows, by the game's
rem         own rule; the 7-AP ones once the story opens them), money (set / +10 000), items from the disc's lists, gears' HP and fuel full,
rem         random battles off, turbo always x2 / x4. What is changed there goes into saves made afterwards.
rem   Tab = held: the game at 4 times its pace (battles, the field, the world map; movies and menus as they are; music keeps its tempo).
rem   F4  = win the battle being fought (the game gives its EXP, gold and drops and shows its results).
rem Extra arguments go to the game:
rem   play.cmd                     a new game from the prologue
rem   play.cmd ff=8000             a new game, the opening skipped to Fei's room
rem   play.cmd card=out\saves\usa.srm slot=0   your USA memory card's first save (a copy; near Lahan)
rem   play.cmd boot=1              the console switched on: publisher's notice, opening movie, title (New Game: Up, then X)
rem   play.cmd lang=en             the English text (USA disc 1); the window title shows which (RU / EN)
rem   play.cmd encounters=0        random battles off from the start (also on the F1 panel)
rem   play.cmd turbo=4             the game always at 4 times its pace (turbo=2: twice)
rem   play.cmd flash=0             the battle flashes off from the start (as F8; 1 weak, 2 as in the game)
rem   play.cmd palhold=0           the palette hold off, for comparisons (on by default: a model's texture whose palette
rem                                changed by at most 2 of 31 in the colours its texels use keeps the HD picture chosen
rem                                before - the world map's land no longer flickers; characters are never held;
rem                                see docs\HOW_IT_WORKS.md, "Palette hold")
rem   play.cmd lang=auto           the discs in weltall\Games found by their content (the translation's disc 1 first)
rem Paths: root=<folder> (default this folder) with games=, pack=, alias_index=, movies= (out\movies: HD replacements of
rem the game's movies, <disc>\<NN>.ogv), saves=, states= under it. The mod folder for another PC: python tools\make_dist.py
rem (dist\XenogearsHD, its own batch file), see docs\BUILD.md.
start "" "%~dp0tools\godot\Godot_v4.7.2-stable_win64.exe" --path "%~dp0game" -- map=4 reports=out\frame_reports %*
