@echo off
rem Xenogears HD: the game in a Godot shell over WeltallCore, with an HD texture pack and an HD opening movie.
rem Double-click to play. The disc image is not included: put yours into the Games folder (see the README file).
rem Disc 2 goes there too, now or once the story asks for it: the game finds it there by itself, even while it runs.
rem All the Russian text this window shows comes from engine\xeno_check.exe (this file stays ASCII on purpose).
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "ENGINE=%ROOT%\engine"
cd /d "%ROOT%"

rem The disc images in Games, found by their content: 0 Russian, 1 English, 2 nothing to play.
"%ENGINE%\xeno_check.exe" check "%ROOT%"
if errorlevel 2 goto stop

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if exist "%ROOT%\game\.godot\extension_list.cfg" goto run

rem The first run: Godot imports the project once (headless, no editor window).
"%ENGINE%\xeno_check.exe" say firstrun
"%ENGINE%\Godot_v4.7.2-stable_win64_console.exe" --headless --import --path "%ROOT%\game" > "%ROOT%\logs\import.log" 2>&1
if exist "%ROOT%\game\.godot\extension_list.cfg" goto run
"%ENGINE%\xeno_check.exe" say firstrun_failed "%ROOT%\logs\import.log"
goto stop

:run
"%ENGINE%\xeno_check.exe" say starting
rem The game's own lines go to logs\godot.log only (Godot would print them into this window too).
"%ENGINE%\Godot_v4.7.2-stable_win64.exe" --path "%ROOT%\game" --log-file "%ROOT%\logs\godot.log" -- "root=%ROOT%" games=Games lang=auto pack=pack alias_table=data\sprite_alias_table.csv alias_index=data\sprite_alias_index.bin movies=movies saves=saves states=states reports=reports boot=1 %* > nul 2>&1
set "CODE=%ERRORLEVEL%"
rem 0: the player closed the game; 2: the game could not start and its window said why.
if "%CODE%"=="0" goto end
if "%CODE%"=="2" goto end
"%ENGINE%\xeno_check.exe" say failed %CODE% "%ROOT%\logs\godot.log"

:stop
echo.
pause

:end
endlocal
