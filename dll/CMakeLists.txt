cmake_minimum_required(VERSION 3.20)
project(StellarisBridge VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Static CRT: version.dll is a load-time import of stellaris.exe, so a
# missing vcruntime140/msvcp140 on the player's machine would abort the
# game launch entirely with an opaque loader error. /MT removes the
# VC++ redistributable dependency.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

add_library(version SHARED
    src/dllmain.cpp
    src/proxy.cpp
    src/bridge.cpp
    src/console.cpp
    src/logging.cpp
)

target_sources(version PRIVATE version.def)

target_compile_definitions(version PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _CRT_SECURE_NO_WARNINGS
)

target_link_libraries(version PRIVATE
    kernel32 user32 shell32 ole32
)

set_target_properties(version PROPERTIES
    OUTPUT_NAME "version"
    PREFIX ""
    SUFFIX ".dll"
)

# Unit test for the pattern scanner (the safety-critical part): a plain
# console exe, off by default so a player's build-dll stays a single DLL.
option(BUILD_TESTING "Build dll/tests" OFF)
if(BUILD_TESTING)
    enable_testing()
    add_executable(scanner_test tests/scanner_test.cpp)
    target_include_directories(scanner_test PRIVATE src)
    target_compile_definitions(scanner_test PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX _CRT_SECURE_NO_WARNINGS)
    add_test(NAME scanner_test COMMAND scanner_test)

    # Host process for scripts/check_dll_pipe.py (drives the real pipe server).
    add_executable(pipe_host tests/pipe_host.cpp)
    target_compile_definitions(pipe_host PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX _CRT_SECURE_NO_WARNINGS)
endif()
