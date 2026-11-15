# Stage 0 console probe: links the WeltallCore.lib that weltall/Tests builds (configure that first).
cmake_minimum_required(VERSION 3.25)
project(XenoProbe LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(WELTALL "${CMAKE_CURRENT_SOURCE_DIR}/../../weltall")
set(WELTALL_LIB "${WELTALL}/out/tests/windows/Release/WeltallCore.lib")

# The core's own language rules (weltall/Tests/CMakeLists.txt): no exceptions, no RTTI.
string(REGEX REPLACE "/EH[a-z]+" "" CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")

add_library(WeltallCore STATIC IMPORTED)
set_target_properties(WeltallCore PROPERTIES IMPORTED_LOCATION "${WELTALL_LIB}")
target_include_directories(WeltallCore INTERFACE "${WELTALL}/Source/WeltallCore/Public")
target_compile_options(WeltallCore INTERFACE /EHs-c- /GR- /utf-8 /permissive-)
target_compile_definitions(WeltallCore INTERFACE _HAS_EXCEPTIONS=0 WELTALLCORE_API=)

# NewGameParty: Weltall's test helper (MIT), used as is.
add_executable(probe_field probe_field.cpp "${WELTALL}/Tests/Support/NewGameParty.cpp")
target_include_directories(probe_field PRIVATE "${WELTALL}/Tests")
target_link_libraries(probe_field PRIVATE WeltallCore)
