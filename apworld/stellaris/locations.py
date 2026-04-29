"""Location definitions for the Stellaris Archipelago world."""

from enum import IntEnum
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Set

from BaseClasses import Location

from .data.tech_catalog import TECH_CATALOG, location_name as _tech_location_name


class StellarisLocation(Location):
    game = "Stellaris"


class LocationTiming(IntEnum):
    EARLY = 0
    MID = 1
    LATE = 2
    ENDGAME = 3


class LocationData(NamedTuple):
    code: int
    timing: LocationTiming
    category: str  # exploration, tech, expansion, diplomacy, warfare, traditions, crisis
    location_type: str = "milestone"  # "milestone" = auto-detected, "tech" = researchable AP tech
    dlc: Optional[str] = None  # None = base game
    group: Optional[str] = None  # for grouping related checks


BASE_ID = 7_471_000  # Same base as items, locations start at +1000

# =============================================================================
# Exploration Locations
# =============================================================================

EXPLORATION_LOCATIONS: Dict[str, LocationData] = {
    "Survey 5 Systems": LocationData(
        BASE_ID + 1000, LocationTiming.EARLY, "exploration",
    ),
    "Survey 10 Systems": LocationData(
        BASE_ID + 1001, LocationTiming.EARLY, "exploration",
    ),
    "Survey 20 Systems": LocationData(
        BASE_ID + 1002, LocationTiming.MID, "exploration",
    ),
    "Survey 30 Systems": LocationData(
        BASE_ID + 1003, LocationTiming.MID, "exploration",
    ),
    "First Contact": LocationData(
        BASE_ID + 1010, LocationTiming.EARLY, "exploration",
    ),
    "Second Contact": LocationData(
        BASE_ID + 1011, LocationTiming.EARLY, "exploration",
    ),
    "Find 3 Anomalies": LocationData(
        BASE_ID + 1020, LocationTiming.EARLY, "exploration", "tech",
    ),
    "Find 6 Anomalies": LocationData(
        BASE_ID + 1021, LocationTiming.MID, "exploration", "tech",
    ),
    "Enter a Wormhole": LocationData(
        BASE_ID + 1030, LocationTiming.MID, "exploration", "tech",
    ),
    "Complete a Precursor Chain": LocationData(
        BASE_ID + 1040, LocationTiming.MID, "exploration", "tech",
        group="precursors",
    ),
    "Explore the L-Cluster": LocationData(
        BASE_ID + 1050, LocationTiming.LATE, "exploration", "tech",
        group="lgates",
    ),
}

# =============================================================================
# Technology Locations
# =============================================================================

TECH_LOCATIONS: Dict[str, LocationData] = {
    "Research 5 Technologies": LocationData(
        BASE_ID + 1100, LocationTiming.EARLY, "tech",
    ),
    "Research 15 Technologies": LocationData(
        BASE_ID + 1101, LocationTiming.EARLY, "tech",
    ),
    "Research 30 Technologies": LocationData(
        BASE_ID + 1102, LocationTiming.MID, "tech",
    ),
    "Research 50 Technologies": LocationData(
        BASE_ID + 1103, LocationTiming.LATE, "tech",
    ),
    "Research a Rare Tech": LocationData(
        BASE_ID + 1110, LocationTiming.MID, "tech", "tech",
    ),
    # NOTE: "Research Mega-Engineering" used to live here; it's now provided
    # by the comprehensive tech catalog (data/tech_catalog.py), which scans
    # in tech_mega_engineering directly. Don't re-add this static entry —
    # it would name-collide with the catalog's Research-X for that tech.
    "Research a Repeatable Tech": LocationData(
        BASE_ID + 1130, LocationTiming.LATE, "tech", "tech",
    ),
}

# =============================================================================
# Expansion & Economy Locations
# =============================================================================

EXPANSION_LOCATIONS: Dict[str, LocationData] = {
    "Colonize 1 Planet": LocationData(
        BASE_ID + 1200, LocationTiming.EARLY, "expansion",
    ),
    "Colonize 3 Planets": LocationData(
        BASE_ID + 1201, LocationTiming.EARLY, "expansion",
    ),
    "Colonize 5 Planets": LocationData(
        BASE_ID + 1202, LocationTiming.MID, "expansion",
    ),
    "Colonize 10 Planets": LocationData(
        BASE_ID + 1203, LocationTiming.LATE, "expansion",
    ),
    "Reach 50 Pops": LocationData(
        BASE_ID + 1210, LocationTiming.EARLY, "expansion",
    ),
    "Reach 100 Pops": LocationData(
        BASE_ID + 1211, LocationTiming.MID, "expansion",
    ),
    "Reach 200 Pops": LocationData(
        BASE_ID + 1212, LocationTiming.LATE, "expansion",
    ),
    "Own 5 Starbases": LocationData(
        BASE_ID + 1220, LocationTiming.EARLY, "expansion",
    ),
    "Own 10 Starbases": LocationData(
        BASE_ID + 1221, LocationTiming.MID, "expansion",
    ),
    "Reach 1k Monthly Energy": LocationData(
        BASE_ID + 1230, LocationTiming.MID, "expansion",
    ),
    "Reach 1k Monthly Alloys": LocationData(
        BASE_ID + 1231, LocationTiming.LATE, "expansion",
    ),
    "Build a Megastructure": LocationData(
        BASE_ID + 1240, LocationTiming.LATE, "expansion", "tech",
        dlc="utopia", group="megastructures",
    ),
    "Complete a Megastructure": LocationData(
        BASE_ID + 1241, LocationTiming.LATE, "expansion", "tech",
        dlc="utopia", group="megastructures",
    ),
}

# =============================================================================
# Diplomacy Locations
# =============================================================================

DIPLOMACY_LOCATIONS: Dict[str, LocationData] = {
    "Form or Join a Federation": LocationData(
        BASE_ID + 1300, LocationTiming.MID, "diplomacy", "tech",
        dlc="federations",
    ),
    "Federation Level 3": LocationData(
        BASE_ID + 1301, LocationTiming.LATE, "diplomacy", "tech",
        dlc="federations",
    ),
    "Federation Level 5": LocationData(
        BASE_ID + 1302, LocationTiming.LATE, "diplomacy", "tech",
        dlc="federations",
    ),
    "Join Galactic Community": LocationData(
        BASE_ID + 1310, LocationTiming.MID, "diplomacy", "tech",
        dlc="federations",
    ),
    "Pass a Galactic Resolution": LocationData(
        BASE_ID + 1311, LocationTiming.MID, "diplomacy", "tech",
        dlc="federations",
    ),
    "Become Custodian": LocationData(
        BASE_ID + 1320, LocationTiming.LATE, "diplomacy", "tech",
        dlc="federations",
    ),
    "Form the Galactic Imperium": LocationData(
        BASE_ID + 1321, LocationTiming.LATE, "diplomacy", "tech",
        dlc="federations",
    ),
    "Integrate a Subject": LocationData(
        BASE_ID + 1330, LocationTiming.MID, "diplomacy", "tech",
    ),
    "Sign a Non-Aggression Pact": LocationData(
        BASE_ID + 1340, LocationTiming.EARLY, "diplomacy",
    ),
    "Sign a Defensive Pact": LocationData(
        BASE_ID + 1341, LocationTiming.MID, "diplomacy",
    ),
    "Have 3 Envoys Active": LocationData(
        BASE_ID + 1350, LocationTiming.MID, "diplomacy", "tech",
    ),
}

# =============================================================================
# Warfare & Military Locations
# =============================================================================

WARFARE_LOCATIONS: Dict[str, LocationData] = {
    "Win First War": LocationData(
        BASE_ID + 1400, LocationTiming.MID, "warfare",
    ),
    "Win 3 Wars": LocationData(
        BASE_ID + 1401, LocationTiming.LATE, "warfare",
    ),
    "Destroy a Starbase": LocationData(
        BASE_ID + 1410, LocationTiming.MID, "warfare", "tech",
    ),
    "Conquer a Capital": LocationData(
        BASE_ID + 1420, LocationTiming.LATE, "warfare", "tech",
    ),
    "Achieve 50k Fleet Power": LocationData(
        BASE_ID + 1430, LocationTiming.MID, "warfare",
    ),
    "Achieve 100k Fleet Power": LocationData(
        BASE_ID + 1431, LocationTiming.LATE, "warfare",
    ),
    "Achieve 200k Fleet Power": LocationData(
        BASE_ID + 1432, LocationTiming.LATE, "warfare",
    ),
    "Defeat a Leviathan": LocationData(
        BASE_ID + 1440, LocationTiming.LATE, "warfare", "tech",
        dlc="leviathans",
    ),
    "Destroy a Fallen Empire": LocationData(
        BASE_ID + 1450, LocationTiming.LATE, "warfare", "tech",
    ),
}

# =============================================================================
# Tradition & Ascension Locations
# =============================================================================

TRADITION_LOCATIONS: Dict[str, LocationData] = {
    "Complete 1 Tradition Tree": LocationData(
        BASE_ID + 1500, LocationTiming.EARLY, "traditions",
    ),
    "Complete 3 Tradition Trees": LocationData(
        BASE_ID + 1501, LocationTiming.MID, "traditions",
    ),
    "Complete 5 Tradition Trees": LocationData(
        BASE_ID + 1502, LocationTiming.LATE, "traditions",
    ),
    "Adopt 1 Ascension Perk": LocationData(
        BASE_ID + 1510, LocationTiming.EARLY, "traditions",
    ),
    "Adopt 3 Ascension Perks": LocationData(
        BASE_ID + 1511, LocationTiming.MID, "traditions",
    ),
    "Adopt 5 Ascension Perks": LocationData(
        BASE_ID + 1512, LocationTiming.LATE, "traditions",
    ),
    "Complete Biological Ascension": LocationData(
        BASE_ID + 1520, LocationTiming.LATE, "traditions", "tech",
        dlc="utopia", group="ascension",
    ),
    "Complete Synthetic Ascension": LocationData(
        BASE_ID + 1521, LocationTiming.LATE, "traditions", "tech",
        dlc="utopia", group="ascension",
    ),
    "Complete Psionic Ascension": LocationData(
        BASE_ID + 1522, LocationTiming.LATE, "traditions", "tech",
        dlc="utopia", group="ascension",
    ),
}

# =============================================================================
# Crisis & Endgame Locations
# =============================================================================

CRISIS_LOCATIONS: Dict[str, LocationData] = {
    "Survive the Crisis 10 Years": LocationData(
        BASE_ID + 1600, LocationTiming.ENDGAME, "crisis", "tech",
    ),
    "Defeat the Endgame Crisis": LocationData(
        BASE_ID + 1601, LocationTiming.ENDGAME, "crisis", "tech",
    ),
    "Become the Crisis Tier 1": LocationData(
        BASE_ID + 1610, LocationTiming.LATE, "crisis", "tech",
        dlc="nemesis",
    ),
    "Become the Crisis Tier 5": LocationData(
        BASE_ID + 1611, LocationTiming.ENDGAME, "crisis", "tech",
        dlc="nemesis",
    ),
    "Control 40% of Galaxy": LocationData(
        BASE_ID + 1620, LocationTiming.LATE, "crisis", "tech",
    ),
    "Control 60% of Galaxy": LocationData(
        BASE_ID + 1621, LocationTiming.ENDGAME, "crisis", "tech",
    ),
}

# =============================================================================
# Victory Locations (always exactly one, based on goal)
# =============================================================================

VICTORY_LOCATIONS: Dict[str, LocationData] = {
    "Victory": LocationData(
        BASE_ID + 1900, LocationTiming.ENDGAME, "victory",
    ),
}

# =============================================================================
# Helpers
# =============================================================================

ALL_LOCATIONS: Dict[str, LocationData] = {
    **EXPLORATION_LOCATIONS,
    **TECH_LOCATIONS,
    **EXPANSION_LOCATIONS,
    **DIPLOMACY_LOCATIONS,
    **WARFARE_LOCATIONS,
    **TRADITION_LOCATIONS,
    **CRISIS_LOCATIONS,
    **VICTORY_LOCATIONS,

    # ==========================================================
    # Vanilla Tech Research Milestones + Gameplay Milestones
    # ==========================================================

    # ==========================================================
    # Vanilla Tech Research (catalog-driven, IDs BASE_ID + 10000+)
    # See data/tech_catalog.py — these are tech-type locations whose
    # vanilla counterparts get blocked when the player selects them
    # via the randomized_techs YAML option. The +10000 offset keeps
    # them well clear of the +3000-3999 milestone range above.
    # ==========================================================
    **{
        _tech_location_name(_t): LocationData(
            BASE_ID + 10000 + _t.offset,
            LocationTiming.EARLY if _t.tier <= 1
            else LocationTiming.MID if _t.tier <= 3
            else LocationTiming.LATE,
            "tech",
            location_type="tech",
            dlc=_t.dlc,
        )
        for _t in TECH_CATALOG
    },


    # ==========================================================
    # Gameplay Milestones (monthly scanner)
    # ==========================================================
    "Reach 10k Fleet Power": LocationData(
        BASE_ID + 3040, LocationTiming.EARLY, "warfare",
    ),
    "Own 100 Systems": LocationData(
        BASE_ID + 3041, LocationTiming.LATE, "exploration",
    ),
    "Own 20 Systems": LocationData(
        BASE_ID + 3042, LocationTiming.EARLY, "exploration",
    ),
    "Reach 25k Fleet Power": LocationData(
        BASE_ID + 3043, LocationTiming.MID, "warfare",
    ),
    "Own 50 Systems": LocationData(
        BASE_ID + 3044, LocationTiming.MID, "exploration",
    ),
    "Reach 100 Monthly Research": LocationData(
        BASE_ID + 3045, LocationTiming.EARLY, "tech",
    ),
    "Reach 1k Monthly Research": LocationData(
        BASE_ID + 3046, LocationTiming.LATE, "tech",
    ),
    "Reach 500 Monthly Research": LocationData(
        BASE_ID + 3047, LocationTiming.MID, "tech",
    ),
    "Reach 500 Pops": LocationData(
        BASE_ID + 3048, LocationTiming.LATE, "expansion",
    ),
    "Stockpile 10k Alloys": LocationData(
        BASE_ID + 3049, LocationTiming.LATE, "expansion",
    ),
    "Stockpile 10k Energy": LocationData(
        BASE_ID + 3050, LocationTiming.EARLY, "expansion",
    ),
    "Stockpile 10k Minerals": LocationData(
        BASE_ID + 3051, LocationTiming.EARLY, "expansion",
    ),
    "Stockpile 5k Alloys": LocationData(
        BASE_ID + 3052, LocationTiming.MID, "expansion",
    ),
}


def get_locations_for_options(
    include_exploration: bool = True,
    include_diplomacy: bool = True,
    include_warfare: bool = True,
    include_crisis: bool = True,
    dlc_utopia: bool = False,
    dlc_federations: bool = False,
    dlc_nemesis: bool = False,
    dlc_leviathans: bool = False,
    dlc_apocalypse: bool = False,
    dlc_megacorp: bool = False,
    dlc_overlord: bool = False,
    randomized_techs: Optional[Iterable[str]] = None,
) -> Dict[str, LocationData]:
    """Return the location pool filtered by the player's YAML options.

    ``randomized_techs`` is the set of Stellaris tech keys the player chose
    to randomize. Catalog-driven Research-X locations are kept only for
    those techs; the rest are dropped from the slot. ``None`` keeps all
    catalog techs (used by tests / introspection)."""
    enabled_dlcs: Set[Optional[str]] = {None}  # base game always on
    if dlc_utopia:
        enabled_dlcs.add("utopia")
    if dlc_federations:
        enabled_dlcs.add("federations")
    if dlc_nemesis:
        enabled_dlcs.add("nemesis")
    if dlc_leviathans:
        enabled_dlcs.add("leviathans")
    if dlc_apocalypse:
        enabled_dlcs.add("apocalypse")
    if dlc_megacorp:
        enabled_dlcs.add("megacorp")
    if dlc_overlord:
        enabled_dlcs.add("overlord")

    # Build the set of catalog Research-X names the player picked.
    if randomized_techs is None:
        selected_tech_locations: Optional[FrozenSet[str]] = None
    else:
        wanted = set(randomized_techs)
        selected_tech_locations = frozenset(
            _tech_location_name(t) for t in TECH_CATALOG if t.key in wanted
        )

    locations: Dict[str, LocationData] = {}
    for name, data in ALL_LOCATIONS.items():
        # Filter by DLC
        if data.dlc not in enabled_dlcs:
            continue
        # Filter by category toggles
        if data.category == "exploration" and not include_exploration:
            continue
        if data.category == "diplomacy" and not include_diplomacy:
            continue
        if data.category == "warfare" and not include_warfare:
            continue
        if data.category == "crisis" and not include_crisis:
            continue
        # Filter catalog Research-X locations by player's selection.
        if (selected_tech_locations is not None
                and name.startswith("Research ")
                and BASE_ID + 10000 <= data.code <= BASE_ID + 19999
                and data.location_type == "tech"
                and name not in selected_tech_locations):
            continue
        locations[name] = data

    return locations
