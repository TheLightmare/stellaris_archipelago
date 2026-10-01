"""Automate the two manual setup steps players get wrong most often.

1. Steam launch option ``-logall`` for Stellaris (app 281990). Without it
   the game suppresses repeated log lines and the bridge misses the
   mod's heartbeat and re-logged checks. Stored by Steam in
   ``userdata/<id>/config/localconfig.vdf``; Steam rewrites that file on
   exit, so we only edit it while Steam is closed.

2. Enabling the mod in the Paradox launcher. The launcher keeps its
   playsets in ``launcher-v2.sqlite`` in the Stellaris user directory and
   registers local mods it finds in ``mod/`` on start. We add the mod to
   the active playset (and register it if the launcher has never seen
   it) while the launcher is closed.

Every write makes a timestamped backup next to the file first and
refuses to run while the owning program is open. Everything here is
best-effort: a failure is reported with the manual steps, never raised.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

STELLARIS_APP_ID = "281990"
REQUIRED_LAUNCH_OPTION = "-logall"
MOD_REGISTRY_ID = "mod/archipelago_multiworld.mod"
MOD_DISPLAY_NAME = "Archipelago Multiworld"

MANUAL_LAUNCH_OPTION_STEPS = (
    "In Steam: Library > right-click Stellaris > Properties > General > "
    "Launch Options: type -logall"
)
MANUAL_ENABLE_MOD_STEPS = (
    "In the Paradox launcher: Playsets > tick 'Archipelago Multiworld' in "
    "your active playset"
)


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def is_running(*image_names: str) -> bool:
    """True if any of the given Windows process image names is running."""
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/NH"], capture_output=True, text=True, timeout=10)
    except Exception:
        return False
    listing = r.stdout.lower()
    return any(name.lower() in listing for name in image_names)


def steam_running() -> bool:
    return is_running("steam.exe")


def launcher_running() -> bool:
    # dowser.exe is the Paradox Launcher v2 process; the game itself also
    # holds the launcher DB open while running.
    return is_running("dowser.exe", "Paradox Launcher.exe", "stellaris.exe")


def _backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = path.with_name(f"{path.name}.ap-backup-{stamp}")
    shutil.copy2(path, dst)
    return dst


# ---------------------------------------------------------------------------
# Steam launch options
# ---------------------------------------------------------------------------

def _steam_root() -> Optional[Path]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
            return p if p.exists() else None
    except Exception:
        return None


def _active_steam_user() -> Optional[str]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as k:
            uid = winreg.QueryValueEx(k, "ActiveUser")[0]
            return str(uid) if uid else None
    except Exception:
        return None


def steam_localconfig_paths() -> List[Path]:
    """localconfig.vdf for the active Steam user first, then any others."""
    root = _steam_root()
    if not root:
        return []
    userdata = root / "userdata"
    if not userdata.exists():
        return []
    found = []
    active = _active_steam_user()
    for d in sorted(userdata.iterdir()):
        cfg = d / "config" / "localconfig.vdf"
        if cfg.exists():
            found.append(cfg)
    found.sort(key=lambda p: 0 if active and p.parent.parent.name == active else 1)
    return found


def _find_app_block(text: str, app_id: str):
    """(start, end) of the app's block under the "apps" section, or None.

    The same app id appears elsewhere in the file (CDN tokens, badges),
    so anchor on the "apps" section first.
    """
    apps_idx = text.find('"apps"')
    if apps_idx < 0:
        return None
    m = re.compile(r'"%s"\s*\{' % re.escape(app_id)).search(text, apps_idx)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return m.start(), i


def launch_options_status() -> Dict:
    """What Steam currently has as Stellaris launch options."""
    paths = steam_localconfig_paths()
    result = {
        "supported": sys.platform == "win32",
        "steam_found": bool(paths),
        "steam_running": steam_running(),
        "configured": None,      # True / False / None (unknown)
        "options": "",
        "path": str(paths[0]) if paths else None,
        "manual": MANUAL_LAUNCH_OPTION_STEPS,
    }
    if not paths:
        return result
    try:
        text = paths[0].read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["error"] = str(e)
        return result
    span = _find_app_block(text, STELLARIS_APP_ID)
    if not span:
        result["configured"] = False
        result["note"] = "Stellaris has not been launched from Steam on this account yet"
        return result
    block = text[span[0]:span[1]]
    m = re.search(r'"LaunchOptions"\s*"([^"]*)"', block)
    opts = m.group(1) if m else ""
    result["options"] = opts
    result["configured"] = REQUIRED_LAUNCH_OPTION in opts.split()
    return result


def set_launch_option(path: Optional[Path] = None) -> Dict:
    """Add -logall to Stellaris' launch options. Steam must be closed."""
    if sys.platform != "win32":
        return {"success": False, "error": "Windows only", "manual": MANUAL_LAUNCH_OPTION_STEPS}
    if steam_running():
        return {
            "success": False,
            "error": "Steam is running. Close Steam completely (tray icon > Exit) "
                     "and try again, or set it by hand.",
            "manual": MANUAL_LAUNCH_OPTION_STEPS,
        }
    paths = [path] if path else steam_localconfig_paths()
    if not paths:
        return {"success": False, "error": "Steam userdata not found", "manual": MANUAL_LAUNCH_OPTION_STEPS}

    changed = []
    for cfg in paths:
        try:
            raw = cfg.read_bytes()
            text = raw.decode("utf-8", errors="surrogateescape")
            span = _find_app_block(text, STELLARIS_APP_ID)
            if not span:
                continue
            start, end = span
            block = text[start:end]
            m = re.search(r'("LaunchOptions"\s*")([^"]*)(")', block)
            if m:
                opts = m.group(2).split()
                if REQUIRED_LAUNCH_OPTION in opts:
                    changed.append(str(cfg))
                    continue
                opts.append(REQUIRED_LAUNCH_OPTION)
                new_block = block[:m.start(2)] + " ".join(opts) + block[m.end(2):]
            else:
                # Insert right after the opening brace, copying the
                # indentation Steam uses for the sibling keys.
                brace = block.index("{")
                nl = block.find("\n", brace)
                sibling = re.match(r"[ \t]*", block[nl + 1:]).group(0) if nl >= 0 else "\t"
                insertion = f'\n{sibling}"LaunchOptions"\t\t"{REQUIRED_LAUNCH_OPTION}"'
                new_block = block[:brace + 1] + insertion + block[brace + 1:]
            backup = _backup(cfg)
            new_text = text[:start] + new_block + text[end:]
            cfg.write_bytes(new_text.encode("utf-8", errors="surrogateescape"))
            changed.append(str(cfg))
        except Exception as e:
            return {"success": False, "error": f"{cfg}: {e}", "manual": MANUAL_LAUNCH_OPTION_STEPS}

    if not changed:
        return {
            "success": False,
            "error": "Stellaris has never been started from Steam on this account, "
                     "so Steam has no settings block for it yet. Start the game "
                     "once from Steam, close everything, then try again.",
            "manual": MANUAL_LAUNCH_OPTION_STEPS,
        }
    return {"success": True, "files": changed}


# ---------------------------------------------------------------------------
# Paradox launcher playset
# ---------------------------------------------------------------------------

def _launcher_db(user_dir: Path) -> Path:
    return user_dir / "launcher-v2.sqlite"


def launcher_status(user_dir: Path) -> Dict:
    """Is the mod registered with the launcher and enabled in the active playset?"""
    db = _launcher_db(user_dir)
    result = {
        "db_found": db.exists(),
        "launcher_running": launcher_running(),
        "registered": False,
        "enabled": False,
        "playset": None,
        "manual": MANUAL_ENABLE_MOD_STEPS,
    }
    if not db.exists():
        result["note"] = "Launcher database not found — open the Paradox launcher once"
        return result
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            mod = con.execute(
                "select id from mods where gameRegistryId = ?", (MOD_REGISTRY_ID,)
            ).fetchone()
            result["registered"] = mod is not None
            ps = con.execute(
                "select id, name from playsets where isActive = 1 and isRemoved = 0"
            ).fetchone()
            if ps:
                result["playset"] = ps[1]
                if mod:
                    row = con.execute(
                        "select enabled from playsets_mods where playsetId = ? and modId = ?",
                        (ps[0], mod[0]),
                    ).fetchone()
                    result["enabled"] = bool(row and row[0])
        finally:
            con.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def enable_mod_in_launcher(user_dir: Path, mod_dir: Optional[Path] = None) -> Dict:
    """Register (if needed) and enable the mod in the active playset.

    The launcher and the game must be closed: the launcher writes the
    database on exit and would overwrite our change.
    """
    db = _launcher_db(user_dir)
    mod_dir = mod_dir or (user_dir / "mod" / "archipelago_multiworld")
    if not db.exists():
        return {"success": False,
                "error": "Launcher database not found. Open the Paradox launcher once, close it, and retry.",
                "manual": MANUAL_ENABLE_MOD_STEPS}
    if not (mod_dir / "descriptor.mod").exists():
        return {"success": False, "error": "Install the mod first.", "manual": MANUAL_ENABLE_MOD_STEPS}
    if launcher_running():
        return {"success": False,
                "error": "Close the Paradox launcher (and Stellaris) first, then retry — "
                         "the launcher overwrites its database on exit.",
                "manual": MANUAL_ENABLE_MOD_STEPS}

    try:
        backup = _backup(db)
        con = sqlite3.connect(db, timeout=5)
        try:
            cols = {r[1] for r in con.execute("pragma table_info(mods)")}
            for needed in ("id", "gameRegistryId", "displayName", "dirPath", "status", "source"):
                if needed not in cols:
                    return {"success": False,
                            "error": f"Unexpected launcher database layout (no mods.{needed}); "
                                     "enable the mod by hand.",
                            "manual": MANUAL_ENABLE_MOD_STEPS}

            mod = con.execute(
                "select id from mods where gameRegistryId = ?", (MOD_REGISTRY_ID,)
            ).fetchone()
            registered_now = False
            if mod:
                mod_id = mod[0]
            else:
                mod_id = str(uuid.uuid4())
                desc = (mod_dir / "descriptor.mod").read_text(encoding="utf-8", errors="replace")
                version = re.search(r'version\s*=\s*"([^"]*)"', desc)
                req = re.search(r'supported_version\s*=\s*"([^"]*)"', desc)
                row = {
                    "id": mod_id,
                    "gameRegistryId": MOD_REGISTRY_ID,
                    "displayName": MOD_DISPLAY_NAME,
                    "dirPath": str(mod_dir),
                    "status": "ready_to_play",
                    "source": "local",
                    "version": version.group(1) if version else "",
                    "requiredVersion": req.group(1) if req else "",
                    "tags": json.dumps(["Gameplay"]),
                    "createdDate": int(time.time()),
                }
                row = {k: v for k, v in row.items() if k in cols}
                con.execute(
                    f"insert into mods ({', '.join(row)}) values ({', '.join('?' * len(row))})",
                    list(row.values()),
                )
                registered_now = True

            ps = con.execute(
                "select id, name from playsets where isActive = 1 and isRemoved = 0"
            ).fetchone()
            if not ps:
                ps = con.execute(
                    "select id, name from playsets where isRemoved = 0 order by createdOn limit 1"
                ).fetchone()
                if not ps:
                    return {"success": False,
                            "error": "No playset exists yet. Open the Paradox launcher once "
                                     "(it creates one), close it, and retry.",
                            "manual": MANUAL_ENABLE_MOD_STEPS}
                con.execute("update playsets set isActive = 0")
                con.execute("update playsets set isActive = 1 where id = ?", (ps[0],))
            playset_id, playset_name = ps

            existing = con.execute(
                "select enabled from playsets_mods where playsetId = ? and modId = ?",
                (playset_id, mod_id),
            ).fetchone()
            if existing is None:
                pos = con.execute(
                    "select coalesce(max(position), -1) + 1 from playsets_mods where playsetId = ?",
                    (playset_id,),
                ).fetchone()[0]
                con.execute(
                    "insert into playsets_mods (playsetId, modId, enabled, position) values (?, ?, 1, ?)",
                    (playset_id, mod_id, pos),
                )
            elif not existing[0]:
                con.execute(
                    "update playsets_mods set enabled = 1 where playsetId = ? and modId = ?",
                    (playset_id, mod_id),
                )
            con.commit()
        finally:
            con.close()
        return {"success": True, "playset": playset_name,
                "registered_now": registered_now, "backup": str(backup)}
    except Exception as e:
        return {"success": False, "error": f"Could not update launcher database: {e}",
                "manual": MANUAL_ENABLE_MOD_STEPS}


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

def launch_stellaris() -> Dict:
    """Ask Steam to start Stellaris (the Paradox launcher appears as usual)."""
    if sys.platform != "win32":
        return {"success": False, "error": "Windows only"}
    try:
        os.startfile(f"steam://run/{STELLARIS_APP_ID}")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------

def missing_python_deps() -> List[str]:
    missing = []
    try:
        import websocket  # noqa: F401
    except ImportError:
        try:
            import websockets  # noqa: F401
        except ImportError:
            missing.append("websocket-client")
    if sys.platform == "win32":
        try:
            import win32file  # noqa: F401
        except ImportError:
            missing.append("pywin32")
    return missing


def install_python_deps() -> Dict:
    missing = missing_python_deps()
    if not missing:
        return {"success": True, "installed": []}
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", *missing],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        # --user is rejected inside virtualenvs; retry plainly.
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing],
            capture_output=True, text=True, timeout=600,
        )
    if r.returncode != 0:
        return {"success": False, "error": (r.stderr or r.stdout)[-800:],
                "manual": f"pip install {' '.join(missing)}"}
    return {"success": True, "installed": missing,
            "note": "Restart the dashboard so it picks up the new packages" if "pywin32" in missing else None}
