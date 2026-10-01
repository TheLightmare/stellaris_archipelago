#include "proxy.h"
#include "logging.h"
#include <cstdio>

static HMODULE g_realDll = nullptr;
static FARPROC fp[17] = {};
static INIT_ONCE g_loadOnce = INIT_ONCE_STATIC_INIT;

// Loads the real version.dll from System32 and resolves its exports.
// Runs at most once, on the first proxied call — NOT in DllMain, where
// LoadLibrary is forbidden by the loader-lock rules (it usually works
// for system DLLs, but "usually" is the wrong word for something that
// runs before the game's first frame). A failure here degrades the
// proxied functions to "return FALSE/0" instead of aborting the game.
static BOOL CALLBACK load_real_dll(PINIT_ONCE, PVOID, PVOID*) {
    char sysDir[MAX_PATH];
    if (!GetSystemDirectoryA(sysDir, MAX_PATH)) { ap_log("ERROR: GetSystemDirectory failed"); return TRUE; }
    strcat_s(sysDir, "\\version.dll");
    g_realDll = LoadLibraryA(sysDir);
    if (!g_realDll) { ap_log("ERROR: Failed to load real version.dll from %s (%lu)", sysDir, GetLastError()); return TRUE; }
    fp[0]  = GetProcAddress(g_realDll, "GetFileVersionInfoA");
    fp[1]  = GetProcAddress(g_realDll, "GetFileVersionInfoByHandle");
    fp[2]  = GetProcAddress(g_realDll, "GetFileVersionInfoExA");
    fp[3]  = GetProcAddress(g_realDll, "GetFileVersionInfoExW");
    fp[4]  = GetProcAddress(g_realDll, "GetFileVersionInfoSizeA");
    fp[5]  = GetProcAddress(g_realDll, "GetFileVersionInfoSizeExA");
    fp[6]  = GetProcAddress(g_realDll, "GetFileVersionInfoSizeExW");
    fp[7]  = GetProcAddress(g_realDll, "GetFileVersionInfoSizeW");
    fp[8]  = GetProcAddress(g_realDll, "GetFileVersionInfoW");
    fp[9]  = GetProcAddress(g_realDll, "VerFindFileA");
    fp[10] = GetProcAddress(g_realDll, "VerFindFileW");
    fp[11] = GetProcAddress(g_realDll, "VerInstallFileA");
    fp[12] = GetProcAddress(g_realDll, "VerInstallFileW");
    fp[13] = GetProcAddress(g_realDll, "VerLanguageNameA");
    fp[14] = GetProcAddress(g_realDll, "VerLanguageNameW");
    fp[15] = GetProcAddress(g_realDll, "VerQueryValueA");
    fp[16] = GetProcAddress(g_realDll, "VerQueryValueW");
    ap_log("Proxy: real version.dll loaded from %s", sysDir);
    return TRUE;
}

bool proxy_init() {
    InitOnceExecuteOnce(&g_loadOnce, load_real_dll, nullptr, nullptr);
    return g_realDll != nullptr;
}
void proxy_shutdown() { if (g_realDll) { FreeLibrary(g_realDll); g_realDll = nullptr; } }

extern void trigger_deferred_init();
#define PROXY_CALL(idx, ret, ...) reinterpret_cast<ret(__stdcall*)(__VA_ARGS__)>(fp[idx])

// IMPORTANT: every proxied export MUST call proxy_init() (lazy load of the
// real DLL) and trigger_deferred_init(). We can't predict which
// version.dll function Stellaris will call first (varies by Windows
// version, game build, and locale). Modern apps use the W variants; if
// only the A variants triggered init, the bridge thread (and therefore
// the named pipe) would never start on those systems — exactly the
// silent-DLL bug seen in the wild. Both functions are idempotent and
// safe to call from any thread.
#define PROXY_PROLOGUE() do { proxy_init(); trigger_deferred_init(); } while (0)

extern "C" {
BOOL __stdcall proxy_GetFileVersionInfoA(LPCSTR a, DWORD b, DWORD c, LPVOID d) {
    PROXY_PROLOGUE();
    return fp[0] ? PROXY_CALL(0, BOOL, LPCSTR, DWORD, DWORD, LPVOID)(a, b, c, d) : FALSE;
}
BOOL __stdcall proxy_GetFileVersionInfoByHandle(LPCSTR a, DWORD b, DWORD c, LPVOID d) {
    PROXY_PROLOGUE();
    return fp[1] ? PROXY_CALL(1, BOOL, LPCSTR, DWORD, DWORD, LPVOID)(a, b, c, d) : FALSE;
}
BOOL __stdcall proxy_GetFileVersionInfoExA(DWORD f, LPCSTR a, DWORD b, DWORD c, LPVOID d) {
    PROXY_PROLOGUE();
    return fp[2] ? PROXY_CALL(2, BOOL, DWORD, LPCSTR, DWORD, DWORD, LPVOID)(f, a, b, c, d) : FALSE;
}
BOOL __stdcall proxy_GetFileVersionInfoExW(DWORD f, LPCWSTR a, DWORD b, DWORD c, LPVOID d) {
    PROXY_PROLOGUE();
    return fp[3] ? PROXY_CALL(3, BOOL, DWORD, LPCWSTR, DWORD, DWORD, LPVOID)(f, a, b, c, d) : FALSE;
}
DWORD __stdcall proxy_GetFileVersionInfoSizeA(LPCSTR a, LPDWORD b) {
    PROXY_PROLOGUE();
    return fp[4] ? PROXY_CALL(4, DWORD, LPCSTR, LPDWORD)(a, b) : 0;
}
DWORD __stdcall proxy_GetFileVersionInfoSizeExA(DWORD f, LPCSTR a, LPDWORD b) {
    PROXY_PROLOGUE();
    return fp[5] ? PROXY_CALL(5, DWORD, DWORD, LPCSTR, LPDWORD)(f, a, b) : 0;
}
DWORD __stdcall proxy_GetFileVersionInfoSizeExW(DWORD f, LPCWSTR a, LPDWORD b) {
    PROXY_PROLOGUE();
    return fp[6] ? PROXY_CALL(6, DWORD, DWORD, LPCWSTR, LPDWORD)(f, a, b) : 0;
}
DWORD __stdcall proxy_GetFileVersionInfoSizeW(LPCWSTR a, LPDWORD b) {
    PROXY_PROLOGUE();
    return fp[7] ? PROXY_CALL(7, DWORD, LPCWSTR, LPDWORD)(a, b) : 0;
}
BOOL __stdcall proxy_GetFileVersionInfoW(LPCWSTR a, DWORD b, DWORD c, LPVOID d) {
    PROXY_PROLOGUE();
    return fp[8] ? PROXY_CALL(8, BOOL, LPCWSTR, DWORD, DWORD, LPVOID)(a, b, c, d) : FALSE;
}
DWORD __stdcall proxy_VerFindFileA(DWORD f, LPCSTR a, LPCSTR b, LPCSTR c, LPSTR d, PUINT e, LPSTR g, PUINT h) {
    PROXY_PROLOGUE();
    return fp[9] ? PROXY_CALL(9, DWORD, DWORD, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT, LPSTR, PUINT)(f, a, b, c, d, e, g, h) : 0;
}
DWORD __stdcall proxy_VerFindFileW(DWORD f, LPCWSTR a, LPCWSTR b, LPCWSTR c, LPWSTR d, PUINT e, LPWSTR g, PUINT h) {
    PROXY_PROLOGUE();
    return fp[10] ? PROXY_CALL(10, DWORD, DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT, LPWSTR, PUINT)(f, a, b, c, d, e, g, h) : 0;
}
DWORD __stdcall proxy_VerInstallFileA(DWORD f, LPCSTR a, LPCSTR b, LPCSTR c, LPCSTR d, LPCSTR e, LPSTR g, PUINT h) {
    PROXY_PROLOGUE();
    return fp[11] ? PROXY_CALL(11, DWORD, DWORD, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT)(f, a, b, c, d, e, g, h) : 0;
}
DWORD __stdcall proxy_VerInstallFileW(DWORD f, LPCWSTR a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPCWSTR e, LPWSTR g, PUINT h) {
    PROXY_PROLOGUE();
    return fp[12] ? PROXY_CALL(12, DWORD, DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT)(f, a, b, c, d, e, g, h) : 0;
}
DWORD __stdcall proxy_VerLanguageNameA(DWORD a, LPSTR b, DWORD c) {
    PROXY_PROLOGUE();
    return fp[13] ? PROXY_CALL(13, DWORD, DWORD, LPSTR, DWORD)(a, b, c) : 0;
}
DWORD __stdcall proxy_VerLanguageNameW(DWORD a, LPWSTR b, DWORD c) {
    PROXY_PROLOGUE();
    return fp[14] ? PROXY_CALL(14, DWORD, DWORD, LPWSTR, DWORD)(a, b, c) : 0;
}
BOOL __stdcall proxy_VerQueryValueA(LPCVOID a, LPCSTR b, LPVOID* c, PUINT d) {
    PROXY_PROLOGUE();
    return fp[15] ? PROXY_CALL(15, BOOL, LPCVOID, LPCSTR, LPVOID*, PUINT)(a, b, c, d) : FALSE;
}
BOOL __stdcall proxy_VerQueryValueW(LPCVOID a, LPCWSTR b, LPVOID* c, PUINT d) {
    PROXY_PROLOGUE();
    return fp[16] ? PROXY_CALL(16, BOOL, LPCVOID, LPCWSTR, LPVOID*, PUINT)(a, b, c, d) : FALSE;
}
} // extern "C"
