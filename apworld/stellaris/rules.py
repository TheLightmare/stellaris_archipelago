"""Access rules for the Stellaris Archipelago world.

Rules define what items are required to logically reach a region or
complete a specific location. These are used by the AP generator to
ensure the game is completable.
"""

from typing import Dict, Iterable, List
from BaseClasses import CollectionState, Region

from .data.tech_catalog import (
    TECH_CATALOG,
    item_name as _tech_item_name,
    location_name as _tech_location_name,
)


def has(state: CollectionState, player: int, item: str, count: int = 1) -> bool:
    """Shorthand: does the player have at least `count` of `item`?"""
    return state.has(item, player, count)


def find_entrance(region: Region, name: str):
    """Find an entrance by name from a region's exits list."""
    for exit in region.exits:
        if exit.name == name:
            return exit
    raise KeyError(f"Entrance '{name}' not found in region '{region.name}'")


def set_region_rules(regions: Dict[str, Region], player: int) -> None:
    """Set access rules on region-to-region entrances."""

    # Early Game → Mid Game
    mid_entrance = find_entrance(regions["Early Game"], "Early to Mid")
    mid_entrance.access_rule = lambda state: (
        has(state, player, "Progressive Ship Class", 1)
        and has(state, player, "Progressive Starbase", 1)
        and has(state, player, "Progressive Weapons", 1)
    )

    # Mid Game → Late Game
    late_entrance = find_entrance(regions["Mid Game"], "Mid to Late")
    late_entrance.access_rule = lambda state: (
        has(state, player, "Progressive Ship Class", 3)
        and has(state, player, "Progressive Starbase", 3)
        and has(state, player, "Progressive Weapons", 3)
        and has(state, player, "Progressive Defenses", 2)
    )

    # Late Game → Endgame
    endgame_entrance = find_entrance(regions["Late Game"], "Late to Endgame")
    endgame_entrance.access_rule = lambda state: (
        has(state, player, "Progressive Ship Class", 4)
        and has(state, player, "Progressive Weapons", 4)
        and has(state, player, "Progressive Defenses", 3)
    )


def set_location_rules(regions: Dict[str, Region], player: int, options) -> None:
    """Set access rules on individual locations within regions.

    These are *additional* rules beyond the region gate. A location
    inherits its region's entrance rule plus any rules set here.
    """

    def set_rule(loc_name: str, rule):
        """Safely set a rule — skip if the location doesn't exist in this pool."""
        for region in regions.values():
            for loc in region.locations:
                if loc.name == loc_name:
                    loc.access_rule = rule
                    return

    # --- Exploration ---
    set_rule("Explore the L-Cluster", lambda state: (
        has(state, player, "L-Gate Insight", 7)
    ))
    set_rule("Complete a Precursor Chain", lambda state: (
        has(state, player, "Precursor Unlock")
    ))

    # --- Expansion ---
    set_rule("Colonize 5 Planets", lambda state: (
        has(state, player, "Progressive Colony Ship", 2)
    ))
    set_rule("Colonize 10 Planets", lambda state: (
        has(state, player, "Progressive Colony Ship", 3)
    ))

    # --- Megastructures (Utopia) ---
    if options.dlc_utopia:
        set_rule("Build a Megastructure", lambda state: (
            has(state, player, "Mega-Engineering License")
            and has(state, player, "Progressive Megastructure", 1)
        ))
        set_rule("Complete a Megastructure", lambda state: (
            has(state, player, "Mega-Engineering License")
            and has(state, player, "Progressive Megastructure", 2)
        ))
        set_rule("Research Mega-Engineering", lambda state: (
            has(state, player, "Mega-Engineering License")
        ))

    # --- Diplomacy ---
    set_rule("Sign a Defensive Pact", lambda state: (
        has(state, player, "Progressive Diplomacy", 1)
    ))
    set_rule("Integrate a Subject", lambda state: (
        has(state, player, "Progressive Diplomacy", 1)
    ))
    if options.dlc_federations:
        set_rule("Form or Join a Federation", lambda state: (
            has(state, player, "Progressive Diplomacy", 2)
        ))
        set_rule("Federation Level 3", lambda state: (
            has(state, player, "Progressive Diplomacy", 2)
        ))
        set_rule("Federation Level 5", lambda state: (
            has(state, player, "Progressive Diplomacy", 3)
        ))
        set_rule("Become Custodian", lambda state: (
            has(state, player, "Progressive Diplomacy", 3)
        ))
        set_rule("Form the Galactic Imperium", lambda state: (
            has(state, player, "Progressive Diplomacy", 3)
        ))

    # --- Warfare ---
    set_rule("Achieve 100k Fleet Power", lambda state: (
        has(state, player, "Progressive Ship Class", 2)
        and has(state, player, "Progressive Weapons", 2)
    ))
    set_rule("Achieve 200k Fleet Power", lambda state: (
        has(state, player, "Progressive Ship Class", 3)
        and has(state, player, "Progressive Weapons", 3)
    ))
    set_rule("Destroy a Fallen Empire", lambda state: (
        has(state, player, "Progressive Ship Class", 3)
        and has(state, player, "Progressive Weapons", 4)
        and has(state, player, "Progressive Defenses", 3)
    ))
    if options.dlc_leviathans:
        set_rule("Defeat a Leviathan", lambda state: (
            has(state, player, "Progressive Ship Class", 2)
            and has(state, player, "Progressive Weapons", 2)
            and has(state, player, "Progressive Defenses", 2)
        ))

    # --- Crisis ---
    if options.include_crisis:
        set_rule("Defeat the Endgame Crisis", lambda state: (
            has(state, player, "Progressive Ship Class", 4)
            and has(state, player, "Progressive Weapons", 4)
            and has(state, player, "Progressive Defenses", 3)
        ))
        set_rule("Survive the Crisis 10 Years", lambda state: (
            has(state, player, "Progressive Ship Class", 3)
            and has(state, player, "Progressive Weapons", 3)
        ))

    # --- Ascension (Utopia) ---
    if options.dlc_utopia:
        set_rule("Complete Biological Ascension", lambda state: (
            has(state, player, "Ascension Path: Biological")
        ))
        set_rule("Complete Synthetic Ascension", lambda state: (
            has(state, player, "Ascension Path: Synthetic")
        ))
        set_rule("Complete Psionic Ascension", lambda state: (
            has(state, player, "Ascension Path: Psionic")
        ))


def tech_prerequisite_items(selected_keys: Iterable[str]) -> Dict[str, List[str]]:
    """Map each randomized tech's location to the Tech: items it needs.

    In-game, the AP tech that replaces vanilla tech T keeps T's vanilla
    prerequisites. If one of those prerequisites P is *also* randomized,
    the only way to ever obtain P (and therefore research T's AP tech)
    is to receive the "Tech: P" item from the multiworld. Without this
    rule the generator could place "Tech: P" behind "Research T" — a
    seed that can never be completed.

    Returns {"Research T": ["Tech: P", ...]} for every selected T that
    has at least one selected prerequisite.
    """
    selected = set(selected_keys)
    by_key = {t.key: t for t in TECH_CATALOG}
    rules: Dict[str, List[str]] = {}
    for key in selected:
        entry = by_key.get(key)
        if entry is None:
            continue
        needed = [
            _tech_item_name(by_key[p])
            for p in entry.prereqs
            if p in selected and p in by_key
        ]
        if needed:
            rules[_tech_location_name(entry)] = needed
    return rules


def gating_tech_keys(selected_keys: Iterable[str]) -> List[str]:
    """Selected techs that are a prerequisite of another selected tech.

    Their "Tech: X" items gate locations, so they must be classified as
    progression — the fill algorithm only guarantees reachability for
    progression items.
    """
    selected = set(selected_keys)
    by_key = {t.key: t for t in TECH_CATALOG}
    gating = set()
    for key in selected:
        entry = by_key.get(key)
        if entry is None:
            continue
        for p in entry.prereqs:
            if p in selected and p in by_key:
                gating.add(p)
    return sorted(gating)


def set_tech_prerequisite_rules(
    regions: Dict[str, Region], player: int, selected_keys: Iterable[str],
) -> None:
    """AND the Tech: prerequisite items into each Research-X location's rule.

    Applied *after* set_location_rules so a location that already has a
    rule (e.g. "Research Mega-Engineering" needing the license) keeps it.
    """
    required = tech_prerequisite_items(selected_keys)
    if not required:
        return
    for region in regions.values():
        for loc in region.locations:
            items = required.get(loc.name)
            if not items:
                continue
            previous = loc.access_rule
            loc.access_rule = (
                lambda state, prev=previous, needed=tuple(items), p=player: (
                    prev(state) and all(state.has(i, p) for i in needed)
                )
            )


def set_rules(regions: Dict[str, Region], player: int, options,
              selected_tech_keys: Iterable[str] = ()) -> None:
    """Set all access rules for the world."""
    set_region_rules(regions, player)
    set_location_rules(regions, player, options)
    set_tech_prerequisite_rules(regions, player, selected_tech_keys)
