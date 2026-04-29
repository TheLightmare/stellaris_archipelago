"""Location definitions for the Stellaris Archipelago world."""

from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Set

from BaseClasses import Location


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
    "Research Mega-Engineering": LocationData(
        BASE_ID + 1120, LocationTiming.LATE, "tech", "tech",
        dlc="utopia", group="megastructures",
    ),
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
    # Vanilla Tech Research Milestones (auto-detected)
    # ==========================================================
    "Research Planetary Unification": LocationData(
        BASE_ID + 3000, LocationTiming.EARLY, "tech",
    ),
    "Research Eco Simulation": LocationData(
        BASE_ID + 3001, LocationTiming.EARLY, "tech",
    ),
    "Research Powered Exoskeletons": LocationData(
        BASE_ID + 3002, LocationTiming.EARLY, "tech",
    ),
    "Research Alloy Foundries": LocationData(
        BASE_ID + 3003, LocationTiming.EARLY, "tech",
    ),
    "Research Luxury Goods": LocationData(
        BASE_ID + 3004, LocationTiming.EARLY, "tech",
    ),
    "Research Mineral Purification": LocationData(
        BASE_ID + 3005, LocationTiming.EARLY, "tech",
    ),
    "Research Administrative AI": LocationData(
        BASE_ID + 3006, LocationTiming.EARLY, "tech",
    ),
    "Research Robotic Workers": LocationData(
        BASE_ID + 3007, LocationTiming.EARLY, "tech",
    ),
    "Research Fleet Size I": LocationData(
        BASE_ID + 3008, LocationTiming.EARLY, "tech",
    ),
    "Research Navy Size I": LocationData(
        BASE_ID + 3009, LocationTiming.EARLY, "tech",
    ),
    "Research Galactic Markets": LocationData(
        BASE_ID + 3010, LocationTiming.LATE, "tech",
    ),
    "Research Synthetics": LocationData(
        BASE_ID + 3011, LocationTiming.LATE, "tech",
    ),
    "Research Fleet Size V": LocationData(
        BASE_ID + 3012, LocationTiming.LATE, "tech",
    ),
    "Research Habitats II": LocationData(
        BASE_ID + 3013, LocationTiming.LATE, "tech",
    ),
    "Research Climate Restoration": LocationData(
        BASE_ID + 3014, LocationTiming.LATE, "tech",
    ),
    "Research Capital Productivity III": LocationData(
        BASE_ID + 3015, LocationTiming.LATE, "tech",
    ),
    "Research Advanced Alloys": LocationData(
        BASE_ID + 3016, LocationTiming.MID, "tech",
    ),
    "Research Gene Crops": LocationData(
        BASE_ID + 3017, LocationTiming.MID, "tech",
    ),
    "Research Colonial Centralization": LocationData(
        BASE_ID + 3018, LocationTiming.MID, "tech",
    ),
    "Research Interstellar Economics": LocationData(
        BASE_ID + 3019, LocationTiming.MID, "tech",
    ),
    "Research Global Research Initiative": LocationData(
        BASE_ID + 3020, LocationTiming.MID, "tech",
    ),
    "Research Droids": LocationData(
        BASE_ID + 3021, LocationTiming.MID, "tech",
    ),
    "Research Gene Tailoring": LocationData(
        BASE_ID + 3022, LocationTiming.MID, "tech",
    ),
    "Research Cloning": LocationData(
        BASE_ID + 3023, LocationTiming.MID, "tech",
    ),
    "Research Glandular Acclimation": LocationData(
        BASE_ID + 3024, LocationTiming.MID, "tech",
    ),
    "Research Psionic Theory": LocationData(
        BASE_ID + 3025, LocationTiming.MID, "tech",
    ),
    "Research Telepathy": LocationData(
        BASE_ID + 3026, LocationTiming.MID, "tech",
    ),
    "Research Sensors II": LocationData(
        BASE_ID + 3027, LocationTiming.MID, "tech",
    ),
    "Research Sensors III": LocationData(
        BASE_ID + 3028, LocationTiming.MID, "tech",
    ),
    "Research Fleet Size III": LocationData(
        BASE_ID + 3029, LocationTiming.MID, "tech",
    ),
    "Research Navy Size III": LocationData(
        BASE_ID + 3030, LocationTiming.MID, "tech",
    ),
    "Research Centralized Command": LocationData(
        BASE_ID + 3031, LocationTiming.MID, "tech",
    ),
    "Research Habitats I": LocationData(
        BASE_ID + 3032, LocationTiming.MID, "tech",
    ),
    "Research Exotic Gas Extraction": LocationData(
        BASE_ID + 3033, LocationTiming.MID, "tech",
    ),
    "Research Volatile Motes Extraction": LocationData(
        BASE_ID + 3034, LocationTiming.MID, "tech",
    ),
    "Research Rare Crystal Mining": LocationData(
        BASE_ID + 3035, LocationTiming.MID, "tech",
    ),
    "Research Capital Productivity I": LocationData(
        BASE_ID + 3036, LocationTiming.MID, "tech",
    ),
    "Research Global Defense Grid": LocationData(
        BASE_ID + 3037, LocationTiming.MID, "tech",
    ),
    "Research Planetary Shield Generator": LocationData(
        BASE_ID + 3038, LocationTiming.MID, "tech",
    ),
    "Research Galactic Administration": LocationData(
        BASE_ID + 3039, LocationTiming.MID, "tech",
    ),

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
) -> Dict[str, LocationData]:
    """Return the location pool filtered by the player's YAML options."""
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
        locations[name] = data

    return locations
