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

static LRESULT CALLBACK AP_WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_TIMER && wp == AP_TIMER_ID) { bridge_tick(); return 0; }
    return CallWindowProcA(g_originalWndProc, hwnd, msg, wp, lp);
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
    ap_log("Deferred init: found game window %p", (void*)hwnd);
    g_originalWndProc = (WNDPROC)SetWindowLongPtrA(hwnd, GWLP_WNDPROC, (LONG_PTR)AP_WndProc);
    if (g_originalWndProc) SetTimer(hwnd, AP_TIMER_ID, AP_TICK_MS, nullptr);
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
        ap_log("=== Stellaris Archipelago Bridge DLL v0.3 ===");
        if (!proxy_init()) { ap_log("FATAL: proxy_init failed"); return FALSE; }
        ap_log("DllMain complete (init will trigger on first proxy call)");
        break;
    case DLL_PROCESS_DETACH:
        ap_log("Shutting down...");
        bridge_stop();
        if (g_gameWindow) { KillTimer(g_gameWindow, AP_TIMER_ID);
            if (g_originalWndProc) SetWindowLongPtrA(g_gameWindow, GWLP_WNDPROC, (LONG_PTR)g_originalWndProc); }
        proxy_shutdown();
        ap_log_shutdown();
        break;
    }
    return TRUE;
}
