#include "logging.h"
#include <windows.h>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <ctime>
#include <mutex>
#include <sys/stat.h>

static FILE* g_logFile = nullptr;
static std::mutex g_logMutex;
static char g_logPath[MAX_PATH] = "archipelago_dll.log";

// Keep the log from growing without bound across hundreds of sessions:
// above this size the previous log is kept once as .old and a new one
// is started.
static const long long LOG_ROTATE_BYTES = 2 * 1024 * 1024;

void ap_log_init(HMODULE self) {
    if (g_logFile) return;

    char dir[MAX_PATH] = {};
    if (self && GetModuleFileNameA(self, dir, MAX_PATH)) {
        char* slash = strrchr(dir, '\\');
        if (slash) *slash = 0;
        snprintf(g_logPath, sizeof(g_logPath), "%s\\archipelago_dll.log", dir);
    }

    struct _stat64 st;
    if (_stat64(g_logPath, &st) == 0 && st.st_size > LOG_ROTATE_BYTES) {
        char old[MAX_PATH + 8];
        snprintf(old, sizeof(old), "%s.old", g_logPath);
        remove(old);
        rename(g_logPath, old);
    }

    g_logFile = fopen(g_logPath, "a");
    if (g_logFile) {
        fprintf(g_logFile, "\n=== Stellaris Archipelago DLL loaded ===\n");
        fflush(g_logFile);
    }
}

const char* ap_log_path() { return g_logPath; }

void ap_log_shutdown() {
    // Take the same lock as ap_log so a thread mid-log can't use the
    // FILE* while we free it.
    std::lock_guard<std::mutex> lock(g_logMutex);
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
