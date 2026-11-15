@echo off
rem Xenogears from the title screen: the console switched on (publisher's notice, opening movie, title), where
rem Continue loads a File save (out\saves\game). The same as play.cmd boot=1; extra arguments go on to the game.
call "%~dp0play.cmd" boot=1 %*
