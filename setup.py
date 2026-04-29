"""Stellaris x Archipelago — Setup & Run

One script to install, build, test, and play.

Usage:
    python setup.py install         Install the Stellaris mod
    python setup.py build-dll       Build the DLL (requires MSVC)
    python setup.py install-dll     Copy built DLL to Stellaris game folder
    python setup.py check-errors    Check error.log for mod issues
    python setup.py test            Send test items via DLL pipe
    python setup.py mock            Start mock AP server + bridge
    python setup.py play            Connect to a real AP server
    python setup.py status          Show what's installed and working
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR  # setup.py is at root
MOD_SRC = PROJECT_DIR / "mod-install"
CLIENT_DIR = PROJECT_DIR / "client"
DLL_DIR = PROJECT_DIR / "dll"


def find_stellaris_user_dir() -> Path:
    home = Path.home()
    for p in [
        home / "Documents" / "Paradox Interactive" / "Stellaris",
        home / "OneDrive" / "Documents" / "Paradox Interactive" / "Stellaris",
    ]:
        if p.exists():
            return p
    print("ERROR: Stellaris user directory not found.")
    print("Looked in:")
    print(f"  {home / 'Documents' / 'Paradox Interactive' / 'Stellaris'}")
    print(f"  {home / 'OneDrive' / 'Documents' / 'Paradox Interactive' / 'Stellaris'}")
    sys.exit(1)


def find_stellaris_game_dir() -> Path:
    """Try common Steam install locations."""
    candidates = [
        Path("C:/Program Files (x86)/Steam/steamapps/common/Stellaris"),
        Path("C:/Program Files/Steam/steamapps/common/Stellaris"),
        Path.home() / "Steam" / "steamapps" / "common" / "Stellaris",
        Path("D:/SteamLibrary/steamapps/common/Stellaris"),
    ]
    for p in candidates:
        if p.exists() and (p / "stellaris.exe").exists():
            return p
    return None


def cmd_install():
    """Install the Stellaris mod."""
    stellaris = find_stellaris_user_dir()
    mod_dir = stellaris / "mod" / "archipelago_multiworld"
    mod_file = stellaris / "mod" / "archipelago_multiworld.mod"

    print(f"Installing mod to: {mod_dir}")

    # Copy .mod descriptor
    shutil.copy2(MOD_SRC / "archipelago_multiworld.mod", mod_file)

    # Copy mod content
    if mod_dir.exists():
        shutil.rmtree(mod_dir)
    shutil.copytree(MOD_SRC / "archipelago_multiworld", mod_dir)

    file_count = sum(1 for _ in mod_dir.rglob("*") if _.is_file())
    print(f"  Copied {file_count} mod files")

    # Check DLL
    game_dir = find_stellaris_game_dir()
    if game_dir and (game_dir / "version.dll").exists():
        print(f"  DLL: found at {game_dir / 'version.dll'}")
    elif game_dir:
        print(f"  DLL: NOT found at {game_dir}")
        print(f"       Run: python setup.py build-dll && python setup.py install-dll")
    else:
        print(f"  DLL: Stellaris game directory not found automatically")
        print(f"       Copy dll/build/Release/version.dll to the Stellaris game folder")

    # Check Python deps
    try:
        import websocket
        print(f"  websocket-client: installed")
    except ImportError:
        try:
            import websockets
            print(f"  websockets: installed (sync mode)")
        except ImportError:
            print(f"  WebSocket library: NOT installed")
            print(f"       Run: pip install websocket-client")

    print(f"\nDone! Enable 'Archipelago Multiworld' in the Stellaris launcher.")
    print(f"Launch Stellaris with: -logall")


def cmd_build_dll():
    """Build the DLL with CMake + MSVC."""
    if sys.platform != "win32":
        print("DLL build requires Windows + MSVC"); return

    build_dir = DLL_DIR / "build"
    build_dir.mkdir(exist_ok=True)

    print("Configuring with CMake...")
    r = subprocess.run(
        ["cmake", "..", "-G", "Visual Studio 17 2022", "-A", "x64"],
        cwd=build_dir, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"CMake configure failed:\n{r.stderr}")
        return

    print("Building...")
    r = subprocess.run(
        ["cmake", "--build", ".", "--config", "Release"],
        cwd=build_dir, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"Build failed:\n{r.stderr}")
        return

    dll_path = build_dir / "Release" / "version.dll"
    if dll_path.exists():
        print(f"  Built: {dll_path} ({dll_path.stat().st_size} bytes)")
        print(f"  Run: python setup.py install-dll")
    else:
        print(f"  Build output not found at {dll_path}")


def cmd_install_dll():
    """Copy built DLL to Stellaris game folder."""
    dll_path = DLL_DIR / "build" / "Release" / "version.dll"
    if not dll_path.exists():
        print(f"DLL not found at {dll_path}")
        print(f"Run: python setup.py build-dll"); return

    game_dir = find_stellaris_game_dir()
    if not game_dir:
        print("Stellaris game directory not found automatically.")
        print(f"Copy {dll_path} to your Stellaris game folder manually."); return

    dest = game_dir / "version.dll"
    shutil.copy2(dll_path, dest)
    print(f"  Installed: {dest}")


def cmd_configure(game_dir=None):
    """Scan techs and open the dashboard configurator."""
    # Step 1: scan if no config exists
    stellaris = find_stellaris_user_dir()
    config_path = stellaris / "ap_tech_config.json"

    if not config_path.exists():
        print("No config found. Scanning game files first...")
        sys.path.insert(0, str(CLIENT_DIR))
        from tech_scanner import cmd_scan
        cmd_scan(game_dir)

    if config_path.exists():
        print(f"\nConfig: {config_path}")
    else:
        print("Could not create config. Run: python client/tech_scanner.py scan --game-dir <path>")
        return

    # Step 2: launch dashboard
    print(f"\nLaunching dashboard for tech configuration...")
    print(f"  Go to the 'Tech Config' tab to toggle techs on/off")
    print(f"  Then click 'Apply & Save' to generate mod overrides")
    import subprocess
    subprocess.Popen([sys.executable, str(PROJECT_DIR / "dashboard.py")])


def cmd_apply_config(game_dir=None):
    """Apply tech config to regenerate mod overrides."""
    sys.path.insert(0, str(CLIENT_DIR))
    from tech_scanner import cmd_apply
    cmd_apply(game_dir)


def cmd_check_errors():
    """Show mod loading errors from error.log."""
    stellaris = find_stellaris_user_dir()
    error_log = stellaris / "logs" / "error.log"
    if not error_log.exists():
        print("error.log not found. Start a game first."); return

    with open(error_log, "r", encoding="utf-8", errors="replace") as f:
        errors = [l.strip() for l in f if "ap_" in l.lower() or "archipelago" in l.lower()]

    if errors:
        print(f"Found {len(errors)} AP-related error(s):\n")
        for err in errors:
            print(f"  {err}")
    else:
        print("No AP-related errors found in error.log!")


def cmd_test():
    """Send test items via the DLL pipe."""
    if sys.platform != "win32":
        print("Pipe test requires Windows"); return

    sys.path.insert(0, str(CLIENT_DIR))
    from pipe_client import create_pipe_client

    p = create_pipe_client()
    if not p.connect():
        print("Could not connect to DLL pipe. Is Stellaris running with the DLL?"); return

    print(f"Connected: {p.ping()}\n")
    tests = [
        ("Energy +1000", "add_resource = { energy = 1000 }"),
        ("Minerals +500", "add_resource = { minerals = 500 }"),
        ("Progressive Ship Class", "ap_grant_progressive_ship_class = yes"),
    ]
    for name, effect in tests:
        p.send_effect(effect)
        print(f"  {name}")
    flushed = p.flush_commands()
    print(f"\nFlushed {flushed} command(s). Check in-game!")
    p.disconnect()


def cmd_mock():
    """Start mock AP server + bridge for local testing."""
    sys.path.insert(0, str(CLIENT_DIR))

    # Install mod first
    cmd_install()

    # Generate test AP techs
    print("\nGenerating test AP techs for mock session...")
    from slot_generator import generate_mod_files
    stellaris = find_stellaris_user_dir()
    mod_dir = stellaris / "mod" / "archipelago_multiworld"

    test_slots = [
        {"location_id": 7472000, "location_name": "Survey 5 Systems",
         "item_name": "Mothwing Cloak", "player_name": "Alice",
         "game": "Hollow Knight", "classification": "progression",
         "is_own_item": False, "location_type": "milestone"},
        {"location_id": 7474010, "location_name": "Research Robotic Workers",
         "item_name": "Mantis Claw", "player_name": "Alice",
         "game": "Hollow Knight", "classification": "progression",
         "is_own_item": False, "location_type": "tech"},
        {"location_id": 7474020, "location_name": "Research Droids",
         "item_name": "Crystal Heart", "player_name": "Alice",
         "game": "Hollow Knight", "classification": "progression",
         "is_own_item": False, "location_type": "tech"},
        {"location_id": 7472030, "location_name": "Enter a Wormhole",
         "item_name": "Hermes Boots", "player_name": "Bob",
         "game": "Terraria", "classification": "useful",
         "is_own_item": False, "location_type": "tech"},
        {"location_id": 7472200, "location_name": "Colonize 1 Planet",
         "item_name": "Progressive Ship Class", "player_name": "You",
         "game": "Stellaris", "classification": "progression",
         "is_own_item": True, "location_type": "milestone"},
    ]
    generate_mod_files(test_slots, mod_dir)

    print(f"\n{'='*60}")
    print("READY TO TEST")
    print(f"{'='*60}")
    print(f"\n1. Start Stellaris with -logall, enable the mod, start a game")
    print(f"2. In another terminal, run:")
    print(f"   cd client && python mock_ap_server.py")
    print(f"3. In another terminal, run:")
    print(f"   cd client && python ap_bridge.py --server localhost:38281 --slot Stellaris")
    print(f"4. In the mock server, type: ship / cache / trap")


def cmd_play(server: str, slot: str, password: str = ""):
    """Connect to a real AP server."""
    sys.path.insert(0, str(CLIENT_DIR))

    # Install mod
    cmd_install()

    print(f"\nConnecting to {server} as '{slot}'...")
    print(f"The bridge will auto-generate AP techs on connect.")
    print(f"After it says 'DYNAMIC TECHS GENERATED', restart Stellaris.\n")

    # Run the bridge
    os.chdir(CLIENT_DIR)
    subprocess.run([
        sys.executable, "ap_bridge.py",
        "--server", server,
        "--slot", slot,
        "--password", password,
    ])


def cmd_uninstall():
    """Remove all installed files."""
    stellaris = find_stellaris_user_dir()
    game_dir = find_stellaris_game_dir()

    mod_dir = stellaris / "mod" / "archipelago_multiworld"
    mod_file = stellaris / "mod" / "archipelago_multiworld.mod"

    if mod_dir.exists():
        shutil.rmtree(mod_dir)
        print(f"  Removed: {mod_dir}")
    if mod_file.exists():
        mod_file.unlink()
        print(f"  Removed: {mod_file}")

    for name in ["ap_tech_config.json", "ap_tech_data.py", "ap_bridge_state.json", "ap_bridge_commands.txt"]:
        f = stellaris / name
        if f.exists():
            f.unlink()
            print(f"  Removed: {name}")

    if game_dir:
        dll = game_dir / "version.dll"
        log_f = game_dir / "archipelago_dll.log"
        if dll.exists():
            try:
                dll.unlink()
                print(f"  Removed: {dll}")
            except PermissionError:
                print(f"  Cannot delete {dll} - close Stellaris first")
        if log_f.exists():
            log_f.unlink()
            print(f"  Removed: {log_f}")

    print("\nUninstall complete.")


def cmd_status():
    """Show what's installed and working."""
    print("=== Stellaris AP Status ===\n")

    # User dir
    try:
        stellaris = find_stellaris_user_dir()
        print(f"  User dir:  {stellaris}")
    except SystemExit:
        print(f"  User dir:  NOT FOUND"); return

    # Mod installed?
    mod_dir = stellaris / "mod" / "archipelago_multiworld"
    mod_file = stellaris / "mod" / "archipelago_multiworld.mod"
    if mod_dir.exists() and mod_file.exists():
        file_count = sum(1 for _ in mod_dir.rglob("*") if _.is_file())
        print(f"  Mod:       installed ({file_count} files)")
    else:
        print(f"  Mod:       NOT installed")

    # Dynamic techs?
    dyn = mod_dir / "common" / "technology" / "ap_dynamic_techs.txt"
    if dyn.exists():
        import re
        with open(dyn) as f:
            count = len(re.findall(r'^ap_slot_\d+', f.read(), re.MULTILINE))
        print(f"  AP techs:  {count} generated")
    else:
        print(f"  AP techs:  none (connect to AP server to generate)")

    # DLL?
    game_dir = find_stellaris_game_dir()
    if game_dir:
        print(f"  Game dir:  {game_dir}")
        dll = game_dir / "version.dll"
        if dll.exists():
            print(f"  DLL:       installed ({dll.stat().st_size} bytes)")
        else:
            print(f"  DLL:       NOT installed")
    else:
        print(f"  Game dir:  not found automatically")

    # DLL built?
    built_dll = DLL_DIR / "build" / "Release" / "version.dll"
    if built_dll.exists():
        print(f"  DLL build: {built_dll}")
    else:
        print(f"  DLL build: not built yet")

    # Python deps
    deps = {"websocket-client": "websocket", "websockets": "websockets", "pywin32": "win32api"}
    for name, mod in deps.items():
        try:
            __import__(mod)
            print(f"  {name}: installed")
        except ImportError:
            print(f"  {name}: NOT installed")

    # State file
    state = stellaris / "ap_bridge_state.json"
    if state.exists():
        import json
        data = json.loads(state.read_text())
        print(f"  AP state:  {len(data.get('sent_checks', []))} checks, {len(data.get('processed_indices', []))} items")
    else:
        print(f"  AP state:  no saved state")

    # Error log
    error_log = stellaris / "logs" / "error.log"
    if error_log.exists():
        with open(error_log, "r", encoding="utf-8", errors="replace") as f:
            ap_errors = sum(1 for l in f if "ap_" in l.lower() or "archipelago" in l.lower())
        print(f"  Errors:    {ap_errors} AP-related in error.log")


def main():
    parser = argparse.ArgumentParser(
        description="Stellaris x Archipelago — Setup & Run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  install         Install the Stellaris mod
  build-dll       Build the DLL (requires CMake + MSVC)
  install-dll     Copy built DLL to Stellaris game folder
  configure       Scan techs and open the configurator UI
  apply-config    Regenerate mod files from tech config
  check-errors    Check error.log for mod issues
  test            Send test items via DLL pipe
  mock            Set up for local testing with mock server
  play            Connect to a real AP server
  status          Show installation status
  uninstall       Remove all installed files
        """
    )
    parser.add_argument("command",
        choices=["install", "build-dll", "install-dll", "configure", "apply-config",
                 "check-errors", "test", "mock", "play", "status", "uninstall"])
    parser.add_argument("--server", default="localhost:38281", help="AP server address")
    parser.add_argument("--slot", default="Stellaris", help="Slot name")
    parser.add_argument("--password", default="", help="Room password")
    parser.add_argument("--game-dir", type=Path, default=None, help="Stellaris game directory (for tech scanning)")
    args = parser.parse_args()

    if args.command == "install":
        cmd_install()
    elif args.command == "build-dll":
        cmd_build_dll()
    elif args.command == "install-dll":
        cmd_install_dll()
    elif args.command == "configure":
        cmd_configure(args.game_dir)
    elif args.command == "apply-config":
        cmd_apply_config(args.game_dir)
    elif args.command == "check-errors":
        cmd_check_errors()
    elif args.command == "test":
        cmd_test()
    elif args.command == "mock":
        cmd_mock()
    elif args.command == "play":
        cmd_play(args.server, args.slot, args.password)
    elif args.command == "status":
        cmd_status()
    elif args.command == "uninstall":
        cmd_uninstall()


if __name__ == "__main__":
    main()
