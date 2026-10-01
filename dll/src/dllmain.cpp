#include "proxy.h"
#include "bridge.h"
#include "console.h"
#include "logging.h"
#include <windows.h>

static const char* BRIDGE_VERSION = "0.5";

static volatile LONG g_init_started = 0;
static HWND g_gameWindow = nullptr;
static WNDPROC g_originalWndProc = nullptr;
static const UINT_PTR AP_TIMER_ID = 0xAB01;
static const UINT AP_TICK_MS = 200;

// Custom window message used by bridge.cpp (running on the pipe server
// thread) to ask the game thread to drain the command queue. SendMessage
// from another thread blocks the caller until WndProc returns, so we get
// a synchronous "do this on the right thread and tell me the count" call.
// Without this, FLUSH used to call console_process_queue() directly from
// the pipe server thread, which invoked Stellaris's internal
// ExecuteCommand from the wrong thread and crashed the game on the very
// first command.
static const UINT WM_AP_FLUSH = WM_USER + 0x100;

// Tracks whether the subclassed window is Unicode, so we use the
// matching CallWindowProcW/A variant when forwarding unhandled messages.
// Mismatched A/W can corrupt WM_CHAR and similar text messages.
static bool g_windowIsUnicode = false;

static LRESULT CALLBACK AP_WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_TIMER && wp == AP_TIMER_ID) {
        // One-shot diagnostic: prove the WM_TIMER hook is actually firing.
        // If you never see this line, the WndProc subclass didn't take.
        static bool s_firstTick = true;
        if (s_firstTick) {
            s_firstTick = false;
            ap_log("Bridge: first WM_TIMER tick received — subclass is live");
        }
        bridge_tick();
        return 0;
    }
    if (msg == WM_AP_FLUSH) {
        return (LRESULT)console_process_queue();
    }
    return g_windowIsUnicode
        ? CallWindowProcW(g_originalWndProc, hwnd, msg, wp, lp)
        : CallWindowProcA(g_originalWndProc, hwnd, msg, wp, lp);
}

int dispatch_flush_on_game_thread(DWORD timeout_ms) {
    HWND hwnd = g_gameWindow;
    if (!hwnd) {
        ap_log("Bridge: dispatch_flush requested but no game window yet — "
               "commands stay queued");
        return -1;
    }
    // Bounded dispatch: a plain SendMessage blocks this (pipe) thread
    // forever if the game thread isn't pumping messages (loading screen,
    // autosave stall, shutdown). On timeout the commands stay queued and
    // the WM_TIMER tick drains them later. The timeout is deliberately
    // shorter than the Python client's pipe I/O timeout so the client
    // gets a definite "queued" answer instead of giving up on the pipe.
    DWORD_PTR result = 0;
    LRESULT ok = g_windowIsUnicode
        ? SendMessageTimeoutW(hwnd, WM_AP_FLUSH, 0, 0, SMTO_ABORTIFHUNG | SMTO_NORMAL, timeout_ms, &result)
        : SendMessageTimeoutA(hwnd, WM_AP_FLUSH, 0, 0, SMTO_ABORTIFHUNG | SMTO_NORMAL, timeout_ms, &result);
    if (!ok) {
        ap_log("Bridge: flush dispatch timed out after %lu ms — game thread busy; "
               "commands stay queued for the timer tick", timeout_ms);
        return -1;
    }
    return (int)result;
}

// ---------------------------------------------------------------------
// Game window discovery
// ---------------------------------------------------------------------

struct WindowSearch {
    HWND titled = nullptr;   // visible window of this process with "Stellaris" in the title
    HWND fallback = nullptr; // any visible, non-console top-level window of this process
};

static BOOL CALLBACK find_game_window(HWND hwnd, LPARAM lParam) {
    auto* search = reinterpret_cast<WindowSearch*>(lParam);
    DWORD pid; GetWindowThreadProcessId(hwnd, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd)) return TRUE;
    if (GetWindow(hwnd, GW_OWNER) != nullptr) return TRUE; // owned popups/tooltips
    char cls[256]; GetClassNameA(hwnd, cls, sizeof(cls));
    if (strcmp(cls, "ConsoleWindowClass") == 0) return TRUE;
    char title[256]; GetWindowTextA(hwnd, title, sizeof(title));
    if (strstr(title, "Stellaris")) { search->titled = hwnd; return FALSE; }
    if (!search->fallback) search->fallback = hwnd;
    return TRUE;
}

static HWND wait_for_game_window() {
    // Prefer the window titled "Stellaris". If the title ever changes
    // (localisation, a version suffix the strstr still catches, a rename)
    // accept any visible top-level window of ours after a grace period
    // rather than never hooking at all.
    const int TOTAL_WAIT_MS = 120000, FALLBACK_AFTER_MS = 20000, STEP_MS = 500;
    for (int waited = 0; waited < TOTAL_WAIT_MS; waited += STEP_MS) {
        WindowSearch s;
        EnumWindows(find_game_window, (LPARAM)&s);
        if (s.titled) return s.titled;
        if (s.fallback && waited >= FALLBACK_AFTER_MS) {
            char title[256] = {}; GetWindowTextA(s.fallback, title, sizeof(title));
            ap_log("Deferred init: no window titled 'Stellaris' after %ds; using '%s'",
                   waited / 1000, title);
            return s.fallback;
        }
        Sleep(STEP_MS);
    }
    return nullptr;
}

// ---------------------------------------------------------------------
// Deferred initialisation (runs on its own thread, outside the loader lock)
// ---------------------------------------------------------------------

static DWORD deferred_init_body() {
    Sleep(3000);
    ap_log("Deferred init: starting...");
    if (!console_init()) ap_log("Deferred init: console_init failed");
    bridge_start();
    ap_log("Deferred init: waiting for game window...");
    HWND hwnd = wait_for_game_window();
    if (!hwnd) { ap_log("Deferred init: game window not found after 120s"); return 1; }
    g_gameWindow = hwnd;

    char cls[256] = {}; GetClassNameA(hwnd, cls, sizeof(cls));
    char title[256] = {}; GetWindowTextA(hwnd, title, sizeof(title));
    BOOL isUnicode = IsWindowUnicode(hwnd);
    g_windowIsUnicode = (isUnicode != FALSE);
    ap_log("Deferred init: found game window %p '%s' class '%s' (%s)",
           (void*)hwnd, title, cls, isUnicode ? "Unicode" : "ANSI");

    // Subclass the WndProc. Use SetLastError(0) before so we can
    // distinguish "previous WndProc was 0" (impossible for a normal
    // window — would mean failure) from "previous WndProc was non-zero"
    // (success). Use the variant matching the window's character set.
    SetLastError(0);
    LONG_PTR prev = isUnicode
        ? SetWindowLongPtrW(hwnd, GWLP_WNDPROC, (LONG_PTR)AP_WndProc)
        : SetWindowLongPtrA(hwnd, GWLP_WNDPROC, (LONG_PTR)AP_WndProc);
    DWORD err = GetLastError();
    g_originalWndProc = (WNDPROC)prev;

    if (!prev && err != 0) {
        // Real failure. Without the subclass, neither WM_TIMER ticks
        // nor WM_AP_FLUSH dispatches will reach our handler, and the
        // command queue will never drain. Bridge effects are silently
        // lost.
        ap_log("Deferred init: FAILED to subclass WndProc — "
               "GetLastError=%lu (0x%08lX)", err, err);
        ap_log("Deferred init: queue draining is BROKEN — bridge effects "
               "will be queued but never executed");
        g_gameWindow = nullptr;
        return 2;
    }
    if (!prev) {
        ap_log("Deferred init: WARNING — SetWindowLongPtr returned 0 with "
               "no error. Subclass may not be fully installed.");
    }

    UINT_PTR timerId = SetTimer(hwnd, AP_TIMER_ID, AP_TICK_MS, nullptr);
    if (timerId == 0) {
        ap_log("Deferred init: SetTimer FAILED — GetLastError=%lu",
               GetLastError());
        ap_log("Deferred init: timer-driven queue drain BROKEN — only "
               "FLUSH dispatch will work");
    } else {
        ap_log("Deferred init: WndProc subclassed and %dms timer armed",
               AP_TICK_MS);
    }
    ap_log("Deferred init: complete — bridge is operational (%s)", console_status().c_str());
    return 0;
}

// SEH wrapper (no C++ objects here): an unexpected fault during init must
// show up in the log, not as an unexplained game crash a few seconds in.
static DWORD WINAPI deferred_init_thread(LPVOID) {
    __try {
        return deferred_init_body();
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        ap_log("Deferred init: CRASHED with exception 0x%08lX — bridge disabled", GetExceptionCode());
        return 3;
    }
}

void trigger_deferred_init() {
    if (InterlockedCompareExchange(&g_init_started, 1, 0) == 0) {
        ap_log("Triggering deferred init (first proxy call)...");
        HANDLE h = CreateThread(nullptr, 0, deferred_init_thread, nullptr, 0, nullptr);
        if (h) CloseHandle(h);
        else ap_log("ERROR: CreateThread for deferred init failed (%lu)", GetLastError());
    }
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        ap_log_init(hModule);
        ap_log("=== Stellaris Archipelago Bridge DLL v%s ===", BRIDGE_VERSION);
        ap_log("DllMain complete (real version.dll loads lazily; init triggers on first proxy call)");
        // NOTE: nothing else happens here on purpose. LoadLibrary and
        // CreateThread are both unsafe under the loader lock. The real
        // version.dll is loaded on the first proxied call (proxy.cpp), and
        // that same call starts the deferred init thread. Every proxied
        // export does both, so we don't depend on Stellaris calling any
        // one specific function first.
        break;
    case DLL_PROCESS_DETACH:
        // reserved != nullptr means the process is terminating: every
        // other thread has already been killed at an arbitrary point and
        // may hold locks (the pipe thread logs constantly, so g_logMutex
        // is a real risk). Touching mutexes, handles, or windows here can
        // deadlock or crash the exiting process — do nothing; the OS
        // reclaims everything.
        if (reserved != nullptr)
            break;
        // FreeLibrary path (never happens for a load-time version.dll
        // proxy, but be correct anyway): best-effort teardown.
        ap_log("Shutting down...");
        bridge_stop();
        if (g_gameWindow) {
            KillTimer(g_gameWindow, AP_TIMER_ID);
            if (g_originalWndProc) {
                if (g_windowIsUnicode)
                    SetWindowLongPtrW(g_gameWindow, GWLP_WNDPROC, (LONG_PTR)g_originalWndProc);
                else
                    SetWindowLongPtrA(g_gameWindow, GWLP_WNDPROC, (LONG_PTR)g_originalWndProc);
            }
        }
        proxy_shutdown();
        ap_log_shutdown();
        break;
    }
    return TRUE;
}
