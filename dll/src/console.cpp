// console.cpp — Phase 2: Direct engine call with Phase 1 (SendInput) fallback
//
// Phase 2 finds three internal Stellaris functions via AOB pattern scanning:
//   1. StringConstruct — builds the engine's internal string object from a C string
//   2. ExecuteCommand  — parses and executes a console command string
//   3. StringDestruct  — frees the internal string object
//
// The call sequence mirrors what the game's own TweakerGUI debug panel does:
//   StringConstruct(buf, "effect ap_grant_something = yes");
//   ExecuteCommand(buf);
//   StringDestruct(buf);
//
// Phase 2 is only enabled when every pattern matches exactly once inside an
// executable section AND the two string functions pass a round-trip
// self-test on a short (inline) and a long (heap) string. Anything less and
// the DLL falls back to Phase 1 rather than risk calling the wrong function.

#include "console.h"
#include "logging.h"
#include "scanner.h"
#include <windows.h>
#include <shlobj.h>
#include <queue>
#include <mutex>
#include <atomic>
#include <fstream>
#include <filesystem>

namespace fs = std::filesystem;

// =========================================================================
// Phase 2: Direct engine call types and state
// =========================================================================

// The engine's internal string object. Offsets 0x10..0x30 are an MSVC
// std::string (inline buffer or heap pointer at 0x10, size at 0x20,
// capacity at 0x28 — 0xF while the inline buffer is in use), preceded by
// a 16-byte header. Total 0x30 bytes; we allocate 0x38 for safety.
struct EngineString {
    uint8_t data[0x38];
};
static const size_t ES_DATA = 0x10, ES_SIZE = 0x20, ES_CAPACITY = 0x28;
static const uint64_t ES_SSO_CAPACITY = 0xF;

// Function signatures (x64 __fastcall, RCX = first param, RDX = second param):
//   StringConstruct: RCX = EngineString*, RDX = const char*
//   ExecuteCommand:  RCX = EngineString*
//   StringDestruct:  RCX = EngineString*
using StringConstructFn = void* (__fastcall*)(void* buf, const char* text);
using ExecuteCommandFn  = void  (__fastcall*)(void* buf);
using StringDestructFn  = void  (__fastcall*)(void* buf);

static StringConstructFn g_fnStringConstruct = nullptr;
static ExecuteCommandFn  g_fnExecuteCommand  = nullptr;
static StringDestructFn  g_fnStringDestruct  = nullptr;
static bool g_phase2_ready = false;

// Counters for STATUS.
static std::atomic<long> g_executed{0};
static std::atomic<long> g_failed{0};

// AOB Patterns — derived from Stellaris binary analysis via Ghidra.
// Wildcards (??) cover bytes that may change between game versions:
// RIP-relative offsets, stack frame sizes, and local variable offsets.

// FUN_1415d2860 — ExecuteCommand (debug panel command executor)
// Loads the console singleton internally, logs the command, then dispatches it.
static const char* PAT_EXECUTE_COMMAND =
    "48 89 5C 24 08 "   // MOV [RSP+8], RBX
    "48 89 7C 24 18 "   // MOV [RSP+0x18], RDI
    "55 "               // PUSH RBP
    "48 8D 6C 24 ?? "   // LEA RBP, [RSP-??]
    "48 81 EC ?? ?? ?? ?? " // SUB RSP, ??
    "48 8B F9 "         // MOV RDI, RCX
    "33 C0 "            // XOR EAX, EAX
    "89 45 ?? "         // MOV [RBP+??], EAX
    "48 8B 1D ?? ?? ?? ??"; // MOV RBX, [console_singleton]

// FUN_141b07c30 — StringConstruct (builds engine string from C string)
// Initializes the string struct and calls into the string assign function.
static const char* PAT_STRING_CONSTRUCT =
    "40 53 "            // PUSH RBX
    "48 83 EC 20 "      // SUB RSP, 0x20
    "33 C0 "            // XOR EAX, EAX
    "48 C7 41 28 0F 00 00 00 " // MOV [RCX+0x28], 0xF  (SSO capacity)
    "48 89 41 10 "      // MOV [RCX+0x10], RAX
    "48 8B D9 "         // MOV RBX, RCX
    "88 41 10 "         // MOV [RCX+0x10], AL
    "49 C7 C0 FF FF FF FF"; // MOV R8, -1  (strlen sentinel)

// FUN_14014c6e0 — StringDestruct (frees engine string)
// Checks if heap-allocated (capacity >= 0x10), frees if needed, resets to SSO state.
static const char* PAT_STRING_DESTRUCT =
    "40 53 "            // PUSH RBX
    "48 83 EC 20 "      // SUB RSP, 0x20
    "48 83 79 28 10 "   // CMP [RCX+0x28], 0x10  (capacity vs SSO threshold)
    "48 8B D9 "         // MOV RBX, RCX
    "72 ?? "            // JC short (skip free if SSO)
    "83 39 01 "         // CMP [RCX], 1  (ref count check)
    "74 ??";            // JZ short (skip free if shared)

// =========================================================================
// Phase 1: SendInput fallback (original implementation)
// =========================================================================

static const WORD SC_GRAVE = 0x29, SC_ENTER = 0x1C, SC_BACKSPACE = 0x0E;
static fs::path g_userDir;
static const char* CMD_FILENAME = "ap_bridge_commands.txt";

static void send_scan_key(WORD sc, bool up = false) {
    INPUT inp = {};
    inp.type = INPUT_KEYBOARD;
    inp.ki.wScan = sc;
    inp.ki.dwFlags = KEYEVENTF_SCANCODE | (up ? KEYEVENTF_KEYUP : 0);
    SendInput(1, &inp, sizeof(INPUT));
}
static void press_scancode(WORD sc) { send_scan_key(sc, false); send_scan_key(sc, true); }

static void type_unicode_string(const std::string& text) {
    std::vector<INPUT> events;
    events.reserve(text.size() * 2);
    for (char ch : text) {
        INPUT d = {}, u = {};
        d.type = u.type = INPUT_KEYBOARD;
        d.ki.wScan = u.ki.wScan = (WORD)ch;
        d.ki.dwFlags = KEYEVENTF_UNICODE;
        u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        events.push_back(d);
        events.push_back(u);
    }
    if (!events.empty()) SendInput((UINT)events.size(), events.data(), sizeof(INPUT));
}

static bool write_command_file(const std::vector<std::string>& commands) {
    fs::path filepath = g_userDir / CMD_FILENAME;
    std::ofstream ofs(filepath, std::ios::trunc);
    if (!ofs.is_open()) {
        ap_log("Console: failed to write %s", filepath.string().c_str());
        return false;
    }
    for (const auto& cmd : commands) ofs << cmd << "\n";
    ofs.close();
    return true;
}

static bool find_user_dir() {
    PWSTR docs = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_Documents, 0, nullptr, &docs))) {
        ap_log("Console: SHGetKnownFolderPath failed");
        return false;
    }
    g_userDir = fs::path(docs) / "Paradox Interactive" / "Stellaris";
    CoTaskMemFree(docs);
    if (!fs::exists(g_userDir)) {
        ap_log("Console: user dir not found: %s", g_userDir.string().c_str());
        return false;
    }
    return true;
}

static bool phase1_execute_batch(const std::vector<std::string>& commands) {
    if (commands.empty()) return true;
    if (!write_command_file(commands)) return false;

    HWND fg = GetForegroundWindow();
    HWND game = nullptr;
    EnumWindows([](HWND hwnd, LPARAM lp) -> BOOL {
        DWORD pid; GetWindowThreadProcessId(hwnd, &pid);
        if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd)) return TRUE;
        char title[256]; GetWindowTextA(hwnd, title, sizeof(title));
        if (strstr(title, "Stellaris")) {
            char cls[256]; GetClassNameA(hwnd, cls, sizeof(cls));
            if (strcmp(cls, "ConsoleWindowClass") != 0) {
                *reinterpret_cast<HWND*>(lp) = hwnd;
                return FALSE;
            }
        }
        return TRUE;
    }, reinterpret_cast<LPARAM>(&game));

    if (!game) { ap_log("Console: WARNING — game window not found"); return false; }

    static const int CONSOLE_OPEN_MS = 150, BACKSPACE_MS = 30,
                     POST_TYPE_MS = 30, POST_ENTER_MS = 80, CONSOLE_CLOSE_MS = 80;

    keybd_event(VK_MENU, 0, 0, 0);
    keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0);
    SetForegroundWindow(game);
    Sleep(80);
    if (GetForegroundWindow() != game) {
        keybd_event(VK_MENU, 0, 0, 0);
        keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0);
        BringWindowToTop(game);
        SetForegroundWindow(game);
        Sleep(80);
    }
    if (GetForegroundWindow() != game) {
        ap_log("Console: ERROR — could not focus game");
        return false;
    }

    press_scancode(SC_GRAVE); Sleep(CONSOLE_OPEN_MS);
    press_scancode(SC_BACKSPACE); Sleep(BACKSPACE_MS);
    type_unicode_string(std::string("run ") + CMD_FILENAME); Sleep(POST_TYPE_MS);
    press_scancode(SC_ENTER); Sleep(POST_ENTER_MS);
    press_scancode(SC_GRAVE); Sleep(CONSOLE_CLOSE_MS);

    if (fg && fg != game) SetForegroundWindow(fg);
    ap_log("Console: Phase 1 — executed batch of %zu command(s) via SendInput",
           commands.size());
    g_executed += (long)commands.size();
    return true;
}

// =========================================================================
// Phase 2: locating and verifying the engine functions
// =========================================================================

static uintptr_t locate(HMODULE exe, const char* name, const char* pattern) {
    std::string where;
    ScanResult r = scan_module_unique(exe, pattern, &where);
    if (r.matches == 0) {
        ap_log("Console: %s pattern NOT FOUND", name);
        return 0;
    }
    if (r.matches > 1) {
        // Guessing here is how a game update turns into a crash on the
        // first delivered item. Refuse and fall back.
        ap_log("Console: %s pattern is AMBIGUOUS (%zu+ matches) — refusing to guess", name, r.matches);
        return 0;
    }
    ap_log("Console: %s @ %p (section %s)", name, (void*)r.address, where.c_str());
    return r.address;
}

// SEH-only helpers (no C++ objects with destructors: C2712).

// Round-trip a C string through StringConstruct/StringDestruct and check
// the object looks like the layout we assume. Returns false on mismatch
// or if either function throws.
static bool selftest_string_fns_seh(const char* text, size_t len) {
    EngineString buf = {};
    __try {
        g_fnStringConstruct(&buf, text);
        uint64_t size = *(const uint64_t*)(buf.data + ES_SIZE);
        uint64_t capacity = *(const uint64_t*)(buf.data + ES_CAPACITY);
        const char* data = capacity > ES_SSO_CAPACITY
            ? *(const char* const*)(buf.data + ES_DATA)
            : (const char*)(buf.data + ES_DATA);
        bool ok = size == len && capacity >= len && data != nullptr
                  && memcmp(data, text, len) == 0 && data[len] == 0;
        g_fnStringDestruct(&buf);
        return ok;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

static bool execute_one_seh(const char* cmd, DWORD* code) {
    EngineString buf = {};
    __try {
        g_fnStringConstruct(&buf, cmd);
        g_fnExecuteCommand(&buf);
        g_fnStringDestruct(&buf);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        *code = GetExceptionCode();
        // Do not call StringDestruct on a possibly-uninitialized buf.
        // Small leak per crashed command, but safer than a secondary
        // fault inside the destructor.
        return false;
    }
}

static bool phase2_selftest() {
    // Short string: inline (SSO) path. Long string: heap path, which is
    // the one every real console command takes.
    static const char* SHORT_TEXT = "ap";
    static const char* LONG_TEXT = "archipelago bridge self-test string, longer than sso";
    if (!selftest_string_fns_seh(SHORT_TEXT, strlen(SHORT_TEXT))) {
        ap_log("Console: string self-test FAILED on the inline (short) path");
        return false;
    }
    if (!selftest_string_fns_seh(LONG_TEXT, strlen(LONG_TEXT))) {
        ap_log("Console: string self-test FAILED on the heap (long) path");
        return false;
    }
    ap_log("Console: string construct/destruct self-test passed");
    return true;
}

static bool phase2_execute_batch(const std::vector<std::string>& commands) {
    int succeeded = 0;
    int crashed = 0;
    for (const auto& cmd : commands) {
        DWORD code = 0;
        // SEH around the engine call. ExecuteCommand can crash if the
        // command requires game state that doesn't exist (e.g.
        // set_country_flag at the main menu has no country scope and
        // dereferences null). SEH here means we get a log line naming
        // the offending command instead of a silent process death.
        // CAVEAT: catching engine exceptions can leave game state
        // inconsistent; the next command might fail too, and a delayed
        // crash later is possible. This is strictly better than dying
        // immediately with no diagnostic, but it is not a substitute
        // for not sending bad commands in the first place — which is
        // why the bridge only delivers once the mod has reported in.
        if (execute_one_seh(cmd.c_str(), &code)) {
            succeeded++;
        } else {
            ap_log("Console: Phase 2 EXCEPTION 0x%08lX during command: %s", code, cmd.c_str());
            ap_log("  (likely cause: command requires save game state that "
                   "is not currently loaded, e.g. effect commands at the "
                   "main menu with no country scope)");
            crashed++;
        }
    }
    g_executed += succeeded;
    g_failed += crashed;
    ap_log("Console: Phase 2 — executed %d/%zu command(s) directly%s",
           succeeded, commands.size(),
           crashed ? " (some commands triggered exceptions, see above)" : "");
    // ALWAYS return true. The retry-on-failure logic in console_process_queue
    // was designed for Phase 1's SendInput failures (couldn't focus the game
    // window, etc.) which are genuinely transient. Phase 2 "failures" are
    // SEH-caught access violations from ExecuteCommand — these are NOT
    // transient. The same command in the same game state will crash
    // identically every tick. Re-queuing produces a 5Hz infinite loop of
    // exceptions until the bridge happens to send a different command or
    // the game state changes. The bridge owns the decision to re-send.
    return true;
}

// =========================================================================
// Shared command queue
// =========================================================================

static std::queue<std::string> g_commandQueue;
static std::mutex g_queueMutex;
static std::atomic<bool> g_executing{false}, g_ready{false};

// =========================================================================
// Public interface
// =========================================================================

bool console_init() {
    // Try Phase 2: pattern scan for engine functions
    HMODULE exe = GetModuleHandleA(nullptr);
    if (exe) {
        size_t nsec = executable_sections(exe).size();
        ap_log("Console: scanning %zu executable section(s) of the game image", nsec);
        uintptr_t addrExecute   = locate(exe, "ExecuteCommand", PAT_EXECUTE_COMMAND);
        uintptr_t addrConstruct = locate(exe, "StringConstruct", PAT_STRING_CONSTRUCT);
        uintptr_t addrDestruct  = locate(exe, "StringDestruct", PAT_STRING_DESTRUCT);

        if (addrExecute && addrConstruct && addrDestruct) {
            g_fnExecuteCommand  = (ExecuteCommandFn)addrExecute;
            g_fnStringConstruct = (StringConstructFn)addrConstruct;
            g_fnStringDestruct  = (StringDestructFn)addrDestruct;
            if (phase2_selftest()) {
                g_phase2_ready = true;
                ap_log("Console: Phase 2 READY — direct engine calls");
            } else {
                g_fnExecuteCommand = nullptr;
                g_fnStringConstruct = nullptr;
                g_fnStringDestruct = nullptr;
                ap_log("Console: Phase 2 disabled — engine string layout differs from "
                       "what this build expects (game update?)");
            }
        } else {
            ap_log("Console: Phase 2 pattern scan failed — the game binary has probably "
                   "changed; the PAT_* signatures in console.cpp need refreshing");
        }
        if (!g_phase2_ready) ap_log("Console: falling back to Phase 1 (SendInput)");
    }

    // Phase 1 setup (needed as fallback, or as primary if Phase 2 failed)
    if (!g_phase2_ready) {
        if (!find_user_dir()) {
            ap_log("Console: Phase 1 init failed (no user dir)");
            return false;
        }
    }

    g_ready = true;
    return true;
}

bool console_is_ready() { return g_ready; }

std::string console_status() {
    size_t queued;
    {
        std::lock_guard<std::mutex> lock(g_queueMutex);
        queued = g_commandQueue.size();
    }
    const char* mode = !g_ready ? "none" : (g_phase2_ready ? "phase2" : "phase1");
    char buf[160];
    snprintf(buf, sizeof(buf), "mode=%s ready=%d queued=%zu executed=%ld failed=%ld",
             mode, g_ready ? 1 : 0, queued, g_executed.load(), g_failed.load());
    return buf;
}

void console_queue_command(const std::string& command) {
    std::lock_guard<std::mutex> lock(g_queueMutex);
    g_commandQueue.push(command);
    ap_log("Console: queued: %s", command.c_str());
}

bool console_execute_batch(const std::vector<std::string>& commands) {
    if (commands.empty()) return true;

    if (g_phase2_ready) {
        return phase2_execute_batch(commands);
    } else {
        return phase1_execute_batch(commands);
    }
}

// Consecutive execution failures and the next tick we're allowed to
// retry at. Without backoff, a persistent failure (e.g. Phase 1 can't
// focus a backgrounded game) retried every 200ms WM_TIMER tick spams
// SendInput keystrokes into whatever app IS focused, 5 times a second.
static int g_failStreak = 0;
static ULONGLONG g_nextRetryTick = 0;

int console_process_queue() {
    if (!g_ready || g_executing) return 0;
    if (g_failStreak > 0 && GetTickCount64() < g_nextRetryTick) return 0;
    std::vector<std::string> batch;
    {
        std::lock_guard<std::mutex> lock(g_queueMutex);
        while (!g_commandQueue.empty()) {
            batch.push_back(g_commandQueue.front());
            g_commandQueue.pop();
        }
    }
    if (batch.empty()) return 0;
    int count = (int)batch.size();
    g_executing = true;
    bool ok = console_execute_batch(batch);
    g_executing = false;
    if (!ok) {
        g_failStreak++;
        // Exponential backoff: 1s, 2s, 4s, ... capped at 30s.
        int shift = g_failStreak - 1;
        if (shift > 5) shift = 5;
        ULONGLONG delay = 1000ULL << shift;
        if (delay > 30000ULL) delay = 30000ULL;
        g_nextRetryTick = GetTickCount64() + delay;
        ap_log("Console: execution failed (streak %d), re-queuing %d command(s), retry in %llu ms",
               g_failStreak, count, delay);
        // Re-queue in original order (queue is FIFO — pushing front-first
        // preserves order).
        std::lock_guard<std::mutex> lock(g_queueMutex);
        for (const auto& cmd : batch)
            g_commandQueue.push(cmd);
        return 0;
    }
    g_failStreak = 0;
    return count;
}
