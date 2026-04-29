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


# =============================================================================
# YAML Wizard — option introspection
# =============================================================================
# The wizard reads its option list directly from apworld/stellaris/options.py
# at request time, so it stays in sync with the apworld. We mock the small
# slice of Archipelago's `Options` module that options.py imports — just
# enough to let the class definitions evaluate.

_YAML_OPTION_GROUPS = [
    ("Gameplay", ["goal", "galaxy_size"]),
    ("Locations", ["include_exploration", "include_diplomacy",
                   "include_warfare", "include_crisis"]),
    ("Items", ["traps_enabled", "trap_percentage",
               "energy_link_enabled", "energy_link_rate"]),
    ("Tech Randomization", ["randomized_techs"]),
    ("DLC", ["dlc_utopia", "dlc_federations", "dlc_nemesis", "dlc_leviathans",
             "dlc_apocalypse", "dlc_megacorp", "dlc_overlord"]),
]


def _load_tech_catalog():
    """Load apworld/stellaris/data/tech_catalog.py and return its TECH_CATALOG.

    Returns a list of plain dicts (one per catalog entry) with keys:
      key, display, tier, area, prereqs, dlc, offset

    The catalog file has no Archipelago dependencies, so we can import it
    directly without mocking anything.
    """
    import importlib.util

    apworld_dir = SCRIPT_DIR / "apworld"
    catalog_path = apworld_dir / "stellaris" / "data" / "tech_catalog.py"

    spec = importlib.util.spec_from_file_location(
        "stellaris_tech_catalog_introspect", catalog_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return [
        {
            "key": t.key,
            "display": t.display,
            "tier": t.tier,
            "area": t.area,
            "prereqs": list(t.prereqs),
            "dlc": t.dlc,
            "offset": t.offset,
        }
        for t in mod.TECH_CATALOG
    ]


def _introspect_stellaris_options():
    """Load apworld/stellaris/options.py and return the option metadata.

    Returns a list of group dicts:
      [{"label": "Gameplay",
        "options": [
          {"attr": "goal", "display_name": "Goal", "doc": "...",
           "kind": "choice", "default": "victory",
           "choices": [{"name": "victory", "value": 0}, ...]},
          ...
        ]},
       ...]
    """
    import sys
    import types
    import textwrap
    from dataclasses import fields as dc_fields

    # Mock just enough of the Options module for the class bodies to evaluate.
    class _Base:
        default = 0
        display_name = ""

    class _Choice(_Base):
        pass

    class _Toggle(_Base):
        default = 0

    class _DefaultOnToggle(_Toggle):
        default = 1

    class _Range(_Base):
        range_start = 0
        range_end = 100

    class _OptionSet(_Base):
        valid_keys = frozenset()
        default = frozenset()

    class _PerGameCommonOptions:
        pass

    om = types.ModuleType("Options")
    om.Choice = _Choice
    om.Toggle = _Toggle
    om.DefaultOnToggle = _DefaultOnToggle
    om.Range = _Range
    om.OptionSet = _OptionSet
    om.PerGameCommonOptions = _PerGameCommonOptions
    sys.modules["Options"] = om

    # Make the apworld importable
    apworld_dir = SCRIPT_DIR / "apworld"
    if str(apworld_dir) not in sys.path:
        sys.path.insert(0, str(apworld_dir))

    # Load options.py directly (bypassing stellaris/__init__.py, which pulls
    # in BaseClasses and the rest of Archipelago). options.py contains a
    # relative import (`from .data.tech_catalog import ...`), so we need to
    # stand up a minimal stellaris/stellaris.data package shell first.
    import importlib.util

    if "stellaris" not in sys.modules:
        stellaris_pkg = types.ModuleType("stellaris")
        stellaris_pkg.__path__ = [str(apworld_dir / "stellaris")]
        sys.modules["stellaris"] = stellaris_pkg
    if "stellaris.data" not in sys.modules:
        data_pkg = types.ModuleType("stellaris.data")
        data_pkg.__path__ = [str(apworld_dir / "stellaris" / "data")]
        sys.modules["stellaris.data"] = data_pkg
    if "stellaris.data.tech_catalog" not in sys.modules:
        tc_path = apworld_dir / "stellaris" / "data" / "tech_catalog.py"
        tc_spec = importlib.util.spec_from_file_location(
            "stellaris.data.tech_catalog", tc_path
        )
        tc_mod = importlib.util.module_from_spec(tc_spec)
        sys.modules["stellaris.data.tech_catalog"] = tc_mod
        tc_spec.loader.exec_module(tc_mod)

    options_path = apworld_dir / "stellaris" / "options.py"
    spec = importlib.util.spec_from_file_location(
        "stellaris.options_introspect", options_path,
    )
    opts_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(opts_mod)

    StellarisOptions = opts_mod.StellarisOptions

    # Build a lookup from attribute name → option class.
    # Annotations may be either real classes or strings (forward refs).
    annotations = StellarisOptions.__annotations__
    attr_to_cls = {}
    for attr, cls_or_name in annotations.items():
        cls = cls_or_name
        if isinstance(cls, str):
            cls = getattr(opts_mod, cls, None)
        if cls is None:
            continue
        attr_to_cls[attr] = cls

    def describe(attr, cls):
        info = {
            "attr": attr,
            "display_name": getattr(cls, "display_name", attr) or attr,
            "doc": textwrap.dedent(cls.__doc__ or "").strip(),
        }
        if issubclass(cls, _Choice):
            choice_keys = sorted(
                [k for k in dir(cls) if k.startswith("option_")],
                key=lambda k: getattr(cls, k),
            )
            choices = [
                {"name": k.replace("option_", ""), "value": getattr(cls, k)}
                for k in choice_keys
            ]
            default_val = getattr(cls, "default", 0)
            default_name = next(
                (c["name"] for c in choices if c["value"] == default_val),
                choices[0]["name"] if choices else "",
            )
            info.update({
                "kind": "choice",
                "choices": choices,
                "default": default_name,
            })
        elif issubclass(cls, _Range):
            info.update({
                "kind": "range",
                "range_start": getattr(cls, "range_start", 0),
                "range_end": getattr(cls, "range_end", 100),
                "default": int(getattr(cls, "default", 0) or 0),
            })
        elif issubclass(cls, _OptionSet):
            valid = sorted(getattr(cls, "valid_keys", frozenset()))
            default_set = sorted(getattr(cls, "default", frozenset()))
            info.update({
                "kind": "set",
                "valid_keys": valid,
                "default": default_set,
            })
        else:
            # Toggle / DefaultOnToggle
            info.update({
                "kind": "toggle",
                "default": bool(getattr(cls, "default", 0)),
            })
        return info

    groups = []
    seen = set()
    for label, attrs in _YAML_OPTION_GROUPS:
        opts = []
        for attr in attrs:
            if attr in attr_to_cls:
                opts.append(describe(attr, attr_to_cls[attr]))
                seen.add(attr)
        if opts:
            groups.append({"label": label, "options": opts})

    # Catch-all for any options added to options.py that the dashboard
    # doesn't have a group for yet — surfaces them rather than dropping them.
    leftovers = [a for a in attr_to_cls if a not in seen]
    if leftovers:
        groups.append({
            "label": "Other",
            "options": [describe(a, attr_to_cls[a]) for a in leftovers],
        })

    return groups


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
        elif path == "/api/yaml-options":
            self._api_yaml_options()
        elif path == "/api/tech-catalog":
            self._api_tech_catalog()
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

    def _api_yaml_options(self):
        """Return the apworld's option metadata, grouped, for the YAML wizard."""
        try:
            groups = _introspect_stellaris_options()
            self._json_response({"groups": groups})
        except Exception as e:
            self._json_response({
                "error": f"Could not load options.py: {e}",
                "groups": [],
            }, 500)

    def _api_tech_catalog(self):
        """Return the apworld's tech catalog for the Tech Config tab."""
        try:
            catalog = _load_tech_catalog()
            # Also surface the default selection so the UI can render
            # a "Reset to Defaults" button.
            from importlib.util import spec_from_file_location, module_from_spec
            cat_path = SCRIPT_DIR / "apworld" / "stellaris" / "data" / "tech_catalog.py"
            spec = spec_from_file_location("stl_tc_defaults", cat_path)
            mod = module_from_spec(spec); spec.loader.exec_module(mod)
            self._json_response({
                "catalog": catalog,
                "default_selection": mod.default_selection(),
            })
        except Exception as e:
            self._json_response({
                "error": f"Could not load tech_catalog.py: {e}",
                "catalog": [],
            }, 500)

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
  const [yamlGroups, setYamlGroups] = useState(null);
  const [yamlValues, setYamlValues] = useState({});
  const [yamlName, setYamlName] = useState("Stellaris");
  const [yamlDesc, setYamlDesc] = useState("");
  // Tech Config / YAML Wizard share this state so a selection in one
  // shows up in the other. `randomizedTechs` is a Set of catalog tech keys.
  const [techCatalog, setTechCatalog] = useState(null);
  const [techDefaults, setTechDefaults] = useState(null);
  const [randomizedTechs, setRandomizedTechs] = useState(null);
  const [techSearch, setTechSearch] = useState("");
  const [techAreaFilter, setTechAreaFilter] = useState("all");
  const [techTierFilter, setTechTierFilter] = useState("all");
  const [techDlcFilter, setTechDlcFilter] = useState("all");
  // techScannedKeys: when present, the Tech Config tab restricts the
  // catalog view to keys present in the player's local install. Lets
  // them hide DLC techs they don't own without manually unticking each.
  const [techScannedKeys, setTechScannedKeys] = useState(null);

  const addLog = (msg, type="info") => setLog(prev => [...prev, {msg, type, t: Date.now()}]);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(API+"/api/status");
      const d = await r.json();
      setStatus(d);
    } catch(e) { addLog("Failed to fetch status: "+e, "err"); }
  }, []);

  // Lazy-load the tech catalog (from apworld/stellaris/data/tech_catalog.py)
  // the first time either Tech Config or YAML Wizard needs it. Initial
  // selection comes from the catalog's default_selection() (no DLC techs).
  const loadTechCatalog = useCallback(async () => {
    if (techCatalog) return; // already loaded
    try {
      const r = await fetch(API+"/api/tech-catalog");
      const d = await r.json();
      if (d.catalog && d.catalog.length) {
        setTechCatalog(d.catalog);
        setTechDefaults(d.default_selection || []);
        if (randomizedTechs === null) {
          setRandomizedTechs(new Set(d.default_selection || []));
        }
        addLog("Loaded "+d.catalog.length+" catalog techs ("
               + (d.default_selection||[]).length + " default-selected)", "ok");
      } else {
        addLog("Could not load tech catalog: "+(d.error||"empty"), "err");
      }
    } catch(e) { addLog("Failed to load tech catalog: "+e, "err"); }
  }, [techCatalog, randomizedTechs]);

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
        {["setup","bridge","techs","yaml","errors","log"].map(t => (
          <div key={t} className={"tab "+(tab===t?"active":"")} onClick={()=>setTab(t)}>
            {t==="setup"?"Setup":t==="bridge"?"Bridge":t==="techs"?"Tech Config":t==="yaml"?"YAML Wizard":t==="errors"?"Errors":"Log"}
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
          {!techCatalog ? (
            <div className="card">
              <h3>Tech Randomization</h3>
              <p style={{color:"#6880a0",marginBottom:16}}>Pick which Stellaris technologies are randomized through the multiworld.<br/>Each selected tech becomes a <code style={{color:"#4da6ff"}}>Research &lt;X&gt;</code> location <em>and</em> a <code style={{color:"#4da6ff"}}>Tech: &lt;X&gt;</code> item — the vanilla effects are gated until someone in the multiworld sends you the matching item.</p>
              <div className="actions">
                <button className="btn btn-primary" onClick={loadTechCatalog}>Load Catalog</button>
              </div>
            </div>
          ) : (() => {
            const sel = randomizedTechs || new Set();
            // Distinct DLC flags surfaced by the catalog (for the dropdown)
            const dlcFlags = Array.from(new Set(techCatalog.map(t=>t.dlc).filter(Boolean))).sort();
            const filtered = techCatalog.filter(t => {
              if (techAreaFilter !== "all" && t.area !== techAreaFilter) return false;
              if (techTierFilter !== "all" && String(t.tier) !== techTierFilter) return false;
              if (techDlcFilter === "base" && t.dlc) return false;
              if (techDlcFilter !== "all" && techDlcFilter !== "base" && t.dlc !== techDlcFilter) return false;
              if (techScannedKeys && !techScannedKeys.has(t.key)) return false;
              if (techSearch) {
                const q = techSearch.toLowerCase();
                if (!t.display.toLowerCase().includes(q)
                    && !t.key.toLowerCase().includes(q)) return false;
              }
              return true;
            });
            const toggleOne = (key) => {
              const next = new Set(sel);
              next.has(key) ? next.delete(key) : next.add(key);
              setRandomizedTechs(next);
            };
            const setAllInFilter = (val) => {
              const next = new Set(sel);
              filtered.forEach(t => val ? next.add(t.key) : next.delete(t.key));
              setRandomizedTechs(next);
            };
            const resetToDefaults = () => {
              setRandomizedTechs(new Set(techDefaults || []));
              addLog("Reset randomization to default selection","info");
            };
            const runLocalScan = async () => {
              const d = await doAction("Scan Techs","/api/scan");
              if (d && d.techs) {
                const keys = new Set(Object.keys(d.techs));
                setTechScannedKeys(keys);
                addLog(`Scanned ${keys.size} techs from your install`,"ok");
              }
            };
            return (<div>
              <div className="card" style={{marginBottom:12}}>
                <div style={{display:"flex",alignItems:"center",gap:16,flexWrap:"wrap"}}>
                  <div>
                    <div style={{fontFamily:"Orbitron",fontSize:24,color:"#4da6ff"}}>{sel.size}</div>
                    <div style={{fontSize:11,color:"#6880a0"}}>/ {techCatalog.length} CATALOG TECHS</div>
                  </div>
                  <div style={{flex:1,fontSize:13,color:"#8090a8",lineHeight:1.5}}>
                    Selected techs become randomized in the multiworld. Send the resulting <code style={{color:"#4da6ff"}}>.yaml</code> to your host — the YAML Wizard tab includes this selection automatically.
                  </div>
                  <button className="btn" onClick={resetToDefaults}>Reset to Defaults</button>
                </div>
              </div>
              <div className="filters">
                <input placeholder="Search techs..." value={techSearch} onChange={e=>setTechSearch(e.target.value)}/>
                <select value={techAreaFilter} onChange={e=>setTechAreaFilter(e.target.value)}>
                  <option value="all">All Areas</option>
                  <option value="physics">Physics</option>
                  <option value="society">Society</option>
                  <option value="engineering">Engineering</option>
                </select>
                <select value={techTierFilter} onChange={e=>setTechTierFilter(e.target.value)}>
                  <option value="all">All Tiers</option>
                  {[1,2,3,4,5].map(t=><option key={t} value={String(t)}>Tier {t}</option>)}
                </select>
                <select value={techDlcFilter} onChange={e=>setTechDlcFilter(e.target.value)}>
                  <option value="all">All Sources</option>
                  <option value="base">Base game only</option>
                  {dlcFlags.map(d=><option key={d} value={d}>{d.replace(/_/g," ").replace(/\b\w/g, c=>c.toUpperCase())}</option>)}
                </select>
                <button className="btn btn-primary" onClick={runLocalScan} disabled={loading["Scan Techs"]} style={{padding:"6px 14px",fontSize:12}}>
                  {loading["Scan Techs"] ? "Scanning..." : (techScannedKeys ? "Re-scan Install" : "Scan My Install")}
                </button>
                {techScannedKeys && (
                  <button className="btn" onClick={()=>setTechScannedKeys(null)} style={{padding:"6px 14px",fontSize:12}}>Clear scan filter</button>
                )}
                <span style={{fontSize:13,color:"#6880a0"}}>{filtered.length} shown</span>
                <button className="btn btn-success" onClick={()=>setAllInFilter(true)} style={{padding:"6px 14px",fontSize:12}}>Select Visible</button>
                <button className="btn btn-warn" onClick={()=>setAllInFilter(false)} style={{padding:"6px 14px",fontSize:12}}>Deselect Visible</button>
              </div>
              {techScannedKeys && (
                <div style={{fontSize:12,color:"#4dff99",padding:"4px 12px",marginBottom:8,background:"#0a1f10",border:"1px solid #1a4a25",borderRadius:4}}>
                  Filtering to the {techScannedKeys.size} techs found in your local Stellaris install. Catalog items not present in your install are hidden.
                </div>
              )}
              <div style={{maxHeight:"60vh",overflowY:"auto"}}>
                {filtered.map(t => {
                  const ac = {physics:"#4da6ff",society:"#b44dff",engineering:"#ffb44d"}[t.area]||"#4da6ff";
                  const on = sel.has(t.key);
                  return (
                    <div key={t.key} className={"tech-row "+(on?"on ":"")+t.area} onClick={()=>toggleOne(t.key)}>
                      <div className="check">{on?"✓":""}</div>
                      <div style={{width:28,textAlign:"center",fontFamily:"Orbitron",fontSize:11,color:ac+"90"}}>T{t.tier}</div>
                      <div style={{flex:1}}>
                        <div style={{fontSize:14,fontWeight:600,color:on?"#e0e8ff":"#5a6a80"}}>{t.display}</div>
                        <div style={{fontSize:11,color:"#4a5a70"}}>{t.key}{t.prereqs&&t.prereqs.length>0?" — needs: "+t.prereqs.join(", "):""}</div>
                      </div>
                      {t.dlc && <span className="badge" style={{background:"#2a2a1a",border:"1px solid #ffb44d20",color:"#b89040"}}>{t.dlc}</span>}
                      <span className="badge" style={{background:ac+"15",color:ac+"90"}}>{t.area}</span>
                    </div>
                  );
                })}
              </div>
            </div>);
          })()}
        </div>
      )}

      {tab === "yaml" && (
        <div className="panel">
          {!yamlGroups ? (
            <div className="card">
              <h3>YAML Wizard</h3>
              <p style={{color:"#6880a0",marginBottom:16}}>Build the player config you'll send to your multiworld host. The wizard reads option metadata directly from the apworld so it's always in sync with the latest options.</p>
              <div className="actions">
                <button className="btn btn-primary" onClick={async()=>{
                  try {
                    const r = await fetch(API+"/api/yaml-options");
                    const d = await r.json();
                    if (d.groups && d.groups.length) {
                      setYamlGroups(d.groups);
                      const defaults = {};
                      for (const g of d.groups) for (const o of g.options) defaults[o.attr] = o.default;
                      setYamlValues(defaults);
                      addLog("Loaded "+d.groups.reduce((n,g)=>n+g.options.length,0)+" options from apworld","ok");
                    } else {
                      addLog("Could not load options: "+(d.error||"empty response"),"err");
                    }
                  } catch(e) { addLog("Failed to load options: "+e,"err"); }
                }}>Load Options</button>
              </div>
            </div>
          ) : (() => {
            const setVal = (attr, v) => setYamlValues(prev => ({...prev, [attr]: v}));
            // Build the YAML text live
            const yamlLines = [];
            const safeName = (yamlName || "Stellaris").trim() || "Stellaris";
            yamlLines.push("name: "+safeName);
            if (yamlDesc.trim()) yamlLines.push("description: "+yamlDesc.trim());
            yamlLines.push("game: Stellaris");
            yamlLines.push("");
            yamlLines.push("Stellaris:");
            for (const g of yamlGroups) {
              for (const o of g.options) {
                if (o.kind === "set") {
                  // OptionSet: serialize as block-style YAML list. Source the
                  // selection from the shared randomizedTechs state if loaded,
                  // else fall back to the option's default.
                  const items = randomizedTechs
                    ? Array.from(randomizedTechs).sort()
                    : (o.default || []);
                  if (items.length === 0) {
                    yamlLines.push("  "+o.attr+": []");
                  } else {
                    yamlLines.push("  "+o.attr+":");
                    for (const k of items) yamlLines.push("    - "+k);
                  }
                  continue;
                }
                const v = yamlValues[o.attr];
                let formatted;
                if (o.kind === "toggle") formatted = v ? "true" : "false";
                else if (o.kind === "range") formatted = String(parseInt(v) || 0);
                else formatted = String(v);
                yamlLines.push("  "+o.attr+": "+formatted);
              }
            }
            const yaml = yamlLines.join("\n");

            const inputStyle = {padding:"6px 10px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:4,color:"#c0ccdd",fontSize:13,fontFamily:"Rajdhani",outline:"none"};
            const labelStyle = {fontSize:14,fontWeight:600,color:"#c0d0e0",display:"block",marginBottom:4};
            const docStyle = {fontSize:11,color:"#5a6a80",marginTop:4,lineHeight:1.5,whiteSpace:"pre-wrap"};

            return (<div>
              <div className="card">
                <h3>Player Identity</h3>
                <div style={{display:"grid",gridTemplateColumns:"1fr 2fr",gap:12,alignItems:"start"}}>
                  <div>
                    <label style={labelStyle}>Slot Name *</label>
                    <input style={{...inputStyle,width:"100%"}} value={yamlName} onChange={e=>setYamlName(e.target.value)} placeholder="e.g. Alice" />
                    <div style={docStyle}>How you'll appear in the multiworld. Required by Archipelago.</div>
                  </div>
                  <div>
                    <label style={labelStyle}>Description (optional)</label>
                    <input style={{...inputStyle,width:"100%"}} value={yamlDesc} onChange={e=>setYamlDesc(e.target.value)} placeholder="e.g. My first Stellaris seed" />
                    <div style={docStyle}>Free-text note shown to the multiworld host.</div>
                  </div>
                </div>
              </div>

              {yamlGroups.map(g => (
                <div className="card" key={g.label}>
                  <h3>{g.label}</h3>
                  <div style={{display:"grid",gap:14}}>
                    {g.options.map(o => (
                      <div key={o.attr}>
                        {o.kind === "toggle" && (
                          <label style={{display:"flex",alignItems:"flex-start",gap:10,cursor:"pointer"}}>
                            <input type="checkbox" checked={!!yamlValues[o.attr]} onChange={e=>setVal(o.attr, e.target.checked)} style={{marginTop:3,width:16,height:16,accentColor:"#4da6ff"}} />
                            <div style={{flex:1}}>
                              <div style={{fontSize:14,fontWeight:600,color:"#c0d0e0"}}>{o.display_name} <span style={{fontSize:11,color:"#4a5a70",fontWeight:400,marginLeft:6}}>({o.attr})</span></div>
                              <div style={docStyle}>{o.doc}</div>
                            </div>
                          </label>
                        )}
                        {o.kind === "choice" && (
                          <div>
                            <label style={labelStyle}>{o.display_name} <span style={{fontSize:11,color:"#4a5a70",fontWeight:400,marginLeft:6}}>({o.attr})</span></label>
                            <select style={{...inputStyle,minWidth:240}} value={yamlValues[o.attr]} onChange={e=>setVal(o.attr, e.target.value)}>
                              {o.choices.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                            </select>
                            <div style={docStyle}>{o.doc}</div>
                          </div>
                        )}
                        {o.kind === "range" && (
                          <div>
                            <label style={labelStyle}>{o.display_name}: <span style={{color:"#4da6ff",fontWeight:700}}>{yamlValues[o.attr]}</span> <span style={{fontSize:11,color:"#4a5a70",fontWeight:400,marginLeft:6}}>({o.attr}, {o.range_start}–{o.range_end})</span></label>
                            <input type="range" min={o.range_start} max={o.range_end} value={yamlValues[o.attr]||0} onChange={e=>setVal(o.attr, parseInt(e.target.value))} style={{width:"100%",accentColor:"#4da6ff"}} />
                            <div style={docStyle}>{o.doc}</div>
                          </div>
                        )}
                        {o.kind === "set" && (() => {
                          const sel = randomizedTechs;
                          const total = (o.valid_keys || []).length;
                          const count = sel ? sel.size : (o.default || []).length;
                          const ready = sel !== null;
                          return (
                            <div>
                              <label style={labelStyle}>{o.display_name} <span style={{fontSize:11,color:"#4a5a70",fontWeight:400,marginLeft:6}}>({o.attr})</span></label>
                              <div style={{display:"flex",alignItems:"center",gap:14,padding:"10px 14px",background:"#0a0e1a",border:"1px solid #1a2a40",borderRadius:6}}>
                                <div>
                                  <div style={{fontFamily:"Orbitron",fontSize:22,color:"#4da6ff",lineHeight:1}}>{count}</div>
                                  <div style={{fontSize:10,color:"#6880a0"}}>/ {total} TECHS</div>
                                </div>
                                <div style={{flex:1,fontSize:12,color:"#8090a8"}}>
                                  {ready
                                    ? "Selection synced with the Tech Config tab. Edits there update the YAML below in real time."
                                    : "Open the Tech Config tab to load the catalog and customize this selection. Until then, the YAML uses the apworld's default."}
                                </div>
                                <button className="btn btn-primary" onClick={()=>setTab("techs")} style={{padding:"6px 14px",fontSize:12}}>Open Tech Config</button>
                              </div>
                              <div style={docStyle}>{o.doc}</div>
                            </div>
                          );
                        })()}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <div className="card">
                <h3>Generated YAML</h3>
                <pre style={{padding:14,background:"#050810",border:"1px solid #1a2a40",borderRadius:6,fontSize:13,fontFamily:"monospace",color:"#a0c0e0",whiteSpace:"pre-wrap",maxHeight:400,overflowY:"auto",margin:0}}>{yaml}</pre>
                <div className="actions">
                  <button className="btn btn-primary" onClick={()=>{
                    navigator.clipboard.writeText(yaml).then(
                      ()=>addLog("YAML copied to clipboard","ok"),
                      ()=>addLog("Clipboard copy failed (browser blocked it)","err")
                    );
                  }}>Copy to Clipboard</button>
                  <button className="btn btn-success" onClick={()=>{
                    const blob = new Blob([yaml],{type:"text/yaml"});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = safeName.replace(/[^a-zA-Z0-9_-]/g,"_")+".yaml";
                    document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    addLog("Downloaded "+a.download,"ok");
                  }}>Download .yaml</button>
                  <button className="btn" style={{marginLeft:"auto"}} onClick={()=>{
                    const defaults = {};
                    for (const g of yamlGroups) for (const o of g.options) defaults[o.attr] = o.default;
                    setYamlValues(defaults);
                    addLog("Reset to defaults","info");
                  }}>Reset to Defaults</button>
                </div>
                <div style={{...docStyle,marginTop:8}}>Send this <code style={{color:"#4da6ff"}}>.yaml</code> to your multiworld host along with the <code style={{color:"#4da6ff"}}>stellaris.apworld</code> file.</div>
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
