# DLL Bridge Architecture

Proxy DLL (version.dll) loaded into stellaris.exe. Provides a named pipe
server for the Python client to send commands.

## Initialization

1. DllMain: only proxy_init (load real version.dll, forward exports)
2. First proxy function call: triggers deferred init via InterlockedCompareExchange
3. Deferred thread (after 3s): console_init, bridge_start, WndProc hook

No threads are created in DllMain (causes crash under loader lock).

## Command Execution

### Phase 2 — Direct Engine Call (preferred)

On init, three internal Stellaris functions are located via AOB pattern scanning:

1. **StringConstruct** — builds the engine's internal string from a C string
2. **ExecuteCommand** — parses and dispatches a console command (same function
   the game's TweakerGUI debug panel uses)
3. **StringDestruct** — frees the engine string

Commands execute instantly on the game's main thread (via WM_TIMER), with no
console UI interaction, no focus stealing, and no timing dependencies.

### Phase 1 — SendInput Fallback

If pattern scanning fails (e.g. after a game update changes the binary), the
DLL falls back to the original approach:

1. Python client sends EFFECT/EVENT/BATCH/FLUSH via named pipe
2. DLL queues commands, on FLUSH: writes to file + SendInput
3. Alt-key trick for reliable SetForegroundWindow
4. SendInput: grave → backspace → "run ap_bridge_commands.txt" → Enter → grave
5. Restores previous foreground window

## Protocol

```
EFFECT <script>     → OK
EVENT <id>          → OK
BATCH <a>|<b>|<c>   → OK BATCH 3
FLUSH               → OK FLUSHED 2
PING                → PONG READY
```

## AOB Patterns

Patterns are derived from Ghidra analysis of stellaris.exe. If a game update
breaks them, only the PAT_* strings in console.cpp need updating — find the
same functions in the new binary using the Ghidra walkthrough and rebuild
the signatures.

## Build

cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
