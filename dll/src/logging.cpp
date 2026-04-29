#include "logging.h"
#include <windows.h>
#include <cstdio>
#include <cstdarg>
#include <ctime>
#include <mutex>

static FILE* g_logFile = nullptr;
static std::mutex g_logMutex;

void ap_log_init() {
    if (g_logFile) return;
    g_logFile = fopen("archipelago_dll.log", "a");
    if (g_logFile) {
        fprintf(g_logFile, "\n=== Stellaris Archipelago DLL loaded ===\n");
        fflush(g_logFile);
    }
}

void ap_log_shutdown() {
    if (g_logFile) {
        fprintf(g_logFile, "=== DLL unloaded ===\n");
        fclose(g_logFile);
        g_logFile = nullptr;
    }
}

void ap_log(const char* fmt, ...) {
    std::lock_guard<std::mutex> lock(g_logMutex);
    if (!g_logFile) return;

    // Timestamp
    time_t now = time(nullptr);
    struct tm tm_buf;
    localtime_s(&tm_buf, &now);
    fprintf(g_logFile, "[%02d:%02d:%02d] ",
        tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);

    // Message
    va_list args;
    va_start(args, fmt);
    vfprintf(g_logFile, fmt, args);
    va_end(args);

    fprintf(g_logFile, "\n");
    fflush(g_logFile);
}
