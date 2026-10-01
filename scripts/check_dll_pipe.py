"""Drive the bridge DLL's named-pipe server without Stellaris.

Builds nothing itself. Expects a test build of the DLL:

    cmake -B dll/build-test -S dll -A x64 -DBUILD_TESTING=ON
    cmake --build dll/build-test --config Release
    python scripts/check_dll_pipe.py

pipe_host.exe loads dll/build-test/Release/version.dll and calls a
proxied export, exactly like the game would, which starts the DLL's
deferred init and pipe server. This script then talks to it with the
real client/pipe_client.py: PING, STATUS, EFFECT, FLUSH, an unknown
command, and a second connection. The DLL log written next to the DLL
is checked for the init milestones.

What this proves: proxy forwarding, lazy loading of the real
version.dll, pipe framing, the protocol and its responses, and logging
to the DLL's own directory. What it cannot prove: Phase 2 pattern
matching and command execution inside the game.
"""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "dll" / "build-test" / "Release"
DLL = BUILD / "version.dll"
HOST = BUILD / "pipe_host.exe"
LOG = BUILD / "archipelago_dll.log"

sys.path.insert(0, str(REPO / "client"))


def main() -> int:
    if sys.platform != "win32":
        print("Windows only — skipped")
        return 0
    if not DLL.exists() or not HOST.exists():
        print(f"test build missing ({DLL}, {HOST}); see module docstring")
        return 1
    from pipe_client import PipeClient, HAS_WIN32
    if not HAS_WIN32:
        print("pywin32 not installed — cannot drive the pipe")
        return 1

    if LOG.exists():
        LOG.unlink()
    host = subprocess.Popen([str(HOST), str(DLL), "15"], stdout=subprocess.PIPE, text=True)
    failures = []

    def check(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failures.append(msg)

    try:
        # Deferred init sleeps 3s before starting the pipe server.
        client = PipeClient()
        client._retry_interval = 0.2
        deadline = time.time() + 12
        while time.time() < deadline and not client.connect():
            time.sleep(0.25)
        check(client.connected, f"pipe server came up ({client.last_error or 'connected'})")
        if not client.connected:
            return 1

        pong = client.ping()
        check(pong in ("PONG READY", "PONG NOT_READY"), f"PING -> {pong!r}")

        status = client.status()
        check(isinstance(status, dict) and "mode" in status and "queued" in status,
              f"STATUS -> {status!r}")
        check(status.get("mode") in ("phase1", "phase2", "none"), "STATUS mode is a known value")
        # Outside the game the engine patterns must not match the host exe.
        check(status.get("mode") != "phase2", "no false-positive Phase 2 match in a foreign process")

        check(client.send_effect("set_country_flag = ap_test"), "EFFECT accepted")
        check(client.send_effect("add_resource = { energy = 1 }"), "second EFFECT accepted")
        status2 = client.status()
        check(status2.get("queued") == "2", f"two commands queued (STATUS -> {status2!r})")

        flushed = client.flush_commands()
        # No game window in the host: dispatch returns -1 and the
        # commands stay queued. That is the documented behaviour.
        check(flushed == -1, f"FLUSH without a game window reports queued (-1), got {flushed}")

        raw = client.send_command("BOGUS")
        check(raw is not None and raw.startswith("ERROR"), f"unknown command -> {raw!r}")

        client.disconnect()
        client2 = PipeClient()
        client2._retry_interval = 0.2
        deadline = time.time() + 5
        while time.time() < deadline and not client2.connect():
            time.sleep(0.25)
        check(client2.connected, "server accepts a second client after the first disconnects")
        if client2.connected:
            check((client2.ping() or "").startswith("PONG"), "second client PING")
            client2.disconnect()
    finally:
        try:
            host.wait(timeout=30)
        except subprocess.TimeoutExpired:
            host.kill()
        out = host.stdout.read() if host.stdout else ""
        print("  host: " + out.strip().replace("\n", " | "))
        # A nonzero code here with "host exiting" printed means the DLL
        # broke process shutdown (e.g. a static std::thread aborting in
        # its destructor) — which in the game is a crash on every exit.
        check(host.returncode == 0,
              f"host exited cleanly with the DLL loaded (exit code {host.returncode})")

    log = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    check(LOG.exists(), f"DLL wrote its log next to itself ({LOG.name})")
    for needle in ("Proxy: real version.dll loaded", "Deferred init: starting",
                   "Bridge: starting pipe server", "Bridge: client connected"):
        check(needle in log, f"log contains '{needle}'")
    check("Phase 2 READY" not in log, "log does not claim Phase 2 in a foreign process")

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        print(log[-1500:])
        return 1
    print("\nDLL pipe protocol OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
