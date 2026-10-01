# DLL Bridge Architecture

Proxy DLL (version.dll) loaded into stellaris.exe. Provides a named pipe
server for the Python client to send console commands, and executes them
on the game's main thread.

## Initialization

1. DllMain: opens the log (next to the DLL) and nothing else. No
   LoadLibrary, no threads — both are unsafe under the loader lock.
2. First proxied call (any of the 17 version.dll exports): lazily loads
   the real `System32\version.dll` (InitOnceExecuteOnce) and starts the
   deferred-init thread (InterlockedCompareExchange, first call wins).
   If the real DLL can't be loaded the proxied functions return
   FALSE/0 instead of aborting the game.
3. Deferred thread (after 3 s, wrapped in SEH so a fault is logged):
   console_init → bridge_start → find the game window → subclass its
   WndProc and arm a 200 ms timer.

Window discovery prefers the visible top-level window titled "Stellaris";
after 20 s it accepts any visible non-console top-level window of the
process so a title change can't silently disable the bridge.

## Command Execution

### Phase 2 — Direct Engine Call (preferred)

Three internal Stellaris functions are located by AOB pattern scanning:

1. **StringConstruct** — builds the engine's internal string from a C string
2. **ExecuteCommand** — parses and dispatches a console command (same
   function the game's TweakerGUI debug panel uses)
3. **StringDestruct** — frees the engine string

Phase 2 is enabled only if all of the following hold, otherwise the DLL
falls back to Phase 1 and says why in the log:

- each pattern matches **exactly once**, scanning only the executable
  PE sections of stellaris.exe (`scanner.h`). An ambiguous pattern after
  a game update is treated as "not found" — calling the wrong function
  with an engine string is a guaranteed crash;
- a **round-trip self-test** of StringConstruct/StringDestruct on a short
  (inline) and a long (heap) string reproduces the expected object
  layout (MSVC std::string at +0x10: data, size at +0x20, capacity at
  +0x28).

Commands run on the game thread: the 200 ms WM_TIMER drains the queue,
and FLUSH from the pipe thread is marshalled with SendMessageTimeout
(5 s, below the client's 10 s pipe timeout, so a busy game thread yields
"queued" rather than a client-side timeout). Each command runs inside
SEH; an exception is logged with the offending command and counted, and
the batch is never re-queued (the same command would throw again).

### Phase 1 — SendInput Fallback

If Phase 2 is unavailable:

1. Commands are written to `ap_bridge_commands.txt` in the user dir
2. Alt-key trick for reliable SetForegroundWindow
3. SendInput: grave → backspace → "run ap_bridge_commands.txt" → Enter → grave
4. Previous foreground window restored; failures back off exponentially

Visible and fragile, but survives engine updates.

## Protocol

```
EFFECT <script>     → OK                       (queued as "effect <script>")
EVENT <id>          → OK                       (queued as "event <id>")
RAW <command>       → OK
BATCH <a>|<b>|<c>   → OK BATCH 3
FLUSH               → OK FLUSHED <n>           (-1 = still queued; the timer will run it)
PING                → PONG READY | PONG NOT_READY
STATUS              → STATUS mode=phase2|phase1|none ready=1 queued=0 executed=12 failed=0
```

The Python client (`client/pipe_client.py`) exposes STATUS as
`PipeClient.status()`. The bridge logs the mode once per game session and
warns when the SendInput fallback is active; the dashboard's Test Pipe
shows the same.

## Logging

`archipelago_dll.log` is written next to version.dll (i.e. next to
stellaris.exe) regardless of the process's working directory, and is
rotated to `.old` above 2 MB.

## AOB Patterns

Patterns are derived from Ghidra analysis of stellaris.exe. If a game
update breaks them, only the PAT_* strings in console.cpp need updating —
find the same functions in the new binary and rebuild the signatures.
The log tells you which one failed and whether it was missing or
ambiguous.

## Build and test

```
cmake -B build -S . -A x64
cmake --build build --config Release

# with tests
cmake -B build-test -S . -A x64 -DBUILD_TESTING=ON
cmake --build build-test --config Release
build-test\Release\scanner_test.exe            # pattern scanner unit test
python ..\scripts\check_dll_pipe.py            # pipe protocol via a host process
```

Refresh `prebuilt/version.dll` from `build/Release/version.dll` after
any change under `src/`.
