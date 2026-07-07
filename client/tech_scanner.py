"""Stellaris Tech Scanner — reads all technologies from game files.

Scans the Stellaris game directory for all tech definitions, extracts
their metadata (tier, area, prerequisites, cost, DLC), and produces
a config file the player can edit to choose which techs to randomize.

Usage:
    python tech_scanner.py scan              # Scan game files, create config
    python tech_scanner.py scan --game-dir "D:/Steam/..."  # Custom path
    python tech_scanner.py show              # Show current config
    python tech_scanner.py apply             # Generate mod files from config

The config file (ap_tech_config.json) lists every tech with a
"randomize" flag. Edit it to true/false, then run "apply" to
regenerate the mod's tech overrides and update the apworld.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TechScanner")


def find_game_dir() -> Optional[Path]:
    """Find Stellaris game installation (needs unpacked common/technology)."""
    from ap_paths import find_stellaris_game_dir
    return find_stellaris_game_dir(require="data")


def find_user_dir() -> Path:
    from ap_paths import find_stellaris_user_dir
    return find_stellaris_user_dir(fallback=True)


def extract_tech_block(content: str, tech_name: str) -> Optional[str]:
    """Extract a full tech definition block using brace counting."""
    pattern = re.compile(r'^' + re.escape(tech_name) + r'\s*=\s*\{', re.MULTILINE)
    m = pattern.search(content)
    if not m:
        return None
    start = m.start()
    pos = m.end()
    depth = 1
    while pos < len(content) and depth > 0:
        if content[pos] == '{':
            depth += 1
        elif content[pos] == '}':
            depth -= 1
        pos += 1
    return content[start:pos]


def extract_local_vars(content: str) -> Dict[str, str]:
    """Collect @variable definitions from a script file.

    Clausewitz @variables are file-scoped (except common/scripted_variables,
    which is global). Any block copied out of a vanilla file must have that
    file's local @variables inlined, or they resolve to nothing in the
    generated override file.
    """
    out = {}
    for m in re.finditer(r'^\s*(@[A-Za-z0-9_]+)\s*=\s*(\S+)', content, re.MULTILINE):
        out[m.group(1)] = m.group(2)
    return out


def inline_local_vars(block: str, local_vars: Dict[str, str],
                      global_vars: Dict[str, str]) -> str:
    """Replace file-local @variables in a copied block with literal values.

    A variable defined in the source file shadows any global of the same
    name, so file-local definitions always win. Variables that only exist
    globally are left as references.
    """
    # Longest names first so @foo_bar is not clobbered by @foo.
    for var in sorted(local_vars, key=len, reverse=True):
        if var in block:
            block = re.sub(re.escape(var) + r'(?![A-Za-z0-9_])',
                           local_vars[var], block)
    return block


def find_top_level_potential(block: str) -> Optional[re.Match]:
    """Find the potential block at depth 1 of a tech entry, skipping any
    nested potential (e.g. inside prereqfor_desc)."""
    depth = 0
    for m in re.finditer(r'\{|\}|\bpotential\s*=\s*\{', block):
        tok = m.group(0)
        if tok.startswith('potential'):
            if depth == 1:
                return m
            depth += 1
        elif tok == '{':
            depth += 1
        else:
            depth -= 1
    return None


def parse_tech_files(game_dir: Path) -> Dict[str, dict]:
    """Parse all technology files and extract metadata."""
    tech_dir = game_dir / "common" / "technology"
    techs = {}

    for tech_file in sorted(tech_dir.glob("*.txt")):
        # Skip repeatable techs (infinite, not suitable for randomization)
        if "repeatable" in tech_file.name:
            continue

        try:
            content = tech_file.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            logger.warning(f"Could not read {tech_file.name}: {e}")
            continue

        # Determine DLC from filename
        dlc = None
        fname = tech_file.name.lower()
        if "ancient_relics" in fname:
            dlc = "Ancient Relics"
        elif "apocalypse" in fname:
            dlc = "Apocalypse"
        elif "distant_stars" in fname:
            dlc = "Distant Stars"
        elif "federations" in fname:
            dlc = "Federations"
        elif "megacorp" in fname:
            dlc = "Megacorp"
        elif "nemesis" in fname:
            dlc = "Nemesis"
        elif "overlord" in fname:
            dlc = "Overlord"
        elif "toxoids" in fname:
            dlc = "Toxoids"
        elif "first_contact" in fname:
            dlc = "First Contact"
        elif "astral" in fname:
            dlc = "Astral Planes"
        elif "machine_age" in fname:
            dlc = "Machine Age"
        elif "cosmic_storms" in fname:
            dlc = "Cosmic Storms"

        # Find all tech definitions
        for m in re.finditer(r'^(tech_\w+)\s*=\s*\{', content, re.MULTILINE):
            tech_key = m.group(1)
            block = extract_tech_block(content, tech_key)
            if not block:
                continue

            # Parse metadata
            tier_m = re.search(r'\btier\s*=\s*(\d+)', block)
            area_m = re.search(r'\barea\s*=\s*(\w+)', block)
            cost_m = re.search(r'\bcost\s*=\s*(\d+)', block)
            cost_var_m = re.search(r'\bcost\s*=\s*@tier(\d+)cost', block)

            if cost_m:
                cost = int(cost_m.group(1))
            elif cost_var_m:
                # Approximate cost from tier variable: @tier1cost ≈ 500, etc.
                tier_ref = int(cost_var_m.group(1))
                cost = max(500, tier_ref * 600)
            else:
                cost = 0
            cat_m = re.search(r'\bcategory\s*=\s*\{\s*(\w+)', block)
            prereq_m = re.search(r'prerequisites\s*=\s*\{([^}]*)\}', block)
            start_m = re.search(r'\bstart_tech\s*=\s*yes', block)
            rare_m = re.search(r'\bis_rare\s*=\s*yes', block)
            dangerous_m = re.search(r'\bis_dangerous\s*=\s*yes', block)

            tier = int(tier_m.group(1)) if tier_m else 0
            area = area_m.group(1) if area_m else "engineering"
            category = cat_m.group(1) if cat_m else ""
            prereqs = []
            if prereq_m:
                prereqs = [p.strip().strip('"') for p in prereq_m.group(1).split()
                           if p.strip().strip('"').startswith("tech_")]
            is_start = bool(start_m)
            is_rare = bool(rare_m)
            is_dangerous = bool(dangerous_m)

            # Determine a human-readable name from the key
            display_name = tech_key.replace("tech_", "").replace("_", " ").title()

            techs[tech_key] = {
                "key": tech_key,
                "name": display_name,
                "tier": tier,
                "area": area,
                "cost": cost,
                "category": category,
                "prerequisites": prereqs,
                "is_start_tech": is_start,
                "is_rare": is_rare,
                "is_dangerous": is_dangerous,
                "dlc": dlc,
                "source_file": tech_file.name,
                "randomize": False,  # default: not randomized
            }

    return techs


def auto_select_defaults(techs: Dict[str, dict]) -> Dict[str, dict]:
    """Auto-select a sensible default set of techs to randomize.
    
    Conservative by default — selects ~60-80 landmark techs that have
    meaningful gameplay impact. Players can enable more in the config.
    """

    # Never randomize: start techs, things handled by AP progressive items,
    # minor component upgrades, bio ship parts, etc.
    skip_patterns = [
        "tech_starbase_1", "tech_starbase_2",  # start techs
        "tech_basic_",  # fundamental techs
        # AP progressive items handle these
        "tech_colossus", "tech_titans", "tech_juggernaut",
        "tech_destroyers", "tech_cruisers", "tech_battleships",
        "tech_lasers_", "tech_mass_drivers_", "tech_missiles_",
        "tech_shields_", "tech_ship_armor_",
        "tech_hyper_drive_", "tech_jump_drive", "tech_psi_jump",
        "tech_colonization_", "tech_starbase_3", "tech_starbase_4", "tech_starbase_5",
        # Ship components (too granular, not interesting as AP locations)
        "_hull_", "_build_speed", "_fire_rate", "_evasion", "_growth",
        "_healing", "_confuser", "_disruptor", "_weapon",
        "tech_strike_craft", "tech_corvette", "tech_destroyer_",
        "tech_cruiser_", "tech_battleship_",
        "tech_reactor_boosters", "tech_afterburners", "tech_thrusters_",
        "tech_combat_computers", "tech_auxiliary",
        # Storm/bio ship techs (very granular DLC components)
        "storm_", "mauler", "weaver", "harbinger", "mandible",
        "bio_integration", "gravity_snare",
        # Repeatable / L-cluster / special
        "repeatable", "l_cluster", "tech_akx_", "tech_zlb_",
    ]

    # Positive list: categories of techs that make good AP locations
    good_categories = [
        "statecraft", "new_worlds", "biology", "psionics",
        "field_manipulation", "computing", "particles",
        "industry", "materials", "propulsion", "voidcraft",
    ]

    for key, tech in techs.items():
        if tech["is_start_tech"]:
            continue
        if tech["tier"] < 1 or tech["tier"] > 4:
            continue
        if any(pat in key for pat in skip_patterns):
            continue
        # Only select techs in good categories
        if tech.get("category") not in good_categories:
            continue
        # Default: tier 1-3 base game techs
        if tech["tier"] <= 3 and not tech.get("dlc"):
            tech["randomize"] = True

    return techs


def save_config(techs: Dict[str, dict], config_path: Path):
    """Save tech config to JSON."""
    # Sort by area, then tier, then name for readability
    sorted_techs = dict(sorted(
        techs.items(),
        key=lambda x: (x[1]["area"], x[1]["tier"], x[1]["key"])
    ))

    config = {
        "_help": "Set 'randomize' to true/false for each tech. "
                 "Randomized techs will be replaced by AP techs in-game.",
        "_stats": {
            "total_techs": len(sorted_techs),
            "randomized": sum(1 for t in sorted_techs.values() if t["randomize"]),
            "by_area": {
                area: sum(1 for t in sorted_techs.values()
                          if t["area"] == area and t["randomize"])
                for area in ["physics", "society", "engineering"]
            }
        },
        "techs": sorted_techs,
    }

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    logger.info(f"Saved config to {config_path}")
    logger.info(f"  Total techs: {len(sorted_techs)}")
    logger.info(f"  Randomized: {config['_stats']['randomized']}")
    for area in ["physics", "society", "engineering"]:
        count = config["_stats"]["by_area"][area]
        logger.info(f"  {area}: {count} randomized")


def load_config(config_path: Path) -> Dict[str, dict]:
    """Load tech config from JSON."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data.get("techs", {})


def generate_overrides(techs: Dict[str, dict], game_dir: Path, mod_dir: Path):
    """Generate FIOS tech override file from config."""
    tech_dir = game_dir / "common" / "technology"
    randomized = {k: v for k, v in techs.items() if v.get("randomize")}

    if not randomized:
        logger.warning("No techs selected for randomization!")
        return []

    # Read tech files individually — @variables are file-scoped, so each
    # copied block must be paired with its own file's variable definitions.
    file_contents: Dict[str, str] = {}
    file_vars: Dict[str, Dict[str, str]] = {}
    for tech_file in sorted(tech_dir.glob("*.txt")):
        if "repeatable" in tech_file.name:
            continue
        try:
            content = tech_file.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        file_contents[tech_file.name] = content
        file_vars[tech_file.name] = extract_local_vars(content)

    global_vars: Dict[str, str] = {}
    sv_dir = game_dir / "common" / "scripted_variables"
    if sv_dir.exists():
        for sv_file in sv_dir.glob("*.txt"):
            try:
                global_vars.update(extract_local_vars(
                    sv_file.read_text(encoding="utf-8-sig", errors="replace")))
            except Exception:
                pass

    output_lines = [
        "# ==========================================================================",
        "# Vanilla tech overrides for Archipelago (auto-generated by tech_scanner.py)",
        "# Each randomized tech is a verbatim copy of the vanilla tech with the AP",
        "# blocking-flag condition merged into its potential block (never a second",
        "# potential block — Clausewitz silently drops duplicate trigger blocks).",
        "# File-local @variables from the source file are inlined as literals.",
        "# ==========================================================================",
        "",
    ]

    blocked = []
    for tech_key, tech in sorted(randomized.items()):
        source_file = tech.get("source_file", "")
        search_files = ([source_file] if source_file in file_contents
                        else list(file_contents))
        block = None
        for fname in search_files:
            block = extract_tech_block(file_contents[fname], tech_key)
            if block:
                block = inline_local_vars(block, file_vars[fname], global_vars)
                break
        if not block:
            logger.warning(f"Could not find definition for {tech_key}")
            continue

        # Merge blocking flag into the existing top-level potential, or add one
        not_line = f"NOT = {{ has_country_flag = ap_tech_blocked_{tech_key} }}"
        pot_match = find_top_level_potential(block)
        if pot_match:
            line_start = block.rfind('\n', 0, pot_match.start()) + 1
            indent = re.match(r'[ \t]*', block[line_start:]).group(0)
            injection = f"\n{indent}\t{not_line}"
            block = block[:pot_match.end()] + injection + block[pot_match.end():]
        else:
            first_brace = block.index('{')
            injection = (
                f"\n\tpotential = {{\n"
                f"\t\t{not_line}\n"
                f"\t}}\n"
            )
            block = block[:first_brace+1] + injection + block[first_brace+1:]

        output_lines.append(block)
        output_lines.append("")
        blocked.append(tech_key)

    # Write override file
    out_dir = mod_dir / "common" / "technology"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "00_aaa_ap_tech_blocks.txt"
    out_path.write_text("\n".join(output_lines), encoding="utf-8")
    logger.info(f"Generated {len(blocked)} tech overrides in {out_path}")

    return blocked


def generate_vanilla_tech_data(techs: Dict[str, dict]) -> str:
    """Generate VANILLA_TECH_DATA dict for slot_generator.py."""
    randomized = {k: v for k, v in techs.items() if v.get("randomize")}

    lines = ["VANILLA_TECH_DATA = {"]
    for key, tech in sorted(randomized.items()):
        prereqs_str = str(tech.get("prerequisites", []))
        lines.append(
            f'    "{key}": {{"tier": {tech["tier"]}, '
            f'"area": "{tech["area"]}", '
            f'"prereqs": {prereqs_str}}},'
        )
    lines.append("}")

    lines.append("")
    lines.append("LOCATION_TO_VANILLA_TECH = {")
    for key, tech in sorted(randomized.items()):
        display = tech.get("name", key.replace("tech_", "").replace("_", " ").title())
        loc_name = f"Research {display}"
        lines.append(f'    "{loc_name}": "{key}",')
    lines.append("}")

    return "\n".join(lines)


# =========================================================================
# Commands
# =========================================================================

def cmd_scan(game_dir: Optional[Path] = None):
    """Scan game files and create config."""
    if not game_dir:
        game_dir = find_game_dir()
    if not game_dir:
        print("ERROR: Could not find Stellaris game directory.")
        print("Use: python tech_scanner.py scan --game-dir \"C:/path/to/Stellaris\"")
        return

    logger.info(f"Scanning: {game_dir}")
    techs = parse_tech_files(game_dir)
    logger.info(f"Found {len(techs)} technologies")

    config_path = find_user_dir() / "ap_tech_config.json"
    if config_path.exists():
        # Re-scan: keep the player's hand-edited randomize flags instead of
        # clobbering them with the auto-selected defaults.
        try:
            existing = load_config(config_path)
        except Exception as e:
            logger.warning(f"Could not read existing config ({e}); starting fresh")
            existing = {}
        kept = 0
        for key, tech in techs.items():
            if key in existing:
                tech["randomize"] = bool(existing[key].get("randomize"))
                kept += 1
        logger.info(f"Preserved randomize flags for {kept} techs from existing config")
    else:
        techs = auto_select_defaults(techs)

    save_config(techs, config_path)

    print(f"\nConfig saved to: {config_path}")
    print(f"\nEdit the file to set 'randomize' to true/false for each tech.")
    print(f"Then run: python tech_scanner.py apply")

    # Summary by area and tier
    randomized = [t for t in techs.values() if t["randomize"]]
    print(f"\nDefault selection: {len(randomized)} techs randomized out of {len(techs)}")
    for area in ["physics", "society", "engineering"]:
        area_techs = [t for t in randomized if t["area"] == area]
        print(f"  {area}: {len(area_techs)}")
        for tier in range(1, 6):
            tier_techs = [t for t in area_techs if t["tier"] == tier]
            if tier_techs:
                print(f"    Tier {tier}: {', '.join(t['name'] for t in tier_techs[:5])}"
                      + (f" +{len(tier_techs)-5} more" if len(tier_techs) > 5 else ""))


def cmd_show():
    """Show current config."""
    config_path = find_user_dir() / "ap_tech_config.json"
    if not config_path.exists():
        print("No config found. Run: python tech_scanner.py scan")
        return

    techs = load_config(config_path)
    randomized = {k: v for k, v in techs.items() if v.get("randomize")}

    print(f"Randomized techs: {len(randomized)} / {len(techs)}\n")
    for area in ["physics", "society", "engineering"]:
        area_techs = sorted(
            [(k, v) for k, v in randomized.items() if v["area"] == area],
            key=lambda x: x[1]["tier"]
        )
        if area_techs:
            print(f"  {area.upper()} ({len(area_techs)}):")
            for key, tech in area_techs:
                dlc = f" [{tech['dlc']}]" if tech.get("dlc") else ""
                prereq = f" (requires: {', '.join(tech['prerequisites'])})" if tech.get("prerequisites") else ""
                print(f"    T{tech['tier']} {tech['name']}{dlc}{prereq}")
            print()


def cmd_apply(game_dir: Optional[Path] = None):
    """Generate mod files from config."""
    if not game_dir:
        game_dir = find_game_dir()
    if not game_dir:
        print("ERROR: Could not find Stellaris game directory.")
        return

    config_path = find_user_dir() / "ap_tech_config.json"
    if not config_path.exists():
        print("No config found. Run: python tech_scanner.py scan")
        return

    techs = load_config(config_path)
    user_dir = find_user_dir()
    mod_dir = user_dir / "mod" / "archipelago_multiworld"

    # Generate tech override file
    blocked = generate_overrides(techs, game_dir, mod_dir)

    # Generate data for slot_generator
    data_str = generate_vanilla_tech_data(techs)
    data_path = user_dir / "ap_tech_data.py"
    data_path.write_text(data_str, encoding="utf-8")
    logger.info(f"Saved slot_generator data to {data_path}")

    randomized = {k: v for k, v in techs.items() if v.get("randomize")}
    print(f"\nApplied: {len(blocked)} tech overrides generated")
    print(f"Location data: {len(randomized)} techs ready for AP world")
    print(f"\nThe mod's tech overrides have been updated.")
    print(f"Restart Stellaris for changes to take effect.")


def main():
    parser = argparse.ArgumentParser(description="Stellaris Tech Scanner")
    parser.add_argument("command", choices=["scan", "show", "apply"])
    parser.add_argument("--game-dir", type=Path, default=None, help="Stellaris game directory")
    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args.game_dir)
    elif args.command == "show":
        cmd_show()
    elif args.command == "apply":
        cmd_apply(args.game_dir)


if __name__ == "__main__":
    main()
