# Phase 2 Hooking Research: Learning from Other Game Engine Modding Projects

## Executive Summary

No open-source project currently hooks into the Clausewitz engine's internal console or
effect-execution functions. This is uncharted territory for Stellaris. However, several
mature projects solve the *exact same problem* — calling internal game functions from an
injected DLL — for other native C++ engines. This document analyzes the most relevant
ones and distills their techniques into a practical plan for your Stellaris Archipelago mod.


## The Most Relevant Reference Projects

### 1. Phobos / Ares / Syringe (Red Alert 2: Yuri's Revenge)

**What it is:** A community engine extension for Red Alert 2 — an older RTS with a native
C++ engine, no modding API, and no source code. Exactly your situation.

**How it works:**
- **Syringe** is a loader that patches `gamemd.exe` at specific binary addresses, redirecting
  execution into DLLs (like `Phobos.dll`) at those addresses.
- **YRpp** is a set of C++ headers that describe the game's internal classes (units, houses,
  weapons, etc.) — essentially a reverse-engineered SDK.
- **Hooks** are declared with a macro: `DEFINE_HOOK(0x71A92A, MyFunction, 5)` — meaning
  "at address 0x71A92A, overwrite 5 bytes with a jump to MyFunction."
- The hook function can read CPU registers to access game objects, call internal game
  functions, modify state, and then return to the original code or skip it.

**Key lessons for you:**
- RA2 is a fixed binary (no updates), so hard-coded addresses work fine. Stellaris updates
  regularly, so you need pattern scanning instead.
- The `DEFINE_HOOK` approach is the gold standard for calling internal functions from
  injected code. The macro generates a trampoline that saves registers, calls your
  C++ function, and returns control to the game.
- YRpp demonstrates that you don't need full engine source — just enough reverse-engineered
  headers to describe the functions and structs you need to interact with.

**Links:**
- https://github.com/Phobos-developers/Phobos
- https://modenc.renegadeprojects.com/Contributing_to_Ares


### 2. ModEngine / ModEngine2 (Dark Souls III, Elden Ring, Sekiro)

**What it is:** A runtime injection library for FromSoftware's proprietary C++ engine.
Used as the foundation for virtually all Souls game mods, including the DS3 Archipelago
client.

**How it works:**
- Loads as a proxy DLL (`dinput8.dll`) — *exactly like your `version.dll` approach*.
- Uses **AOB (Array of Bytes) scanning** to find function addresses at runtime. This is the
  key difference from the RA2 approach: instead of hard-coding `0x71A92A`, you search for
  a byte pattern like `48 89 5C 24 ?? 48 89 74 24 ?? 57 48 83 EC 30` that uniquely
  identifies the function's prologue.
- Hooks are installed using **Microsoft Detours** or inline patching — overwriting the
  first few instructions of the target function with a jump to your code.
- The original ModEngine (v1) used hard-coded addresses, but v1.13+ switched to AOB scans
  for all function hooks, described as "greatly improving general compatibility" across
  game patches. ModEngine2 continues this pattern.

**Key lessons for you:**
- **AOB scanning is the right approach for Stellaris** because the game updates regularly.
  A well-chosen byte signature will survive most patches (compiler options and surrounding
  code usually don't change).
- Proxy DLL loading (the technique you already use) is the standard injection method in
  this ecosystem too. You're already on the right track.
- ModEngine2 includes ScyllaHide for anti-debug evasion — you won't need this since
  Stellaris has no anti-debug/anti-cheat (unlike Souls games with Easy Anti-Cheat).

**Links:**
- https://github.com/soulsmods/ModEngine2
- https://www.nexusmods.com/darksouls3/mods/332


### 3. Dark Souls III Archipelago Client

**What it is:** The most directly relevant project — an Archipelago multiworld mod for a
native C++ game (FromSoftware engine), delivered as a single DLL.

**How it works:**
- Injects as `dinput8.dll` (proxy DLL, like your `version.dll`).
- Communicates with the AP server via WebSocket.
- **Directly manipulates game memory** to grant items, modify inventory, and detect
  location checks — no console automation, no SendInput.
- Uses known memory offsets (the DS3 AP client targets a specific game version, 1.15,
  and provides a downpatcher to ensure compatibility).
- Reads item pickup events by hooking the game's item acquisition function and checking
  if the picked-up item corresponds to an AP location.

**Key lessons for you:**
- This proves the Archipelago + DLL-injection-into-native-engine pattern works and ships
  to real users.
- Their approach of targeting a specific game version (with a downpatcher) is an
  alternative to AOB scanning. For Stellaris this is less practical because Paradox
  updates more frequently and players generally want to stay current.
- The DS3 client's biggest user-facing issue is the Windows console freezing — a problem
  your Phase 2 would eliminate entirely.

**Links:**
- https://github.com/Marechal-L/Dark-Souls-III-Archipelago-client


### 4. DS3RuntimeScripting

**What it is:** A DLL framework for runtime modding of Dark Souls III. Provides an
interface to install hooks into the game's memory and run scripts on the game's main
thread or asynchronously.

**Key lessons for you:**
- Demonstrates the pattern of queueing work and executing it on the main game thread,
  which is exactly what you need (and already do via WM_TIMER).
- Shows how to build a hook management system with install/uninstall lifecycle.

**Links:**
- https://github.com/AmySouls/DS3RuntimeScripting


## What None of These Projects Had to Do (But You Do)

All the above projects target games with either:
- A fixed, never-updated binary (RA2) — hard-code addresses
- A game where modders target a specific version (DS3 1.15) — hard-code addresses

Stellaris updates regularly, so you need **version-resilient function discovery**. This
means AOB/signature scanning, which ModEngine pioneered for Souls games.


## Recommended Architecture for Phase 2

Based on the patterns from all these projects, here's the concrete approach:

### Step 1: Identify the Target Function via Reverse Engineering

You need to find the internal function that the `effect` console command calls.

**Tools:** Ghidra (free) or IDA Pro, plus x64dbg for runtime verification.

**Approach:**
1. Load `stellaris.exe` in Ghidra. Let auto-analysis complete.
2. Search for the string `"effect"` in the defined strings panel.
3. Look for cross-references (xrefs) that cluster near other console command strings
   like `"event"`, `"run"`, `"observe"`, `"tweakergui"`.
4. These strings are typically used in a command registration table or dispatch function.
   The `effect` handler is your target.
5. The `effect` handler will parse the remaining command text as Clausewitz script and
   execute it in a scope (the player's country, usually).
6. Note: The `run` command handler is also interesting — it reads a file and executes
   each line as a console command. You could potentially call that instead, which would
   let you keep your existing file-based batching approach but without the SendInput.

**Verification with x64dbg:**
1. Attach to running Stellaris (Stellaris doesn't have anti-debug).
2. Set a breakpoint on the address you found in Ghidra.
3. Open the in-game console and type `effect log = "test123"`.
4. Breakpoint hits → inspect call stack, registers, arguments.
5. This tells you the function signature and calling convention.

### Step 2: Build the AOB Signature

Once you have the function address for the current version:

1. Copy the first ~20-30 bytes of the function.
2. Disassemble them — identify which bytes are:
   - **Fixed:** opcode bytes, register encodings → keep as-is
   - **Variable:** relative offsets, absolute addresses, immediate values that might
     change between builds → replace with `??` wildcards
3. Test: your AOB should match exactly once in the current `stellaris.exe`.
4. Test again: download a slightly older version of Stellaris from Steam's beta branches
   and verify the same AOB still matches.

**Example of building a signature:**

```
Original bytes:  48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 30 48 8B F2 48 8D 0D A7 C3 12 01
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^
                 Function prologue (stable)                           LEA with relative offset (variable)

Signature:       48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 30 48 8B F2 48 8D 0D ?? ?? ?? ??
```

### Step 3: Implement Pattern Scanner

The pattern scanner is a well-known utility. Add to your DLL project:

```cpp
#include <windows.h>
#include <psapi.h>
#include <vector>
#include <string>
#include <sstream>

struct Pattern {
    std::vector<uint8_t> bytes;
    std::vector<bool> mask;  // true = must match, false = wildcard
};

Pattern parse_pattern(const char* pat) {
    Pattern p;
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

uintptr_t scan_module(HMODULE mod, const char* pattern_str) {
    MODULEINFO info;
    if (!GetModuleInformation(GetCurrentProcess(), mod, &info, sizeof(info)))
        return 0;

    auto base = (const uint8_t*)info.lpBaseOfDll;
    auto size = info.SizeOfImage;
    auto pat = parse_pattern(pattern_str);

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
```

### Step 4: Call the Function (Thread-Safe)

The critical insight from all these projects: **game engine functions must be called
from the game's main thread.** Your existing `WM_TIMER` + `AP_WndProc` pattern already
runs on the main thread, so use that:

```cpp
// These are populated during console_init() via pattern scanning
static uintptr_t g_executeEffect = 0;    // Address of the effect handler
static uintptr_t g_gameState = 0;        // Address of game state / console singleton

// Function pointer type (you'll determine the exact signature via RE)
// Common Clausewitz patterns:
//   void __fastcall ExecuteConsoleCmd(void* console, const char* cmdline)
//   void __fastcall ExecuteEffect(void* scope, const std::string& script)
using ExecuteConsoleFn = void(__fastcall*)(void* instance, const char* cmdtext);
static ExecuteConsoleFn g_fnExecuteConsole = nullptr;

bool console_init() {
    // Pattern for the "effect" command handler (you'll fill this in)
    const char* PATTERN_EFFECT = "48 89 5C 24 ?? 48 89 74 24 ?? 57 48 83 EC ??";
    // Pattern for the console/game state singleton
    const char* PATTERN_GAMESTATE = "48 8B 0D ?? ?? ?? ?? 48 85 C9 74 ?? E8";

    HMODULE exe = GetModuleHandleA(nullptr);

    g_executeEffect = scan_module(exe, PATTERN_EFFECT);
    if (!g_executeEffect) {
        ap_log("Console Phase 2: pattern scan FAILED — falling back to Phase 1");
        return phase1_console_init();
    }

    g_fnExecuteConsole = (ExecuteConsoleFn)g_executeEffect;
    ap_log("Console Phase 2: effect handler at %p", (void*)g_executeEffect);

    // Find game state pointer (for the 'this' / scope argument)
    // This requires chasing a pointer from a global — pattern-dependent
    g_gameState = find_game_state(exe);

    g_ready = true;
    ap_log("Console Phase 2: ready — direct execution enabled");
    return true;
}

bool console_execute_batch(const std::vector<std::string>& commands) {
    if (!g_fnExecuteConsole) {
        return phase1_execute_batch(commands);  // fallback to SendInput
    }

    void* scope = get_player_scope();  // resolve from g_gameState
    if (!scope) {
        ap_log("Console Phase 2: no player scope — game not loaded?");
        return false;
    }

    for (const auto& cmd : commands) {
        g_fnExecuteConsole(scope, cmd.c_str());
    }

    ap_log("Console Phase 2: executed %zu commands directly", commands.size());
    return true;
}
```

### Step 5: Keep Phase 1 as Fallback

This is what ModEngine did — they shipped hard-coded addresses initially, then moved to
AOB scans, and always kept error handling for when scans fail. Your architecture should:

1. Try Phase 2 (pattern scan → direct call)
2. If pattern scan fails (game updated, binary changed), log a warning and fall back
   to Phase 1 (SendInput)
3. The mod continues to work either way — Phase 2 is just smoother

This means a game update never *breaks* the mod, it just temporarily degrades the
experience until you update the pattern.


## Alternative Approach: Hook the `run` Command Path

Instead of finding and calling the `effect` handler directly, you could hook the `run`
command's file-reading path. Since you already write commands to a file
(`ap_bridge_commands.txt`), you could:

1. Find the function that `run <filename>` calls internally to open and execute each line
2. Call that function directly with your filename
3. This skips the console UI entirely but reuses the game's own command parsing

This might be easier to find (look for file I/O near the `"run"` string reference) and
would require less understanding of the effect execution scope/context.


## Tools You'll Need

| Tool | Purpose | Cost |
|------|---------|------|
| **Ghidra** | Disassembly / decompilation of stellaris.exe | Free (NSA) |
| **x64dbg** | Runtime debugging, breakpoints, register inspection | Free |
| **Cheat Engine** | Quick memory scanning, AOB search verification | Free |
| **HxD** or similar | Hex editor for quick byte-level verification | Free |

**Ghidra tips for Clausewitz:**
- The exe is large (~30-50MB). Auto-analysis takes 10-20 minutes.
- Search → For Strings → filter for "effect" with min length 5
- Use the decompiler view (Window → Decompile) — the pseudo-C output is very readable
  for modern x64 code and will help you understand function signatures.


## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Pattern breaks on game update | Medium | Phase 1 fallback; version-check on startup |
| Wrong scope/context pointer crashes the game | High during dev | Test in x64dbg first; save-scum |
| Calling from wrong thread corrupts state | High if done wrong | Use WM_TIMER (already do) |
| Stellaris adds anti-tamper in future | Very low | Paradox has never done this |
| Function signature changes (new params) | Low per update | Keep signature minimal; test on beta branches |


## Summary of Approach

Your current architecture is already well-suited for Phase 2. The changes are minimal:

1. `console.cpp` — replace the `SendInput` path in `console_execute_batch()` with a
   direct function call, discovered via pattern scanning at startup
2. `dllmain.cpp` — no changes needed (WM_TIMER already provides main-thread execution)
3. `bridge.cpp` — no changes needed (pipe protocol stays the same)
4. Python client — no changes needed at all

The hard part is the reverse engineering to find the right function and build a stable
signature. But once that's done, the code changes are small and the improvement is
dramatic: no console flashing, no focus stealing, no timing sensitivity, and commands
execute instantly.
