#pragma once
#include <windows.h>

// Logs to archipelago_dll.log next to the DLL itself (i.e. next to
// stellaris.exe), regardless of the process's working directory.
void ap_log(const char* fmt, ...);
void ap_log_init(HMODULE self);
void ap_log_shutdown();
const char* ap_log_path();
