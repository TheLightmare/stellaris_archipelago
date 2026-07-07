"""Shared Stellaris directory detection.

Single source of truth for locating the Stellaris user directory
(Documents/Paradox Interactive/Stellaris) and the game install.
Used by ap_bridge.py, tech_scanner.py, setup.py, and dashboard.py —
previously each had its own copy with subtly different candidate
lists and preferences, which could silently pick a directory the
game never writes to (dead log tailer, mod installed where the
launcher never looks).

Overrides for unusual setups:
    STELLARIS_USER_DIR  — full path to the Stellaris user directory
    STELLARIS_GAME_DIR  — full path to the game install directory
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("APPaths")


def _user_dir_candidates() -> List[Path]:
    home = Path.home()
    return [
        home / "Documents" / "Paradox Interactive" / "Stellaris",
        home / "OneDrive" / "Documents" / "Paradox Interactive" / "Stellaris",
    ]


def _activity_score(p: Path):
    """How likely is this to be the directory the game actually uses?

    Ranked by hard evidence: a game.log the game has written beats a
    settings file, which beats merely existing. Ties break on mtime so
    two dirs with logs resolve to the most recently played one.
    """
    log = p / "logs" / "game.log"
    if log.exists():
        return (2, log.stat().st_mtime)
    for settings_name in ("pdx_settings.txt", "settings.txt"):
        s = p / settings_name
        if s.exists():
            return (1, s.stat().st_mtime)
    return (0, 0.0)


def find_stellaris_user_dir(fallback: bool = False) -> Optional[Path]:
    """Locate the Stellaris user directory.

    With OneDrive folder redirection both ~/Documents and
    ~/OneDrive/Documents can contain a Paradox Interactive tree; picking
    the wrong one means the bridge tails a game.log the game never
    writes. Prefer the directory with the freshest evidence of use.

    fallback=True returns the first candidate path even if nothing
    exists yet (callers that need somewhere to write state).
    """
    env = os.environ.get("STELLARIS_USER_DIR")
    if env:
        p = Path(env)
        if p.exists():
            logger.info(f"Stellaris user dir (from STELLARIS_USER_DIR): {p}")
            return p
        logger.warning(f"STELLARIS_USER_DIR is set but does not exist: {p}")

    candidates = [p for p in _user_dir_candidates() if p.exists()]
    if not candidates:
        return _user_dir_candidates()[0] if fallback else None
    if len(candidates) == 1:
        return candidates[0]

    best = max(candidates, key=_activity_score)
    others = [str(c) for c in candidates if c != best]
    logger.info(
        f"Multiple Stellaris user dirs found; using {best} "
        f"(most recent game activity). Ignoring: {', '.join(others)}. "
        "Set STELLARIS_USER_DIR to override."
    )
    return best


def _steam_library_dirs() -> List[Path]:
    """Every Steam library on this machine, discovered via the registry.

    Reads Steam's install path from the registry, then parses
    steamapps/libraryfolders.vdf for additional libraries — this finds
    installs on any drive without hardcoding paths.
    """
    libraries: List[Path] = []
    steam_root: Optional[Path] = None
    try:
        import winreg
        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    value_name = "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath"
                    path, _ = winreg.QueryValueEx(k, value_name)
                    if path and Path(path).exists():
                        steam_root = Path(path)
                        break
            except OSError:
                continue
    except ImportError:
        pass  # non-Windows

    if steam_root:
        libraries.append(steam_root)
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                import re
                text = vdf.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                    p = Path(m.group(1).replace("\\\\", "\\"))
                    if p.exists() and p not in libraries:
                        libraries.append(p)
            except Exception as e:
                logger.debug(f"Could not parse libraryfolders.vdf: {e}")
    return libraries


def _game_dir_candidates() -> List[Path]:
    home = Path.home()
    # Registry-discovered Steam libraries first (authoritative), then the
    # historical hardcoded fallbacks for non-standard setups.
    candidates = [
        lib / "steamapps" / "common" / "Stellaris"
        for lib in _steam_library_dirs()
    ]
    candidates += [
        Path("C:/Program Files (x86)/Steam/steamapps/common/Stellaris"),
        Path("C:/Program Files/Steam/steamapps/common/Stellaris"),
        Path("C:/SteamLibrary/steamapps/common/Stellaris"),
        Path("D:/SteamLibrary/steamapps/common/Stellaris"),
        Path("D:/Steam/steamapps/common/Stellaris"),
        Path("E:/SteamLibrary/steamapps/common/Stellaris"),
        home / "Steam" / "steamapps" / "common" / "Stellaris",
        home / ".steam" / "steam" / "steamapps" / "common" / "Stellaris",
    ]
    # De-dup, preserving order.
    seen = set()
    unique = []
    for c in candidates:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def find_stellaris_game_dir(require: str = "any") -> Optional[Path]:
    """Locate the Stellaris game install.

    require:
        "exe"  — must contain stellaris.exe (DLL install)
        "data" — must contain common/technology (tech scanning)
        "any"  — either marker is enough
    """
    def ok(p: Path) -> bool:
        if not p.exists():
            return False
        has_exe = (p / "stellaris.exe").exists()
        has_data = (p / "common" / "technology").exists()
        if require == "exe":
            return has_exe
        if require == "data":
            return has_data
        return has_exe or has_data

    env = os.environ.get("STELLARIS_GAME_DIR")
    if env:
        p = Path(env)
        if ok(p):
            return p
        logger.warning(
            f"STELLARIS_GAME_DIR is set but missing the required "
            f"{require!r} marker: {p}"
        )

    for p in _game_dir_candidates():
        if ok(p):
            return p
    return None


def find_bridge_dll(repo_root: Path):
    """Locate the version.dll to install: a fresh local build if the
    player compiled one, else the prebuilt binary shipped in the repo.

    Returns (path, source) where source is "built" or "prebuilt",
    or (None, None) if neither exists.
    """
    built = repo_root / "dll" / "build" / "Release" / "version.dll"
    prebuilt = repo_root / "dll" / "prebuilt" / "version.dll"
    if built.exists():
        return built, "built"
    if prebuilt.exists():
        return prebuilt, "prebuilt"
    return None, None
