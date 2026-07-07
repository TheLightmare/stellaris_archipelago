"""Build the release artifacts.

Produces, in dist/:
  stellaris.apworld                      — the Archipelago world package
                                           (zip of apworld/stellaris/, drop
                                           into Archipelago/worlds/)
  stellaris-archipelago-<version>.zip    — the full player package: mod,
                                           client, dashboard, setup.py, and
                                           the bridge DLL

Used by .github/workflows/release.yml and runnable locally:
    python scripts/make_release.py [--version v0.1.0] [--dll path/to/version.dll]

The DLL defaults to the freshest available (local build, else prebuilt).
"""

import argparse
import os
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Everything the player needs at runtime.
FULL_PACKAGE_ITEMS = [
    "setup.py",
    "dashboard.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "mod-install",
    "client",
    "apworld",   # dashboard reads options/tech catalog from here
]

EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_DIR_NAMES for part in p.parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        yield p


def make_apworld(dist: Path) -> Path:
    """Zip apworld/stellaris/ into stellaris.apworld (folder at zip root)."""
    src = REPO / "apworld" / "stellaris"
    out = dist / "stellaris.apworld"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _iter_files(src):
            z.write(f, Path("stellaris") / f.relative_to(src))
    print(f"  {out.name}: {out.stat().st_size:,} bytes")
    return out


def make_full_package(dist: Path, version: str, dll: Path) -> Path:
    out = dist / f"stellaris-archipelago-{version}.zip"
    prefix = Path("stellaris-archipelago")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in FULL_PACKAGE_ITEMS:
            p = REPO / item
            if not p.exists():
                print(f"  WARNING: {item} missing, skipped")
                continue
            if p.is_file():
                z.write(p, prefix / item)
            else:
                for f in _iter_files(p):
                    z.write(f, prefix / f.relative_to(REPO))
        z.write(dll, prefix / "dll" / "prebuilt" / "version.dll")
        z.writestr(str(prefix / "VERSION.txt"), f"{version}\n")
    print(f"  {out.name}: {out.stat().st_size:,} bytes")
    return out


def main():
    parser = argparse.ArgumentParser(description="Build release artifacts")
    parser.add_argument("--version", default=os.environ.get("GITHUB_REF_NAME", "dev"),
                        help="Version label (defaults to the git tag in CI)")
    parser.add_argument("--dll", type=Path, default=None,
                        help="version.dll to package (default: freshest available)")
    args = parser.parse_args()

    dll = args.dll
    if dll is None:
        sys.path.insert(0, str(REPO / "client"))
        from ap_paths import find_bridge_dll
        dll, source = find_bridge_dll(REPO)
        if not dll:
            sys.exit("No version.dll found — build it first (python setup.py build-dll)")
        print(f"Packaging DLL: {dll} ({source})")

    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    print(f"Building release {args.version} into {dist}/")
    make_apworld(dist)
    make_full_package(dist, args.version, dll)
    print("Done.")


if __name__ == "__main__":
    main()
