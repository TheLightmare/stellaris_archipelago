#include "proxy.h"
#include "bridge.h"
#include "console.h"
#include "logging.h"
#include <windows.h>

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
        // Marker so the DLL log proves this code path is live. If you
        // ever stop seeing this line when the bridge sends FLUSH, either
        // the DLL wasn't rebuilt or the game window hook was lost.
        ap_log("Bridge: WM_AP_FLUSH received on game thread");
        return (LRESULT)console_process_queue();
    }
    return g_windowIsUnicode
        ? CallWindowProcW(g_originalWndProc, hwnd, msg, wp, lp)
        : CallWindowProcA(g_originalWndProc, hwnd, msg, wp, lp);
}

// Public entry point used by bridge.cpp's FLUSH handler.
// Returns the number of commands flushed, or -1 if the game window
// hasn't been hooked yet (commands stay queued; the timer will pick
// them up once the window is found).
int dispatch_flush_on_game_thread() {
    HWND hwnd = g_gameWindow;
    if (!hwnd) {
        ap_log("Bridge: dispatch_flush requested but no game window yet — "
               "commands stay queued");
        return -1;
    }
    LRESULT r = g_windowIsUnicode
        ? SendMessageW(hwnd, WM_AP_FLUSH, 0, 0)
        : SendMessageA(hwnd, WM_AP_FLUSH, 0, 0);
    return (int)r;
}
static BOOL CALLBACK find_game_window(HWND hwnd, LPARAM lParam) {
    DWORD pid; GetWindowThreadProcessId(hwnd, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd)) return TRUE;
    char title[256]; GetWindowTextA(hwnd, title, sizeof(title));
    if (strstr(title, "Stellaris")) {
        char cls[256]; GetClassNameA(hwnd, cls, sizeof(cls));
        if (strcmp(cls, "ConsoleWindowClass") != 0) { *reinterpret_cast<HWND*>(lParam) = hwnd; return FALSE; }
    }
    return TRUE;
}

static DWORD WINAPI deferred_init_thread(LPVOID) {
    Sleep(3000);
    ap_log("Deferred init: starting...");
    if (!console_init()) ap_log("Deferred init: console_init failed");
    bridge_start();
    ap_log("Deferred init: waiting for game window...");
    HWND hwnd = nullptr;
    for (int i = 0; i < 120; i++) { EnumWindows(find_game_window, (LPARAM)&hwnd); if (hwnd) break; Sleep(500); }
    if (!hwnd) { ap_log("Deferred init: game window not found after 60s"); return 1; }
    g_gameWindow = hwnd;
    // Log whether the window is Unicode or ANSI — we need to use the
    // matching SetWindowLongPtrW/A variant to subclass it cleanly.
    BOOL isUnicode = IsWindowUnicode(hwnd);
    g_windowIsUnicode = (isUnicode != FALSE);
    ap_log("Deferred init: found game window %p (%s)",
           (void*)hwnd, isUnicode ? "Unicode" : "ANSI");

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
        return 2;
    }
    if (!prev) {
        // Returned 0, GetLastError 0. Theoretically possible if the
        // previous WndProc literally was 0, but that doesn't happen in
        // practice for a real window. Treat as suspect.
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
    ap_log("Deferred init: complete — bridge is operational");
    return 0;
}

void trigger_deferred_init() {
    if (InterlockedCompareExchange(&g_init_started, 1, 0) == 0) {
        ap_log("Triggering deferred init (first proxy call)...");
        HANDLE h = CreateThread(nullptr, 0, deferred_init_thread, nullptr, 0, nullptr);
        if (h) CloseHandle(h);
    }
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        ap_log_init();
        ap_log("=== Stellaris Archipelago Bridge DLL v0.4 (FLUSH-marshal + diagnostics) ===");
        if (!proxy_init()) { ap_log("FATAL: proxy_init failed"); return FALSE; }
        ap_log("DllMain complete (init will trigger on first proxy call)");
        // NOTE: do NOT call trigger_deferred_init() from here. CreateThread
        // from inside DllMain is technically permitted but causes the new
        // thread's DLL_THREAD_ATTACH notifications to fire while Stellaris's
        // loader is still mid-initialization for us, which can crash the
        // process with STATUS_STACK_BUFFER_OVERRUN (0xC0000409). The proxy
        // exports below all trigger init on first call, which is the safe
        // path — by then DllMain has long since returned and the loader
        // lock is fully released. Every proxied export in proxy.cpp must
        // call trigger_deferred_init() so we don't depend on Stellaris
        // calling any one specific export first.
        break;
    case DLL_PROCESS_DETACH:
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
