"""Cross-layer coherence checks (apworld <-> client <-> mod).

The four layers of this project agree on IDs and names only by
convention (see CONTRIBUTING.md). This script verifies that convention
and fails loudly when any layer drifts:

  * client/tech_catalog.py is byte-identical to the apworld catalog
  * every apworld item has a client effect, and every effect exists in
    the mod's ap_item_effects.txt
  * every AP_CHECK line the mod can write names a real apworld location
    with the exact same name
  * every milestone-type location is actually detected by the mod
  * every static tech-type location is known to the bridge
  * every catalog tech has a blocking hook in 00_aaa_ap_tech_blocks.txt
  * events reference localisation keys that exist
  * all Paradox script files have balanced braces
  * the generated ap_resync.txt matches the detection/sender tables

Usage:
    python scripts/check_coherence.py          # verify, exit 1 on drift
    python scripts/check_coherence.py --write  # regenerate ap_resync.txt

Runs without an Archipelago checkout (BaseClasses is stubbed).
"""

import argparse
import importlib
import importlib.util
import re
import sys
import types
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parent.parent
APWORLD = REPO / "apworld"
CLIENT = REPO / "client"
MOD = REPO / "mod-install" / "archipelago_multiworld"

RESYNC_FILE = MOD / "common" / "scripted_effects" / "ap_resync.txt"
DETECTION_FILE = MOD / "common" / "scripted_effects" / "ap_check_detection.txt"
SENDERS_FILE = MOD / "common" / "scripted_effects" / "ap_bridge_log.txt"
EFFECTS_FILE = MOD / "common" / "scripted_effects" / "ap_item_effects.txt"
BLOCKS_FILE = MOD / "common" / "technology" / "00_aaa_ap_tech_blocks.txt"
LOC_FILE = MOD / "localisation" / "english" / "ap_l_english.yml"

VICTORY_FLAG = "ap_sent_victory"


class Report:
    def __init__(self):
        self.errors: List[str] = []
        self.notes: List[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def ok(self, msg: str):
        self.notes.append(msg)


# ---------------------------------------------------------------------------
# Loading the apworld without Archipelago
# ---------------------------------------------------------------------------

def _stub_archipelago():
    """Install a minimal BaseClasses so items.py/locations.py import."""
    if "BaseClasses" in sys.modules:
        return
    import enum

    class ItemClassification(enum.IntFlag):
        filler = 0b0000
        progression = 0b0001
        useful = 0b0010
        trap = 0b0100
        skip_balancing = 0b1000

    class Item:
        pass

    class Location:
        pass

    bc = types.ModuleType("BaseClasses")
    bc.Item = Item
    bc.Location = Location
    bc.ItemClassification = ItemClassification
    sys.modules["BaseClasses"] = bc


def load_apworld_modules():
    """Import stellaris.items / stellaris.locations / stellaris.data.tech_catalog
    as a package rooted at apworld/stellaris without running __init__.py
    (which needs the full Archipelago framework)."""
    _stub_archipelago()
    pkg = types.ModuleType("stellaris")
    pkg.__path__ = [str(APWORLD / "stellaris")]
    sys.modules["stellaris"] = pkg
    data = types.ModuleType("stellaris.data")
    data.__path__ = [str(APWORLD / "stellaris" / "data")]
    sys.modules["stellaris.data"] = data
    catalog = importlib.import_module("stellaris.data.tech_catalog")
    items = importlib.import_module("stellaris.items")
    locations = importlib.import_module("stellaris.locations")
    return catalog, items, locations


def load_client_bridge():
    sys.path.insert(0, str(CLIENT))
    import logging
    logging.disable(logging.CRITICAL)
    import ap_bridge  # noqa: E402
    return ap_bridge


# ---------------------------------------------------------------------------
# Mod parsing helpers
# ---------------------------------------------------------------------------

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def strip_comments(text: str) -> str:
    return re.sub(r"#[^\n]*", "", text)


def sender_log_lines(text: str) -> Dict[str, List[str]]:
    """{sender_effect: [log strings...]} from ap_bridge_log.txt."""
    out: Dict[str, List[str]] = {}
    for m in re.finditer(r"^(ap_send_check_\w+)\s*=\s*\{(.*?)^\}", text, re.M | re.S):
        out[m.group(1)] = re.findall(r'log\s*=\s*"([^"]+)"', m.group(2))
    return out


def detection_pairs(text: str) -> List[Tuple[str, str]]:
    """(sent_flag, sender_effect) pairs from ap_check_detection.txt.

    Each milestone block sets its ap_sent_* flag and immediately calls
    its sender, so the two always appear on consecutive lines.
    """
    return re.findall(
        r"set_country_flag\s*=\s*(ap_sent_\w+)\s*\n\s*(ap_send_check_\w+)\s*=\s*yes",
        strip_comments(text),
    )


def brace_balance(text: str) -> int:
    depth = 0
    for ch in strip_comments(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return depth
    return depth


# ---------------------------------------------------------------------------
# Resync effect generation
# ---------------------------------------------------------------------------

def build_resync(detection: str, senders: str) -> str:
    pairs = detection_pairs(detection)
    logs = sender_log_lines(senders)
    lines = [
        "# ============================================================================",
        "# Archipelago Resync — generated by scripts/check_coherence.py --write",
        "# DO NOT EDIT BY HAND. Re-run the script after changing",
        "# ap_check_detection.txt or ap_bridge_log.txt.",
        "# ============================================================================",
        "# Fires monthly from ap_bridge.1. For every milestone this save has",
        "# already sent, the AP_CHECK line is written to game.log again. The",
        "# bridge deduplicates, so the only effect is that a check made while",
        "# the bridge was not running is recovered at the next monthly tick",
        "# instead of being lost forever (-logall keeps repeated lines).",
        "# AP techs generated per seed re-log themselves from ap_slot.1.",
        "# ============================================================================",
        "",
        "ap_resync_sent_checks = {",
    ]
    seen = set()
    for flag, sender in pairs:
        if flag in seen:
            continue
        seen.add(flag)
        for log in logs.get(sender, []):
            lines.append(
                f'    if = {{ limit = {{ has_country_flag = {flag} }} log = "{log}" }}'
            )
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_catalog_sync(rep: Report):
    def body(p: Path) -> str:
        text = read(p)
        idx = text.find("from typing import")
        return text[idx:] if idx >= 0 else text

    if body(CLIENT / "tech_catalog.py") == body(APWORLD / "stellaris" / "data" / "tech_catalog.py"):
        rep.ok("client/tech_catalog.py matches apworld catalog")
    else:
        rep.error("client/tech_catalog.py differs from apworld/stellaris/data/tech_catalog.py "
                  "(run: cp apworld/stellaris/data/tech_catalog.py client/tech_catalog.py "
                  "and restore the client header)")


def check_items(rep: Report, items, bridge):
    effects_text = read(EFFECTS_FILE)
    defined = set(re.findall(r"^(ap_\w+)\s*=\s*\{", effects_text, re.M))

    apworld_ids = {data.code: name for name, data in items.ALL_ITEMS.items()}
    client_ids = set(bridge.ITEM_EFFECT_MAP)

    for code in sorted(set(apworld_ids) - client_ids):
        rep.error(f"item {apworld_ids[code]!r} (id {code}) has no entry in client ITEM_EFFECT_MAP")
    for code in sorted(client_ids - set(apworld_ids)):
        rep.error(f"client ITEM_EFFECT_MAP id {code} ({bridge.ITEM_EFFECT_MAP[code]}) is not an apworld item")
    for code, effect in sorted(bridge.ITEM_EFFECT_MAP.items()):
        if effect not in defined:
            rep.error(f"effect {effect} (item {code}) is not defined in ap_item_effects.txt")
    rep.ok(f"{len(apworld_ids)} items cross-checked against client map and mod effects")


def check_locations(rep: Report, catalog, locations, bridge):
    senders = sender_log_lines(read(SENDERS_FILE))
    detection = read(DETECTION_FILE)
    pairs = detection_pairs(detection)
    paired_senders = {s for _, s in pairs}

    by_id = {data.code: name for name, data in locations.ALL_LOCATIONS.items()}
    catalog_ids = {locations.BASE_ID + 10000 + t.offset for t in catalog.TECH_CATALOG}

    # (a) every AP_CHECK line in the mod is a real location, name-exact
    sender_for_id: Dict[int, str] = {}
    for sender, logs in senders.items():
        for log in logs:
            m = re.fullmatch(r"AP_CHECK\|(\d+)\|(.*)", log)
            if not m:
                continue
            lid, lname = int(m.group(1)), m.group(2)
            sender_for_id[lid] = sender
            if lid not in by_id:
                rep.error(f"{sender}: AP_CHECK id {lid} is not an apworld location")
            elif by_id[lid] != lname:
                rep.error(f"{sender}: name {lname!r} != apworld {by_id[lid]!r} for id {lid}")

    # (b) every milestone location is detected (flag + sender pair)
    for name, data in locations.ALL_LOCATIONS.items():
        if data.code in catalog_ids:
            continue
        if data.location_type == "milestone":
            sender = sender_for_id.get(data.code)
            if sender is None:
                rep.error(f"milestone {name!r} ({data.code}) has no AP_CHECK sender in ap_bridge_log.txt")
            elif sender not in paired_senders:
                rep.error(f"milestone {name!r}: sender {sender} is never called from ap_check_detection.txt")
        elif data.location_type == "tech":
            if data.code not in bridge._STATIC_TECH_LOCATION_IDS:
                rep.error(f"tech-type location {name!r} ({data.code}) missing from bridge _STATIC_TECH_LOCATION_IDS")
    for lid in sorted(bridge._STATIC_TECH_LOCATION_IDS):
        if lid not in by_id:
            rep.error(f"bridge _STATIC_TECH_LOCATION_IDS has {lid}, which is not an apworld location")
        elif locations.ALL_LOCATIONS[by_id[lid]].location_type != "tech":
            rep.error(f"bridge _STATIC_TECH_LOCATION_IDS has {lid} ({by_id[lid]!r}) but it is a milestone")

    # (c) victory: every goal branch must send it
    goal_branches = re.findall(r"has_country_flag = ap_goal_(\d)", strip_comments(detection))
    victory_sends = detection.count("ap_send_check_victory = yes")
    if victory_sends < 4:
        rep.error(f"ap_check_victory_condition sends the Victory check in {victory_sends} goal branches; expected 4 (goals 0-3)")
    for g in "0123":
        if g not in goal_branches:
            rep.error(f"ap_check_victory_condition has no branch for ap_goal_{g}")

    rep.ok(f"{len(by_id) - len(catalog_ids)} static locations cross-checked against mod senders/detection")


def check_tech_blocks(rep: Report, catalog):
    text = read(BLOCKS_FILE)
    hooks = set(re.findall(r"has_country_flag\s*=\s*ap_tech_blocked_(tech_\w+)", text))
    defined = set(re.findall(r"^(tech_\w+)\s*=\s*\{", text, re.M))
    missing = [t.key for t in catalog.TECH_CATALOG if t.key not in hooks]
    for key in missing:
        rep.error(f"catalog tech {key} has no ap_tech_blocked_ hook in 00_aaa_ap_tech_blocks.txt")
    for key in sorted(defined - {t.key for t in catalog.TECH_CATALOG}):
        rep.error(f"00_aaa_ap_tech_blocks.txt overrides {key}, which is not in the catalog")
    # Every override must carry its hook inside its own block, and must
    # have exactly one top-level trigger block of each kind: Clausewitz
    # logs "Duplicate trigger" and silently drops the second `potential`,
    # which would unblock the tech (seen in the wild with an earlier
    # generator that appended a second potential block).
    # Only keys the generator injects or that define identity. Vanilla
    # itself repeats weight_modifier/ai_weight in a few techs; copying
    # that verbatim is fine.
    singletons = ("potential", "prerequisites", "cost", "tier", "area")
    for m in re.finditer(r"^(tech_\w+)\s*=\s*\{", text, re.M):
        key = m.group(1)
        i, depth, names = m.end(), 1, []
        while i < len(text) and depth > 0:
            c = text[i]
            if c == "#":
                i = text.find("\n", i)
                if i < 0:
                    break
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif depth == 1 and c.isalpha():
                km = re.match(r"([a-z_]+)\s*=", text[i:i + 40])
                if km:
                    names.append(km.group(1))
                    i += len(km.group(1))
                    continue
            i += 1
        block = text[m.start():i]
        if f"ap_tech_blocked_{key}" not in block:
            rep.error(f"00_aaa_ap_tech_blocks.txt: {key}'s block lacks its own ap_tech_blocked_{key} hook")
        for name in singletons:
            if names.count(name) > 1:
                rep.error(f"00_aaa_ap_tech_blocks.txt: {key} has {names.count(name)} top-level "
                          f"'{name}' blocks — Stellaris drops duplicates (\"Duplicate trigger\")")
    rep.ok(f"{len(catalog.TECH_CATALOG)} catalog techs have blocking hooks (single potential each)")


def check_localisation(rep: Report):
    loc_keys = set(re.findall(r"^\s*([A-Za-z0-9_.]+):\d+\s+\"", read(LOC_FILE), re.M))
    refs = set()
    for evt in (MOD / "events").glob("*.txt"):
        text = strip_comments(read(evt))
        refs |= set(re.findall(r"\b(?:title|desc|name|text)\s*=\s*\"?([a-z0-9_]+\.[a-z0-9_.]+)\"?", text))
    for key in sorted(refs - loc_keys):
        rep.error(f"events reference localisation key {key!r}, missing from ap_l_english.yml")
    rep.ok(f"{len(refs)} event localisation keys resolved")


def check_braces(rep: Report):
    count = 0
    for p in MOD.rglob("*.txt"):
        bal = brace_balance(read(p))
        if bal != 0:
            rep.error(f"{p.relative_to(REPO)}: unbalanced braces (depth {bal} at EOF)")
        count += 1
    rep.ok(f"{count} Paradox script files have balanced braces")


def check_resync(rep: Report, write: bool):
    expected = build_resync(read(DETECTION_FILE), read(SENDERS_FILE))
    if write:
        RESYNC_FILE.write_text(expected, encoding="utf-8")
        rep.ok(f"wrote {RESYNC_FILE.relative_to(REPO)}")
        return
    if not RESYNC_FILE.exists():
        rep.error(f"{RESYNC_FILE.relative_to(REPO)} is missing — run with --write")
    elif read(RESYNC_FILE) != expected:
        rep.error(f"{RESYNC_FILE.relative_to(REPO)} is stale — run with --write")
    else:
        rep.ok("ap_resync.txt is up to date")
    if VICTORY_FLAG not in expected:
        rep.error("resync does not cover the Victory check")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="regenerate mod-install/.../ap_resync.txt")
    args = parser.parse_args()

    rep = Report()
    catalog, items, locations = load_apworld_modules()
    bridge = load_client_bridge()

    check_catalog_sync(rep)
    check_items(rep, items, bridge)
    check_locations(rep, catalog, locations, bridge)
    check_tech_blocks(rep, catalog)
    check_localisation(rep)
    check_braces(rep)
    check_resync(rep, args.write)

    for n in rep.notes:
        print(f"  ok   {n}")
    for e in rep.errors:
        print(f"  FAIL {e}")
    if rep.errors:
        print(f"\n{len(rep.errors)} coherence error(s)")
        return 1
    print("\nAll layers coherent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
