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
// If pattern scanning fails (e.g. after a game update), Phase 1 is used automatically.

#include "console.h"
#include "logging.h"
#include <windows.h>
#include <psapi.h>
#include <shlobj.h>
#include <queue>
#include <mutex>
#include <atomic>
#include <fstream>
#include <filesystem>
#include <sstream>

namespace fs = std::filesystem;

// =========================================================================
// Pattern Scanner
// =========================================================================

struct AOBPattern {
    std::vector<uint8_t> bytes;
    std::vector<bool> mask; // true = must match, false = wildcard
};

static AOBPattern parse_pattern(const char* pat) {
    AOBPattern p;
    std::istringstream iss(pat);
    std::string token;
    while (iss >> token) {
        if (token == "??" || token == "?") {
            p.bytes.push_back(0);
            p.mask.push_back(false);
        } else {
            p.bytes.push_back((uint8_t)strtoul(token.c_str(), nullptr, 16));
            p.mask.push_back(true);
        }
    }
    return p;
}

static uintptr_t scan_module(HMODULE mod, const char* pattern_str) {
    MODULEINFO info = {};
    if (!GetModuleInformation(GetCurrentProcess(), mod, &info, sizeof(info)))
        return 0;

    auto base = (const uint8_t*)info.lpBaseOfDll;
    auto size = info.SizeOfImage;
    auto pat = parse_pattern(pattern_str);

    if (pat.bytes.empty()) return 0;

    for (size_t i = 0; i + pat.bytes.size() <= size; i++) {
        bool match = true;
        for (size_t j = 0; j < pat.bytes.size(); j++) {
            if (pat.mask[j] && base[i + j] != pat.bytes[j]) {
                match = false;
                break;
            }
        }
        if (match) return (uintptr_t)(base + i);
    }
    return 0;
}

// =========================================================================
// Phase 2: Direct engine call types and state
// =========================================================================

// The engine's internal string object layout (Clausewitz std::string-like):
//   0x00: int32  — ref count / flags
//   0x08: int64  — unknown
//   0x10: char*  — data pointer (or inline SSO buffer for strings <= 15 chars)
//   0x20: int64  — length
//   0x28: int64  — capacity (0xF = SSO threshold)
// Total size: 0x30 bytes. We allocate 0x38 for safety.
struct EngineString {
    uint8_t data[0x38];
};

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
    return true;
}

// =========================================================================
// Phase 2: Direct engine call execution
// =========================================================================

static bool phase2_execute_batch(const std::vector<std::string>& commands) {
    for (const auto& cmd : commands) {
        EngineString buf = {};
        g_fnStringConstruct(&buf, cmd.c_str());
        g_fnExecuteCommand(&buf);
        g_fnStringDestruct(&buf);
    }
    ap_log("Console: Phase 2 — executed %zu command(s) directly", commands.size());
    return true;
}

// =========================================================================
// Shared command queue (unchanged from Phase 1)
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
        uintptr_t addrExecute   = scan_module(exe, PAT_EXECUTE_COMMAND);
        uintptr_t addrConstruct = scan_module(exe, PAT_STRING_CONSTRUCT);
        uintptr_t addrDestruct  = scan_module(exe, PAT_STRING_DESTRUCT);

        if (addrExecute && addrConstruct && addrDestruct) {
            g_fnExecuteCommand  = (ExecuteCommandFn)addrExecute;
            g_fnStringConstruct = (StringConstructFn)addrConstruct;
            g_fnStringDestruct  = (StringDestructFn)addrDestruct;
            g_phase2_ready = true;
            ap_log("Console: Phase 2 READY — direct engine calls");
            ap_log("  ExecuteCommand  @ %p", (void*)addrExecute);
            ap_log("  StringConstruct @ %p", (void*)addrConstruct);
            ap_log("  StringDestruct  @ %p", (void*)addrDestruct);
        } else {
            ap_log("Console: Phase 2 pattern scan failed:");
            ap_log("  ExecuteCommand  = %p %s", (void*)addrExecute,
                   addrExecute ? "OK" : "MISSING");
            ap_log("  StringConstruct = %p %s", (void*)addrConstruct,
                   addrConstruct ? "OK" : "MISSING");
            ap_log("  StringDestruct  = %p %s", (void*)addrDestruct,
                   addrDestruct ? "OK" : "MISSING");
            ap_log("Console: falling back to Phase 1 (SendInput)");
        }
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

int console_process_queue() {
    if (!g_ready || g_executing) return 0;
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
        ap_log("Console: execution failed, re-queuing %d command(s)", count);
        std::lock_guard<std::mutex> lock(g_queueMutex);
        for (auto it = batch.rbegin(); it != batch.rend(); ++it)
            g_commandQueue.push(*it);
        return 0;
    }
    return count;
}
