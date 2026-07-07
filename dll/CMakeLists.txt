cmake_minimum_required(VERSION 3.20)
project(StellarisBridge VERSION 0.3.0 LANGUAGES CXX)

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
    kernel32 user32 shell32 ole32 psapi
)

set_target_properties(version PROPERTIES
    OUTPUT_NAME "version"
    PREFIX ""
    SUFFIX ".dll"
)
