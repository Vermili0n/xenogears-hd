# The Godot bridge: godot-cpp (tag godot-4.5-stable) + WeltallCore built from weltall/Source with the core's own rules.
# Output: game/bin/xeno_bridge.dll, which game/xeno.gdextension loads.
cmake_minimum_required(VERSION 3.25)
project(XenoBridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(godot-cpp)

# WeltallCore as weltall/Tests/CMakeLists.txt builds it (no exceptions, no RTTI, warnings as errors), here with
# godot-cpp's static CRT so the two link together.
set(WELTALL "${CMAKE_CURRENT_SOURCE_DIR}/../weltall")
string(REGEX REPLACE "/EH[a-z]+" "" CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")
file(GLOB_RECURSE CORE_SOURCES CONFIGURE_DEPENDS "${WELTALL}/Source/WeltallCore/Private/*.cpp")
add_library(WeltallCore STATIC ${CORE_SOURCES} "${WELTALL}/Tests/Support/NewGameParty.cpp")
target_include_directories(WeltallCore PUBLIC "${WELTALL}/Source/WeltallCore/Public" "${WELTALL}/Tests" PRIVATE "${WELTALL}/Source/WeltallCore/Private")
# No RTTI stays the core's own (and the session's, which only talks to it): godot-cpp's classes need RTTI (Wrapped uses dynamic_cast).
target_compile_options(WeltallCore PUBLIC /EHs-c- /utf-8 /permissive- /MP /Z7 PRIVATE /GR- /W4 /WX)
set_source_files_properties(src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp PROPERTIES COMPILE_OPTIONS /GR-)
# The session reads the core's own layout of the game state's records (Game/GameStateLayout.h, a header of its private sources).
set_property(SOURCE src/xeno_session.cpp APPEND PROPERTY INCLUDE_DIRECTORIES "${WELTALL}/Source/WeltallCore/Private")
target_compile_definitions(WeltallCore PUBLIC _HAS_EXCEPTIONS=0 WELTALLCORE_API=)

# bc7decomp (MIT or public domain, third_party/bc7decomp/SOURCE.txt) decodes the pack's BC7 pictures.
add_library(xeno_bridge SHARED src/register_types.cpp src/xeno_core.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp third_party/bc7decomp/bc7decomp.cpp)
target_link_libraries(xeno_bridge PRIVATE godot::cpp WeltallCore)
target_compile_options(xeno_bridge PRIVATE /W3 /MP)
# Symbols in Release too (/Z7 in the objects, the PDB beside the build): crashes inside Godot need them.
target_link_options(xeno_bridge PRIVATE /DEBUG /OPT:REF /OPT:ICF)
# XENO_BIN: where the DLL goes (a second build folder can put it into a copy of game/ while the game runs from game/).
set(XENO_BIN "${CMAKE_CURRENT_SOURCE_DIR}/../game/bin" CACHE PATH "Where xeno_bridge.dll is written")
set(BIN "${XENO_BIN}")
set_target_properties(xeno_bridge PROPERTIES RUNTIME_OUTPUT_DIRECTORY_RELEASE "${BIN}" RUNTIME_OUTPUT_DIRECTORY_DEBUG "${BIN}"
	RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${BIN}" PDB_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/pdb")

# The session alone, without Godot: what goes wrong in the core shows here first. (Every target with the session has the
# disc survey too: the session's drive finds the other disc by content, xeno_discs.cpp.)
add_executable(session_smoke src/session_smoke.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(session_smoke PRIVATE WeltallCore)

# Every field map of disc 1 headless: how many sprite pieces, 2D primitives and scenery polygons the pack draws.
add_executable(pack_sweep src/pack_sweep.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(pack_sweep PRIVATE WeltallCore)

# The world map entered directly at each era's arrivals and each cutscene scene, headless: core errors and what is drawn.
add_executable(world_sweep src/world_sweep.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(world_sweep PRIVATE WeltallCore)

# The Battling arena entered directly (every opponent) headless, as Weltall's arena audit enters it; and where the story starts it.
add_executable(arena_sweep src/arena_sweep.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(arena_sweep PRIVATE WeltallCore)

# The game's sound heard headless as the live game takes it: a WAV and per-second levels.
add_executable(sound_smoke src/sound_smoke.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(sound_smoke PRIVATE WeltallCore)

# Every text of a disc as the core reads it, decoded without drawing (the translation's sweep).
add_executable(text_sweep src/text_sweep.cpp src/xeno_translation.cpp)
target_link_libraries(text_sweep PRIVATE WeltallCore)

# A party member's sprite frames as the core builds them, to compare with the texture pack's layouts.
add_executable(sprite_parts_dump src/sprite_parts_dump.cpp)
target_link_libraries(sprite_parts_dump PRIVATE WeltallCore)

# The story walked by Weltall's own test explorer (Tests/Support/StorySweep*, as WeltallStorySweep -explore=N), the bridge
# looking on at every frame: save states along the way, the bridge's tallies and what it leaves undrawn.
file(GLOB STORY_WALK_SUPPORT CONFIGURE_DEPENDS "${WELTALL}/Tests/Support/StorySweep*.cpp")
add_executable(story_walk src/story_walk.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp ${STORY_WALK_SUPPORT}
	"${WELTALL}/Tests/Support/PlayedGame.cpp" "${WELTALL}/Tests/Support/StoryValues.cpp" "${WELTALL}/Tests/Support/XorShift32.cpp")
target_link_libraries(story_walk PRIVATE WeltallCore)

# Each save state of a folder (the story walk's) loaded and played headless: the bridge's tallies and what it leaves undrawn.
add_executable(story_states src/story_states.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(story_states PRIVATE WeltallCore)

add_executable(sprite_coverage src/sprite_coverage.cpp src/xeno_session.cpp src/xeno_translation.cpp src/xeno_discs.cpp)
target_link_libraries(sprite_coverage PRIVATE WeltallCore)

# The mod folder's start-up check (its batch file runs it): the disc images found by content, said in Russian.
add_executable(xeno_check src/xeno_check.cpp src/xeno_discs.cpp src/xeno_translation.cpp)
target_link_libraries(xeno_check PRIVATE WeltallCore)

# A disc's movies decoded as the core decodes them, headless (to match a replacement video to its movie).
add_executable(movie_dump src/movie_dump.cpp)
target_link_libraries(movie_dump PRIVATE WeltallCore)
