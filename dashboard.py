"""Stellaris x Archipelago Dashboard

One command to rule them all:
    python dashboard.py

Opens a browser dashboard that handles:
  - Tech scanning and configuration
  - Mod installation
  - DLL status check
  - Error log checking
  - Pipe testing
  - Mock server + bridge launch

No external web framework needed — uses Python's built-in http.server.
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from io import BytesIO

PORT = 19472  # AP-inspired port
SCRIPT_DIR = Path(__file__).parent.resolve()
CLIENT_DIR = SCRIPT_DIR / "client"
DLL_DIR = SCRIPT_DIR / "dll"

# Track running subprocesses
_processes = {
    "bridge": None,
    "mock": None,
}
_process_logs = {
    "bridge": [],
    "mock": [],
}

def _read_process_output(name, proc):
    """Background thread to read subprocess output."""
    for line in iter(proc.stdout.readline, ''):
        if line:
            _process_logs[name].append(line.strip())
            # Keep last 200 lines
            if len(_process_logs[name]) > 200:
                _process_logs[name] = _process_logs[name][-200:]
    proc.stdout.close()

sys.path.insert(0, str(CLIENT_DIR))


def find_stellaris_user_dir():
    home = Path.home()
    for p in [
        home / "Documents" / "Paradox Interactive" / "Stellaris",
        home / "OneDrive" / "Documents" / "Paradox Interactive" / "Stellaris",
    ]:
        if p.exists():
            return p
    return None


def find_stellaris_game_dir():
    candidates = [
        Path("C:/Program Files (x86)/Steam/steamapps/common/Stellaris"),
        Path("C:/Program Files/Steam/steamapps/common/Stellaris"),
        Path("D:/SteamLibrary/steamapps/common/Stellaris"),
        Path("D:/Steam/steamapps/common/Stellaris"),
        Path("E:/SteamLibrary/steamapps/common/Stellaris"),
    ]
    for p in candidates:
        if p.exists() and (p / "common" / "technology").exists():
            return p
    return None


class DashboardHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_dashboard()
        elif path == "/api/status":
            self._api_status()
        elif path == "/api/scan":
            self._api_scan()
        elif path == "/api/check-errors":
            self._api_check_errors()
        elif path == "/api/test-pipe":
            self._api_test_pipe()
        elif path == "/api/bridge-status":
            self._api_bridge_status()
        elif path == "/api/scan-milestones":
            self._api_scan_milestones()
        elif path == "/api/milestone-config":
            self._api_get_milestone_config()
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/install":
            self._api_install()
        elif path == "/api/apply-config":
            body = self._read_body()
            self._api_apply_config(body)
        elif path == "/api/uninstall":
            self._api_uninstall()
        elif path == "/api/build-dll":
            self._api_build_dll()
        elif path == "/api/install-dll":
            self._api_install_dll()
        elif path == "/api/start-bridge":
            body = self._read_body()
            self._api_start_bridge(body)
        elif path == "/api/stop-bridge":
            self._api_stop_bridge()
        elif path == "/api/start-mock":
            self._api_start_mock()
        elif path == "/api/stop-mock":
            self._api_stop_mock()
        elif path == "/api/apply-milestones":
            body = self._read_body()
            self._api_apply_milestones(body)
        elif path == "/api/bridge-status":
            self._api_bridge_status()
        else:
            self.send_error(404)

    def _serve_dashboard(self):
        html = DASHBOARD_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html))
        self.end_headers()
        self.wfile.write(html.encode())

    def _api_status(self):
        user_dir = find_stellaris_user_dir()
        game_dir = find_stellaris_game_dir()
        result = {
            "user_dir": str(user_dir) if user_dir else None,
            "game_dir": str(game_dir) if game_dir else None,
            "mod_installed": False,
            "mod_files": 0,
            "dll_installed": False,
            "dll_built": False,
            "config_exists": False,
            "config_randomized": 0,
            "config_total": 0,
            "dynamic_techs": 0,
            "ap_errors": 0,
            "websocket_lib": False,
            "pywin32": False,
        }

        if user_dir:
            mod_dir = user_dir / "mod" / "archipelago_multiworld"
            if mod_dir.exists():
                result["mod_installed"] = True
                result["mod_files"] = sum(1 for _ in mod_dir.rglob("*") if _.is_file())

            config = user_dir / "ap_tech_config.json"
            if config.exists():
                result["config_exists"] = True
                try:
                    data = json.loads(config.read_text())
                    techs = data.get("techs", data)
                    result["config_total"] = len(techs)
                    result["config_randomized"] = sum(1 for t in techs.values() if t.get("randomize"))
                except Exception:
                    pass

            dyn = mod_dir / "common" / "technology" / "ap_dynamic_techs.txt"
            if dyn.exists():
                import re
                result["dynamic_techs"] = len(re.findall(r'^ap_slot_\d+', dyn.read_text(), re.MULTILINE))

            err = user_dir / "logs" / "error.log"
            if err.exists():
                with open(err, "r", encoding="utf-8", errors="replace") as f:
                    result["ap_errors"] = sum(1 for l in f if "ap_" in l.lower() or "archipelago" in l.lower())

        if game_dir:
            result["dll_installed"] = (game_dir / "version.dll").exists()

        dll_build = SCRIPT_DIR / "dll" / "build" / "Release" / "version.dll"
        result["dll_built"] = dll_build.exists()

        try:
            import websocket
            result["websocket_lib"] = True
        except ImportError:
            try:
                import websockets
                result["websocket_lib"] = True
            except ImportError:
                pass

        try:
            import win32api
            result["pywin32"] = True
        except ImportError:
            pass

        self._json_response(result)

    def _api_scan(self):
        game_dir = find_stellaris_game_dir()
        if not game_dir:
            self._json_response({"error": "Stellaris game directory not found"}, 404)
            return

        try:
            from tech_scanner import parse_tech_files, auto_select_defaults
            techs = parse_tech_files(game_dir)
            techs = auto_select_defaults(techs)

            # Sort by area, tier, name
            sorted_techs = dict(sorted(
                techs.items(),
                key=lambda x: (x[1]["area"], x[1]["tier"], x[1]["key"])
            ))

            self._json_response({
                "total": len(sorted_techs),
                "randomized": sum(1 for t in sorted_techs.values() if t["randomize"]),
                "techs": sorted_techs,
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _api_install(self):
        try:
            user_dir = find_stellaris_user_dir()
            if not user_dir:
                self._json_response({"error": "Stellaris user dir not found"}, 404)
                return

            mod_src = SCRIPT_DIR / "mod-install"
            mod_dir = user_dir / "mod" / "archipelago_multiworld"
            mod_file = user_dir / "mod" / "archipelago_multiworld.mod"

            shutil.copy2(mod_src / "archipelago_multiworld.mod", mod_file)
            if mod_dir.exists():
                shutil.rmtree(mod_dir)
            shutil.copytree(mod_src / "archipelago_multiworld", mod_dir)

            count = sum(1 for _ in mod_dir.rglob("*") if _.is_file())
            self._json_response({"success": True, "files": count})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _api_apply_config(self, body):
        try:
            config_data = json.loads(body)
            techs = config_data.get("techs", config_data)

            user_dir = find_stellaris_user_dir()
            game_dir = find_stellaris_game_dir()
            if not user_dir or not game_dir:
                self._json_response({"error": "Dirs not found"}, 404)
                return

            # Save config
            config_path = user_dir / "ap_tech_config.json"
            config_path.write_text(json.dumps({
                "_help": "Tech randomization config",
                "techs": techs,
            }, indent=2))

            # Generate overrides
            from tech_scanner import generate_overrides, generate_vanilla_tech_data
            mod_dir = user_dir / "mod" / "archipelago_multiworld"
            blocked = generate_overrides(techs, game_dir, mod_dir)

            data_str = generate_vanilla_tech_data(techs)
            (user_dir / "ap_tech_data.py").write_text(data_str)

            self._json_response({
                "success": True,
                "blocked": len(blocked),
                "config_saved": str(config_path),
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _api_check_errors(self):
        user_dir = find_stellaris_user_dir()
        if not user_dir:
            self._json_response({"error": "User dir not found"}, 404)
            return

        err_log = user_dir / "logs" / "error.log"
        if not err_log.exists():
            self._json_response({"errors": [], "message": "No error.log found"})
            return

        errors = []
        with open(err_log, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "ap_" in line.lower() or "archipelago" in line.lower():
                    errors.append(line.strip())

        self._json_response({"errors": errors, "count": len(errors)})

    def _api_test_pipe(self):
        if sys.platform != "win32":
            self._json_response({"error": "Windows only"}, 400)
            return
        try:
            from pipe_client import create_pipe_client
            p = create_pipe_client()
            if not p.connect():
                self._json_response({"connected": False, "error": "Could not connect to DLL pipe"})
                return
            ping = p.ping()
            p.send_effect("add_resource = { energy = 500 }")
            flushed = p.flush_commands()
            p.disconnect()
            self._json_response({"connected": True, "ping": ping, "flushed": flushed})
        except Exception as e:
            self._json_response({"connected": False, "error": str(e)})


    def _api_build_dll(self):
        build_dir = DLL_DIR / "build"
        build_dir.mkdir(exist_ok=True)
        try:
            # Configure
            r = subprocess.run(
                ["cmake", "..", "-G", "Visual Studio 17 2022", "-A", "x64"],
                cwd=build_dir, capture_output=True, text=True, timeout=60
            )
            if r.returncode != 0:
                self._json_response({"error": f"CMake configure failed: {r.stderr[:500]}"}, 500)
                return
            # Build
            r = subprocess.run(
                ["cmake", "--build", ".", "--config", "Release"],
                cwd=build_dir, capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                self._json_response({"error": f"Build failed: {r.stderr[:500]}"}, 500)
                return
            dll = build_dir / "Release" / "version.dll"
            if dll.exists():
                self._json_response({"success": True, "path": str(dll), "size": dll.stat().st_size})
            else:
                self._json_response({"error": "Build output not found"}, 500)
        except FileNotFoundError:
            self._json_response({"error": "CMake not found. Install Visual Studio 2022 Build Tools."}, 500)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _api_install_dll(self):
        dll = DLL_DIR / "build" / "Release" / "version.dll"
        if not dll.exists():
            self._json_response({"error": "DLL not built yet. Click Build DLL first."}, 400)
            return
        game_dir = find_stellaris_game_dir()
        if not game_dir:
            self._json_response({"error": "Stellaris game directory not found"}, 404)
            return
        try:
            dest = game_dir / "version.dll"
            shutil.copy2(dll, dest)
            self._json_response({"success": True, "path": str(dest)})
        except PermissionError:
            self._json_response({"error": "Permission denied - close Stellaris first"}, 500)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _api_start_bridge(self, body):
        global _processes, _process_logs
        if _processes["bridge"] and _processes["bridge"].poll() is None:
            self._json_response({"error": "Bridge already running"}, 400)
            return
        try:
            params = json.loads(body) if body else {}
        except Exception:
            params = {}
        server = params.get("server", "localhost:38281")
        slot = params.get("slot", "Stellaris")
        password = params.get("password", "")
        _process_logs["bridge"] = []
        cmd = [sys.executable, str(CLIENT_DIR / "ap_bridge.py"),
               "--server", server, "--slot", slot]
        if password:
            cmd.extend(["--password", password])
        _processes["bridge"] = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=str(CLIENT_DIR)
        )
        threading.Thread(target=_read_process_output, args=("bridge", _processes["bridge"]), daemon=True).start()
        self._json_response({"success": True, "pid": _processes["bridge"].pid, "server": server, "slot": slot})

    def _api_stop_bridge(self):
        global _processes
        if _processes["bridge"] and _processes["bridge"].poll() is None:
            _processes["bridge"].terminate()
            _processes["bridge"].wait(timeout=5)
            self._json_response({"success": True})
        else:
            self._json_response({"error": "Bridge not running"}, 400)

    def _api_start_mock(self):
        global _processes, _process_logs
        if _processes["mock"] and _processes["mock"].poll() is None:
            self._json_response({"error": "Mock server already running"}, 400)
            return
        _process_logs["mock"] = []
        _processes["mock"] = subprocess.Popen(
            [sys.executable, str(CLIENT_DIR / "mock_ap_server.py")],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, stdin=subprocess.PIPE, cwd=str(CLIENT_DIR)
        )
        threading.Thread(target=_read_process_output, args=("mock", _processes["mock"]), daemon=True).start()
        self._json_response({"success": True, "pid": _processes["mock"].pid})

    def _api_stop_mock(self):
        global _processes
        if _processes["mock"] and _processes["mock"].poll() is None:
            _processes["mock"].terminate()
            _processes["mock"].wait(timeout=5)
            self._json_response({"success": True})
        else:
            self._json_response({"error": "Mock server not running"}, 400)

    def _api_scan_milestones(self):
        # The milestone_config tool was retired. Milestones are now defined
        # statically in the apworld (apworld/stellaris/locations.py) and
        # reflected in the mod's hand-maintained ap_check_detection.txt /
        # ap_bridge_log.txt files. This endpoint is kept as a no-op so the
        # dashboard UI doesn't 500.
        self._json_response({
            "milestones": [],
            "deprecated": True,
            "message": (
                "Milestone configuration is now hand-maintained. "
                "Edit apworld/stellaris/locations.py to change locations "
                "and update the matching senders in the mod's "
                "ap_bridge_log.txt and ap_check_detection.txt."
            ),
        })

    def _api_get_milestone_config(self):
        # See _api_scan_milestones above — milestone_config is retired.
        self._json_response({
            "milestones": [],
            "deprecated": True,
            "message": (
                "Milestone configuration is now hand-maintained. "
                "See apworld/stellaris/locations.py."
            ),
        })

    def _api_apply_milestones(self, body):
        # See _api_scan_milestones above — milestone_config is retired.
        self._json_response({
            "success": False,
            "deprecated": True,
            "message": (
                "Milestone generation is no longer automated. "
                "Edit apworld/stellaris/locations.py and the mod's "
                "ap_bridge_log.txt / ap_check_detection.txt by hand."
            ),
        }, 410)

    def _api_bridge_status(self):
        result = {}
        for name in ["bridge", "mock"]:
            proc = _processes.get(name)
            running = proc is not None and proc.poll() is None
            result[name] = {
                "running": running,
                "pid": proc.pid if running else None,
                "log": _process_logs.get(name, [])[-50:],  # last 50 lines
            }
        self._json_response(result)

    def _api_uninstall(self):
        removed = []
        errors = []
        user_dir = find_stellaris_user_dir()
        game_dir = find_stellaris_game_dir()

        if user_dir:
            # Remove mod
            mod_dir = user_dir / "mod" / "archipelago_multiworld"
            mod_file = user_dir / "mod" / "archipelago_multiworld.mod"
            if mod_dir.exists():
                shutil.rmtree(mod_dir)
                removed.append(f"Mod folder: {mod_dir}")
            if mod_file.exists():
                mod_file.unlink()
                removed.append(f"Mod descriptor: {mod_file}")

            # Remove config and state files
            for name in ["ap_tech_config.json", "ap_tech_data.py", "ap_bridge_state.json", "ap_bridge_commands.txt"]:
                f = user_dir / name
                if f.exists():
                    f.unlink()
                    removed.append(f"Config: {name}")

        if game_dir:
            dll = game_dir / "version.dll"
            log = game_dir / "archipelago_dll.log"
            if dll.exists():
                try:
                    dll.unlink()
                    removed.append(f"DLL: {dll}")
                except PermissionError:
                    errors.append(f"Cannot delete {dll} - Stellaris is probably running. Close it first.")
            if log.exists():
                log.unlink()
                removed.append(f"DLL log: {log}")

        self._json_response({
            "success": len(errors) == 0,
            "removed": removed,
            "errors": errors,
        })


DASHBOARD_HTML = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Stellaris AP Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background: #0a0e1a; color: #c0ccdd; font-family: 'Rajdhani', sans-serif; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1a2a40; border-radius: 4px; }
.header { padding: 20px 28px; border-bottom: 1px solid #1a2a40; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-family: 'Orbitron', sans-serif; font-size: 22px; color: #e0e8ff; letter-spacing: 2px; }
.header .sub { font-family: 'Orbitron'; font-size: 10px; letter-spacing: 3px; color: #4da6ff60; text-transform: uppercase; }
.tabs { display: flex; border-bottom: 1px solid #1a2a40; background: #0c1220; }
.tab { padding: 12px 24px; cursor: pointer; font-size: 14px; font-weight: 600; letter-spacing: 1px; color: #6880a0; border-bottom: 2px solid transparent; transition: all 0.2s; }
.tab:hover { color: #a0b0cc; }
.tab.active { color: #4da6ff; border-bottom-color: #4da6ff; }
.panel { padding: 24px 28px; }
.card { background: #0f1525; border: 1px solid #1a2a40; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card h3 { font-size: 16px; color: #e0e8ff; margin-bottom: 12px; letter-spacing: 1px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.stat { background: #0a0e1a; border: 1px solid #1a2a40; border-radius: 6px; padding: 14px; }
.stat .val { font-family: 'Orbitron'; font-size: 22px; color: #4da6ff; }
.stat .label { font-size: 11px; color: #6880a0; letter-spacing: 1px; margin-top: 4px; }
.stat.ok .val { color: #4dff99; }
.stat.warn .val { color: #ffb44d; }
.stat.err .val { color: #ff4d4d; }
.btn { padding: 10px 22px; border-radius: 6px; font-family: 'Rajdhani'; font-weight: 700; font-size: 14px; letter-spacing: 1px; cursor: pointer; border: 1px solid; transition: all 0.2s; }
.btn-primary { background: linear-gradient(135deg, #1a3a5a, #2a5a8a); border-color: #4da6ff40; color: #e0e8ff; }
.btn-success { background: linear-gradient(135deg, #1a5a3a, #2a8a5a); border-color: #4dff9940; color: #e0ffe8; }
.btn-warn { background: linear-gradient(135deg, #5a3a1a, #8a5a2a); border-color: #ffb44d40; color: #ffe8e0; }
.btn:hover { filter: brightness(1.2); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.log { background: #050810; border: 1px solid #1a2a40; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; color: #80a0c0; }
.log .err { color: #ff6666; }
.log .ok { color: #66ff99; }
.log .info { color: #66aaff; }
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.filters input, .filters select { padding: 8px 12px; background: #0a0e1a; border: 1px solid #1a2a40; border-radius: 6px; color: #c0ccdd; font-size: 13px; font-family: 'Rajdhani'; outline: none; }
.filters input { flex: 1; min-width: 200px; }
.tech-row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin-bottom: 2px; border-radius: 6px; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.tech-row:hover { background: #ffffff08; }
.tech-row.on { border-color: #4da6ff20; }
.tech-row.on.physics { background: #1a2a4a40; }
.tech-row.on.society { background: #2a1a3a40; }
.tech-row.on.engineering { background: #2a3a1a40; }
.check { width: 20px; height: 20px; border-radius: 4px; border: 2px solid #3a4a60; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 13px; font-weight: 900; }
.tech-row.on .check { border-color: #4da6ff; color: #4da6ff; }
.tech-row.on.society .check { border-color: #b44dff; color: #b44dff; }
.tech-row.on.engineering .check { border-color: #ffb44d; color: #ffb44d; }
.badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.actions { display: flex; gap: 10px; margin-top: 16px; }
select option { background: #0a0e1a; }
</style>
</head>
<body>
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.9/babel.min.js"></script>
<script type="text/babel">
const { useState, useEffect, useMemo, useCallback } = React;
const API = "";

function App() {
  const [tab, setTab] = useState("setup");
  const [status, setStatus] = useState(null);
  const [techs, setTechs] = useState(null);
  const [log, setLog] = useState([]);
  const [errors, setErrors] = useState(null);
  const [search, setSearch] = useState("");
  const [areaFilter, setAreaFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [loading, setLoading] = useState({});
  const [bridgeStatus, setBridgeStatus] = useState(null);
  const [bridgeServer, setBridgeServer] = useState("localhost:38281");
  const [bridgeSlot, setBridgeSlot] = useState("Stellaris");
  const [bridgePassword, setBridgePassword] = useState("");
  const [milestones, setMilestones] = useState(null);
  const [msSearch, setMsSearch] = useState("");
  const [msCatFilter, setMsCatFilter] = useState("all");

  const addLog = (msg, type="info") => setLog(prev => [...prev, {msg, type, t: Date.now()}]);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(API+"/api/status");
      const d = await r.json();
      setStatus(d);
    } catch(e) { addLog("Failed to fetch status: "+e, "err"); }
  }, []);

  useEffect(() => { fetchStatus(); }, []);
  useEffect(() => {
    const iv = setInterval(async () => {
      try { const r = await fetch(API+"/api/bridge-status"); setBridgeStatus(await r.json()); } catch(e) {}
    }, 2000);
    return () => clearInterval(iv);
  }, []);

  const doAction = async (name, url, opts={}) => {
    setLoading(p => ({...p, [name]: true}));
    addLog(`Running: ${name}...`);
    try {
      const r = await fetch(API+url, opts);
      const d = await r.json();
      if (d.error) { addLog(`${name}: ${d.error}`, "err"); }
      else { addLog(`${name}: Success!`, "ok"); }
      fetchStatus();
      return d;
    } catch(e) { addLog(`${name}: ${e}`, "err"); return null; }
    finally { setLoading(p => ({...p, [name]: false})); }
  };

  const scanTechs = async () => {
    const d = await doAction("Scan Techs", "/api/scan");
    if (d && d.techs) setTechs(d.techs);
  };

  const installMod = () => doAction("Install Mod", "/api/install", {method:"POST"});
  const testPipe = () => doAction("Test Pipe", "/api/test-pipe");

  const checkErrors = async () => {
    const d = await doAction("Check Errors", "/api/check-errors");
    if (d) setErrors(d.errors || []);
  };

  const applyConfig = async () => {
    if (!techs) { addLog("No tech config to apply", "err"); return; }
    await doAction("Apply Config", "/api/apply-config", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({techs}),
    });
  };

  const toggleTech = (key) => {
    setTechs(p => ({...p, [key]: {...p[key], randomize: !p[key].randomize}}));
  };

  const techList = useMemo(() => techs ? Object.values(techs) : [], [techs]);
  const filtered = useMemo(() => {
    return techList.filter(t => {
      if (search && !t.name.toLowerCase().includes(search.toLowerCase()) && !t.key.includes(search.toLowerCase())) return false;
      if (areaFilter !== "all" && t.area !== areaFilter) return false;
      if (tierFilter !== "all" && t.tier !== Number(tierFilter)) return false;
      return true;
    }).sort((a,b) => a.tier-b.tier || a.area.localeCompare(b.area) || a.name.localeCompare(b.name));
  }, [techList, search, areaFilter, tierFilter]);

  const stats = useMemo(() => {
    const rand = techList.filter(t=>t.randomize).length;
    return { total: techList.length, rand };
  }, [techList]);

  const bulkSet = (val) => {
    setTechs(p => {
      const next = {...p};
      filtered.forEach(t => { next[t.key] = {...next[t.key], randomize: val}; });
      return next;
    });
  };

  const S = ({val, label, type}) => (
    <div className={"stat "+(type||"")}>
      <div className="val">{val}</div>
      <div className="label">{label}</div>
    </div>
  );

  return (
    <div>
      <div className="header">
        <div>
          <div className="sub">Stellaris x Archipelago</div>
          <h1>Dashboard</h1>
        </div>
        <div style={{display:"flex",gap:12}}>
          {techs && <div style={{textAlign:"right",marginRight:8}}>
            <div style={{fontFamily:"Orbitron",fontSize:24,color:"#4da6ff"}}>{stats.rand}</div>
            <div style={{fontSize:11,color:"#6880a0"}}>/ {stats.total} TECHS</div>
          </div>}
        </div>
      </div>

      <div className="tabs">
        {["setup","bridge","techs","milestones","errors","log"].map(t => (
          <div key={t} className={"tab "+(tab===t?"active":"")} onClick={()=>setTab(t)}>
            {t==="setup"?"Setup":t==="bridge"?"Bridge":t==="techs"?"Tech Config":t==="milestones"?"Milestones":t==="errors"?"Errors":"Log"}
          </div>
        ))}
      </div>

      {tab === "setup" && (
        <div className="panel">
          <div className="card">
            <h3>System Status</h3>
            {status ? (
              <div className="stat-grid">
                <S val={status.user_dir ? "Found" : "Missing"} label="Stellaris User Dir" type={status.user_dir?"ok":"err"} />
                <S val={status.game_dir ? "Found" : "Not Found"} label="Game Directory" type={status.game_dir?"ok":"warn"} />
                <S val={status.mod_installed ? status.mod_files+" files" : "No"} label="Mod Installed" type={status.mod_installed?"ok":"warn"} />
                <S val={status.dll_installed ? "Yes" : "No"} label="DLL Installed" type={status.dll_installed?"ok":"warn"} />
                <S val={status.websocket_lib ? "Yes" : "No"} label="WebSocket Lib" type={status.websocket_lib?"ok":"err"} />
                <S val={status.config_exists ? status.config_randomized+"/"+status.config_total : "None"} label="Tech Config" type={status.config_exists?"ok":"warn"} />
                <S val={status.dynamic_techs || 0} label="AP Techs Generated" type={status.dynamic_techs?"ok":"warn"} />
                <S val={status.ap_errors} label="Mod Errors" type={status.ap_errors===0?"ok":"err"} />
              </div>
            ) : <div>Loading...</div>}
          </div>

          <div className="card">
            <h3>Mod & Config</h3>
            <div className="actions" style={{flexWrap:"wrap"}}>
              <button className="btn btn-primary" onClick={installMod} disabled={loading["Install Mod"]}>
                {loading["Install Mod"] ? "Installing..." : "Install Mod"}
              </button>
              <button className="btn btn-primary" onClick={scanTechs} disabled={loading["Scan Techs"]}>
                {loading["Scan Techs"] ? "Scanning..." : "Scan Techs"}
              </button>
              <button className="btn btn-success" onClick={applyConfig} disabled={!techs || loading["Apply Config"]}>
                {loading["Apply Config"] ? "Applying..." : "Apply Tech Config"}
              </button>
              <button className="btn btn-primary" onClick={checkErrors} disabled={loading["Check Errors"]}>
                Check Errors
              </button>
              <button className="btn btn-primary" onClick={fetchStatus}>Refresh</button>
              <button className="btn btn-warn" onClick={async () => {
                if (!confirm("Remove mod, DLL, config, and state files?")) return;
                const d = await doAction("Uninstall", "/api/uninstall", {method:"POST"});
                if (d && d.removed) d.removed.forEach(r => addLog("  Removed: "+r, "ok"));
                if (d && d.errors) d.errors.forEach(e => addLog("  "+e, "err"));
              }}>Uninstall</button>
            </div>
          </div>

          <div className="card">
            <h3>DLL</h3>
            <div className="actions" style={{flexWrap:"wrap"}}>
              <button className="btn btn-primary" onClick={()=>doAction("Build DLL","/api/build-dll",{method:"POST"})} disabled={loading["Build DLL"]}>
                {loading["Build DLL"] ? "Building..." : "Build DLL"}
              </button>
              <button className="btn btn-success" onClick={()=>doAction("Install DLL","/api/install-dll",{method:"POST"})} disabled={loading["Install DLL"]}>
                {loading["Install DLL"] ? "Installing..." : "Install DLL"}
              </button>
              <button className="btn btn-warn" onClick={testPipe} disabled={loading["Test Pipe"]}>
                {loading["Test Pipe"] ? "Testing..." : "Test Pipe (+500 EC)"}
              </button>
            </div>
            <div style={{fontSize:12,color:"#6880a0",marginTop:8}}>
              Build requires CMake + Visual Studio 2022. Test Pipe sends 500 energy to verify the DLL is working.
            </div>
          </div>

          <div className="card">
            <h3>Quick Start</h3>
            <div style={{lineHeight:1.8,fontSize:14,color:"#8090a8"}}>
              1. Click <b>Install Mod</b> to copy mod files<br/>
              2. Click <b>Scan Techs</b> to read your game's technologies<br/>
              3. Go to <b>Tech Config</b> tab to choose which techs to randomize<br/>
              4. Click <b>Apply Tech Config</b> to generate overrides<br/>
              5. Build the DLL: <code style={{background:"#1a2535",padding:"2px 6px",borderRadius:4,color:"#4da6ff"}}>python setup.py build-dll && python setup.py install-dll</code><br/>
              6. Launch Stellaris with <code style={{background:"#1a2535",padding:"2px 6px",borderRadius:4,color:"#4da6ff"}}>-logall</code>, enable the mod<br/>
              7. Run the bridge: <code style={{background:"#1a2535",padding:"2px 6px",borderRadius:4,color:"#4da6ff"}}>python client/ap_bridge.py --server host:port --slot Name</code>
            </div>
          </div>
        </div>
      )}

      {tab === "bridge" && (
        <div className="panel">
          <div className="card">
            <h3>Connection Settings</h3>
            <div style={{display:"flex",gap:12,marginBottom:16,flexWrap:"wrap"}}>
              <div style={{flex:1,minWidth:200}}>
                <div style={{fontSize:11,color:"#6880a0",marginBottom:4}}>AP SERVER</div>
                <input value={bridgeServer} onChange={e=>setBridgeServer(e.target.value)} placeholder="localhost:38281" style={{width:"100%",padding:"8px 12px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:6,color:"#c0ccdd",fontSize:14,fontFamily:"Rajdhani",outline:"none"}} />
              </div>
              <div style={{flex:1,minWidth:150}}>
                <div style={{fontSize:11,color:"#6880a0",marginBottom:4}}>SLOT NAME</div>
                <input value={bridgeSlot} onChange={e=>setBridgeSlot(e.target.value)} placeholder="Stellaris" style={{width:"100%",padding:"8px 12px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:6,color:"#c0ccdd",fontSize:14,fontFamily:"Rajdhani",outline:"none"}} />
              </div>
              <div style={{minWidth:120}}>
                <div style={{fontSize:11,color:"#6880a0",marginBottom:4}}>PASSWORD</div>
                <input value={bridgePassword} onChange={e=>setBridgePassword(e.target.value)} type="password" placeholder="(optional)" style={{width:"100%",padding:"8px 12px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:6,color:"#c0ccdd",fontSize:14,fontFamily:"Rajdhani",outline:"none"}} />
              </div>
            </div>
            <div className="actions">
              <button className="btn btn-success" onClick={()=>doAction("Start Bridge","/api/start-bridge",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({server:bridgeServer,slot:bridgeSlot,password:bridgePassword})})} disabled={bridgeStatus?.bridge?.running}>
                {bridgeStatus?.bridge?.running ? "Bridge Running" : "Start Bridge"}
              </button>
              <button className="btn btn-warn" onClick={()=>doAction("Stop Bridge","/api/stop-bridge",{method:"POST"})} disabled={!bridgeStatus?.bridge?.running}>
                Stop Bridge
              </button>
              <button className="btn btn-primary" onClick={()=>doAction("Start Mock","/api/start-mock",{method:"POST"})} disabled={bridgeStatus?.mock?.running}>
                {bridgeStatus?.mock?.running ? "Mock Running" : "Start Mock Server"}
              </button>
              <button className="btn btn-warn" onClick={()=>doAction("Stop Mock","/api/stop-mock",{method:"POST"})} disabled={!bridgeStatus?.mock?.running}>
                Stop Mock
              </button>
            </div>
          </div>

          {bridgeStatus && (
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
              <div className="card">
                <h3 style={{display:"flex",alignItems:"center",gap:8}}>
                  <span style={{width:8,height:8,borderRadius:"50%",background:bridgeStatus.bridge?.running?"#4dff99":"#ff4d4d"}}></span>
                  AP Bridge {bridgeStatus.bridge?.running ? "(PID "+bridgeStatus.bridge.pid+")" : "(stopped)"}
                </h3>
                <div className="log" style={{maxHeight:300}}>
                  {(bridgeStatus.bridge?.log||[]).length === 0 ? "No output yet" :
                   (bridgeStatus.bridge?.log||[]).map((l,i)=><div key={i} className={l.includes("ERROR")?"err":l.includes("RECEIVED")?"ok":l.includes("CHECK")?"info":""}>{l}</div>)}
                </div>
              </div>
              <div className="card">
                <h3 style={{display:"flex",alignItems:"center",gap:8}}>
                  <span style={{width:8,height:8,borderRadius:"50%",background:bridgeStatus.mock?.running?"#4dff99":"#ff4d4d"}}></span>
                  Mock Server {bridgeStatus.mock?.running ? "(PID "+bridgeStatus.mock.pid+")" : "(stopped)"}
                </h3>
                <div className="log" style={{maxHeight:300}}>
                  {(bridgeStatus.mock?.log||[]).length === 0 ? "No output yet" :
                   (bridgeStatus.mock?.log||[]).map((l,i)=><div key={i} className={l.includes("CHECK")?"ok":l.includes("SENT")?"info":""}>{l}</div>)}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "techs" && (
        <div className="panel">
          {!techs ? (
            <div className="card">
              <h3>No tech data loaded</h3>
              <p style={{color:"#6880a0",marginBottom:16}}>Click "Scan Techs" on the Setup tab first, or upload a config file.</p>
              <div className="actions">
                <button className="btn btn-primary" onClick={scanTechs}>Scan Techs</button>
                <label className="btn btn-primary" style={{display:"inline-block"}}>
                  Upload Config
                  <input type="file" accept=".json" style={{display:"none"}} onChange={e => {
                    const f = e.target.files[0]; if (!f) return;
                    const r = new FileReader();
                    r.onload = ev => {
                      try { const d=JSON.parse(ev.target.result); setTechs(d.techs||d); addLog("Config loaded","ok"); }
                      catch(err) { addLog("Invalid JSON: "+err,"err"); }
                    };
                    r.readAsText(f);
                  }} />
                </label>
              </div>
            </div>
          ) : (
            <div>
              <div className="filters">
                <input placeholder="Search techs..." value={search} onChange={e=>setSearch(e.target.value)} />
                <select value={areaFilter} onChange={e=>setAreaFilter(e.target.value)}>
                  <option value="all">All Areas</option>
                  <option value="physics">Physics</option>
                  <option value="society">Society</option>
                  <option value="engineering">Engineering</option>
                </select>
                <select value={tierFilter} onChange={e=>setTierFilter(e.target.value)}>
                  <option value="all">All Tiers</option>
                  {[1,2,3,4,5].map(t=><option key={t} value={t}>Tier {t}</option>)}
                </select>
                <button className="btn btn-success" onClick={()=>bulkSet(true)} style={{padding:"6px 14px",fontSize:12}}>Select All ({filtered.length})</button>
                <button className="btn btn-warn" onClick={()=>bulkSet(false)} style={{padding:"6px 14px",fontSize:12}}>Deselect All</button>
                <button className="btn btn-success" onClick={applyConfig} disabled={loading["Apply Config"]} style={{marginLeft:"auto"}}>
                  {loading["Apply Config"] ? "Applying..." : "Apply & Save"}
                </button>
              </div>
              <div style={{fontSize:12,color:"#4a5a70",padding:"4px 8px",marginBottom:8}}>
                {filtered.length} of {stats.total} shown - {stats.rand} selected
              </div>
              <div style={{maxHeight:"60vh",overflowY:"auto"}}>
                {filtered.map(t => {
                  const ac = {physics:"#4da6ff",society:"#b44dff",engineering:"#ffb44d"}[t.area]||"#4da6ff";
                  return (
                    <div key={t.key} className={"tech-row "+(t.randomize?"on ":"")+t.area} onClick={()=>toggleTech(t.key)}>
                      <div className="check">{t.randomize?"✓":""}</div>
                      <div style={{width:28,textAlign:"center",fontFamily:"Orbitron",fontSize:11,color:ac+"90"}}>T{t.tier}</div>
                      <div style={{flex:1}}>
                        <div style={{fontSize:14,fontWeight:600,color:t.randomize?"#e0e8ff":"#5a6a80"}}>{t.name}</div>
                        <div style={{fontSize:11,color:"#4a5a70"}}>{t.key}{t.prerequisites&&t.prerequisites.length>0?" - needs: "+t.prerequisites.join(", "):""}</div>
                      </div>
                      {t.dlc && <span className="badge" style={{background:"#2a2a1a",border:"1px solid #ffb44d20",color:"#b89040"}}>{t.dlc}</span>}
                      <span className="badge" style={{background:ac+"15",color:ac+"90"}}>{t.area}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "milestones" && (
        <div className="panel">
          {!milestones ? (
            <div className="card">
              <h3>Milestone Configuration</h3>
              <p style={{color:"#6880a0",marginBottom:16}}>Configure which gameplay events count as AP checks and adjust thresholds (e.g. change "Survey 10 Systems" to "Survey 20").</p>
              <div className="actions">
                <button className="btn btn-primary" onClick={async()=>{const d=await doAction("Scan","/api/scan-milestones");if(d&&d.milestones){setMilestones(d.milestones);addLog("Loaded "+d.milestones.length+" milestones","ok");}}}>Load Defaults</button>
                <button className="btn btn-primary" onClick={async()=>{const d=await doAction("Load","/api/milestone-config");if(d&&d.milestones){setMilestones(d.milestones);addLog("Loaded saved config","ok");}}}>Load Saved</button>
              </div>
            </div>
          ) : (()=>{
            const cats=[...new Set(milestones.map(m=>m.category))].sort();
            const en=milestones.filter(m=>m.enabled).length;
            const catColors={exploration:"#4da6ff",tech:"#b44dff",expansion:"#4dff99",economy:"#ffb44d",military:"#ff4d4d",diplomacy:"#4dffff",traditions:"#ff4dff",victory:"#ffff4d"};
            const filt=milestones.filter(m=>{
              if(msCatFilter!=="all"&&m.category!==msCatFilter)return false;
              if(msSearch&&!m.name.toLowerCase().includes(msSearch.toLowerCase()))return false;
              return true;
            });
            return(<div>
              <div className="filters">
                <input placeholder="Search milestones..." value={msSearch} onChange={e=>setMsSearch(e.target.value)}/>
                <select value={msCatFilter} onChange={e=>setMsCatFilter(e.target.value)}>
                  <option value="all">All Categories</option>
                  {cats.map(c=><option key={c} value={c}>{c[0].toUpperCase()+c.slice(1)}</option>)}
                </select>
                <span style={{fontSize:13,color:"#6880a0"}}>{en}/{milestones.length} enabled</span>
                <button className="btn btn-success" onClick={async()=>{await doAction("Apply Milestones","/api/apply-milestones",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({milestones})});}} disabled={loading["Apply Milestones"]} style={{marginLeft:"auto"}}>
                  {loading["Apply Milestones"]?"Applying...":"Apply & Save"}
                </button>
              </div>
              <div style={{maxHeight:"65vh",overflowY:"auto"}}>
                {filt.map(m=>{
                  const ac=catColors[m.category]||"#888";
                  const ri=milestones.indexOf(m);
                  return(<div key={m.id} style={{display:"flex",alignItems:"center",gap:12,padding:"8px 12px",marginBottom:2,borderRadius:6,background:m.enabled?ac+"10":"#ffffff04",border:"1px solid "+(m.enabled?ac+"25":"#ffffff08")}}>
                    <div onClick={()=>{const n=[...milestones];n[ri]={...m,enabled:!m.enabled};setMilestones(n);}} style={{width:20,height:20,borderRadius:4,border:"2px solid "+(m.enabled?ac:"#3a4a60"),cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>
                      {m.enabled&&<span style={{color:ac,fontSize:13,fontWeight:900}}>&#10003;</span>}
                    </div>
                    <div style={{flex:1}}>
                      <div style={{fontSize:14,fontWeight:600,color:m.enabled?"#e0e8ff":"#5a6a80"}}>{m.name}</div>
                      <div style={{fontSize:11,color:"#4a5a70"}}>
                        {m.on_action&&<span style={{marginRight:8}}>Hook: {m.on_action}</span>}
                        {m.tracked_by==="monthly_trigger"&&<span>Monthly scan</span>}
                        {m.tracked_by==="on_action_counter"&&<span>Event counter</span>}
                        {m.tracked_by==="finisher_count"&&<span>Finisher check</span>}
                      </div>
                    </div>
                    <div style={{display:"flex",alignItems:"center",gap:8}}>
                      <span style={{fontSize:12,color:"#6880a0"}}>Threshold:</span>
                      <input type="number" value={m.threshold} min={1} onChange={e=>{
                        const v=parseInt(e.target.value)||1;
                        const n=[...milestones];
                        let nm=m.name;
                        const mt=nm.match(/^(.+?)\s*(\d+)(.*)$/);
                        if(mt)nm=mt[1]+" "+v+mt[3];
                        n[ri]={...m,threshold:v,name:nm,flag:"ap_sent_"+nm.toLowerCase().replace(/ /g,"_").replace(/[^a-z0-9_]/g,"")};
                        setMilestones(n);
                      }} style={{width:70,padding:"4px 8px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:4,color:"#c0ccdd",fontSize:13,fontFamily:"Rajdhani",textAlign:"center"}}/>
                      <span style={{padding:"2px 8px",borderRadius:4,fontSize:11,background:ac+"15",color:ac+"90"}}>{m.category}</span>
                    </div>
                  </div>);
                })}
              </div>
            </div>);
          })()}
        </div>
      )}

      {tab === "errors" && (
        <div className="panel">
          <div className="card">
            <h3>Mod Errors</h3>
            <button className="btn btn-primary" onClick={checkErrors} style={{marginBottom:12}}>Refresh</button>
            {errors === null ? <p style={{color:"#6880a0"}}>Click "Check Errors" to scan error.log</p> :
             errors.length === 0 ? <p style={{color:"#66ff99"}}>No AP-related errors found!</p> :
             <div className="log">{errors.map((e,i)=><div key={i} className="err">{e}</div>)}</div>}
          </div>
        </div>
      )}

      {tab === "log" && (
        <div className="panel">
          <div className="card">
            <h3>Activity Log</h3>
            <div className="log">
              {log.length === 0 ? <span style={{color:"#4a5a70"}}>No activity yet</span> :
               log.map((l,i) => <div key={i} className={l.type}>[{new Date(l.t).toLocaleTimeString()}] {l.msg}</div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.render(React.createElement(App), document.getElementById("root"));
</script>
</body>
</html>'''


def main():
    print(f"Starting Stellaris AP Dashboard on http://localhost:{PORT}")
    server = http.server.HTTPServer(("localhost", PORT), DashboardHandler)

    # Open browser after a short delay
    def open_browser():
        time.sleep(0.5)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
