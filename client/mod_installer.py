"""Install the static mod files without destroying generated content.

The mod directory mixes two kinds of files:
  - static content shipped in mod-install/ (events, effects, tech blocks)
  - dynamic content generated per-seed by slot_generator.py
    (ap_dynamic_*.txt/yml and ap_slot_*.dds icons)

A naive rmtree + copytree wipes the dynamic files, which mid-campaign
means every AP tech vanishes from the research pool until the bridge
next scouts and regenerates them — and if the game is launched in that
window, the save loads without them. install_mod() stashes the dynamic
files and restores them after the copy.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import List

logger = logging.getLogger("APModInstaller")

# Repo-relative paths of files generated at runtime by slot_generator.py.
DYNAMIC_FILES = [
    "common/technology/ap_dynamic_techs.txt",
    "common/scripted_effects/ap_dynamic_effects.txt",
    "common/on_actions/ap_dynamic_on_actions.txt",
    "events/ap_dynamic_events.txt",
    "localisation/english/ap_dynamic_l_english.yml",
]
DYNAMIC_ICON_DIR = "gfx/interface/icons/technologies"
DYNAMIC_ICON_GLOB = "ap_slot_*.dds"
# The static placeholder icon ships with the mod; everything else
# matching the glob is generated.
STATIC_ICONS = {"ap_slot_tech.dds"}


def install_mod(mod_src: Path, user_dir: Path) -> int:
    """Copy the mod from mod_src into the Stellaris user directory,
    preserving any generated dynamic files already present.

    mod_src is the repo's mod-install/ directory (containing
    archipelago_multiworld.mod and archipelago_multiworld/).
    Returns the number of files in the installed mod directory.
    """
    mod_dir = user_dir / "mod" / "archipelago_multiworld"
    mod_file = user_dir / "mod" / "archipelago_multiworld.mod"
    mod_file.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(mod_src / "archipelago_multiworld.mod", mod_file)

    preserved: List[tuple] = []  # (relative_path, temp_path)
    stash = None
    if mod_dir.exists():
        stash = Path(tempfile.mkdtemp(prefix="ap_mod_dynamic_"))
        rels = list(DYNAMIC_FILES)
        icon_dir = mod_dir / DYNAMIC_ICON_DIR
        if icon_dir.exists():
            rels += [
                f"{DYNAMIC_ICON_DIR}/{p.name}"
                for p in icon_dir.glob(DYNAMIC_ICON_GLOB)
                if p.name not in STATIC_ICONS
            ]
        for rel in rels:
            src = mod_dir / rel
            if src.exists():
                dst = stash / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                preserved.append((rel, dst))
        shutil.rmtree(mod_dir)

    shutil.copytree(mod_src / "archipelago_multiworld", mod_dir)

    for rel, tmp in preserved:
        dst = mod_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp, dst)
    if preserved:
        logger.info(f"Preserved {len(preserved)} generated dynamic file(s) across reinstall")
    if stash is not None:
        shutil.rmtree(stash, ignore_errors=True)

    return sum(1 for f in mod_dir.rglob("*") if f.is_file())
