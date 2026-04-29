"""Item definitions for the Stellaris Archipelago world."""

from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Set

from BaseClasses import Item, ItemClassification


class StellarisItem(Item):
    game = "Stellaris"


class ItemCategory(IntEnum):
    PROGRESSIVE = 0
    UNIQUE = 1
    FILLER = 2
    TRAP = 3


class ItemData(NamedTuple):
    code: int
    category: ItemCategory
    classification: ItemClassification
    count: int = 1  # how many copies go into the pool
    dlc: Optional[str] = None  # None = base game
    group: Optional[str] = None  # for grouping related checks


# Base ID offset for Stellaris items in the AP ID space
BASE_ID = 7_471_000  # "STLR" on a phone keypad, roughly

# =============================================================================
# Progressive Items
# =============================================================================
# These are the core gates. Each receipt advances the player one tier.

PROGRESSIVE_ITEMS: Dict[str, ItemData] = {
    # Ship classes: Corvette (free) → Destroyer → Cruiser → Battleship → Titan → Juggernaut
    "Progressive Ship Class": ItemData(
        BASE_ID + 0, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=5,
        group="ships",
    ),
    # Weapon tiers across all weapon types (4 tiers: tier 2 through 5)
    "Progressive Weapons": ItemData(
        BASE_ID + 1, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=4,
        group="military",
    ),
    # Armor & shield tiers
    "Progressive Defenses": ItemData(
        BASE_ID + 2, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=4,
        group="military",
    ),
    # Hyperlane range → Jump Drive → Psi Jump Drive
    "Progressive FTL": ItemData(
        BASE_ID + 3, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=3,
        group="exploration",
    ),
    # Outpost → Starport → Starhold → Star Fortress → Citadel
    "Progressive Starbase": ItemData(
        BASE_ID + 4, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=3,
        group="expansion",
    ),
    # Colonize increasingly hostile planets
    "Progressive Colony Ship": ItemData(
        BASE_ID + 5, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=3,
        group="expansion",
    ),
    # Empire size / sector management tiers
    "Progressive Administration": ItemData(
        BASE_ID + 6, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=3,
        group="expansion",
    ),
    # Diplomatic actions (basic diplo → federations → custodian)
    "Progressive Diplomacy": ItemData(
        BASE_ID + 7, ItemCategory.PROGRESSIVE,
        ItemClassification.progression, count=3,
        group="diplomacy",
    ),

    "Progressive Megastructure": ItemData(
        BASE_ID + 101, ItemCategory.UNIQUE,
        ItemClassification.progression, count=3,
        dlc="utopia", group="megastructures",
    ),
}

# =============================================================================
# Unique Items (one-time unlocks)
# =============================================================================

UNIQUE_ITEMS: Dict[str, ItemData] = {
    "Mega-Engineering License": ItemData(
        BASE_ID + 100, ItemCategory.UNIQUE,
        ItemClassification.progression,
        dlc="utopia", group="megastructures",
    ),    "Ascension Path: Biological": ItemData(
        BASE_ID + 110, ItemCategory.UNIQUE,
        ItemClassification.progression,
        dlc="utopia", group="ascension",
    ),
    "Ascension Path: Synthetic": ItemData(
        BASE_ID + 111, ItemCategory.UNIQUE,
        ItemClassification.progression,
        dlc="utopia", group="ascension",
    ),
    "Ascension Path: Psionic": ItemData(
        BASE_ID + 112, ItemCategory.UNIQUE,
        ItemClassification.progression,
        dlc="utopia", group="ascension",
    ),
    "L-Gate Insight": ItemData(
        BASE_ID + 120, ItemCategory.UNIQUE,
        ItemClassification.progression, count=7,
        group="exploration",
    ),
    "Precursor Unlock": ItemData(
        BASE_ID + 121, ItemCategory.UNIQUE,
        ItemClassification.progression,
        group="exploration",
    ),
    "Galactic Market Nomination": ItemData(
        BASE_ID + 130, ItemCategory.UNIQUE,
        ItemClassification.useful,
        group="economy",
    ),
    "Crisis Beacon": ItemData(
        BASE_ID + 140, ItemCategory.UNIQUE,
        ItemClassification.progression,
        group="crisis",
    ),
}

# =============================================================================
# Filler Items
# =============================================================================

FILLER_ITEMS: Dict[str, ItemData] = {
    "Resource Cache (Small)": ItemData(
        BASE_ID + 200, ItemCategory.FILLER,
        ItemClassification.filler, count=5,
    ),
    "Resource Cache (Medium)": ItemData(
        BASE_ID + 201, ItemCategory.FILLER,
        ItemClassification.filler, count=3,
    ),
    "Resource Cache (Large)": ItemData(
        BASE_ID + 202, ItemCategory.FILLER,
        ItemClassification.filler, count=2,
    ),
    "Alloy Shipment (Small)": ItemData(
        BASE_ID + 210, ItemCategory.FILLER,
        ItemClassification.filler, count=4,
    ),
    "Alloy Shipment (Medium)": ItemData(
        BASE_ID + 211, ItemCategory.FILLER,
        ItemClassification.filler, count=2,
    ),
    "Alloy Shipment (Large)": ItemData(
        BASE_ID + 212, ItemCategory.FILLER,
        ItemClassification.filler, count=1,
    ),
    "Research Boost": ItemData(
        BASE_ID + 220, ItemCategory.FILLER,
        ItemClassification.filler, count=4,
    ),
    "Influence Burst": ItemData(
        BASE_ID + 221, ItemCategory.FILLER,
        ItemClassification.filler, count=3,
    ),
    "Unity Windfall": ItemData(
        BASE_ID + 222, ItemCategory.FILLER,
        ItemClassification.filler, count=3,
    ),
    "Minor Relic": ItemData(
        BASE_ID + 223, ItemCategory.FILLER,
        ItemClassification.filler, count=2,
    ),
    "Pop Growth Stimulus": ItemData(
        BASE_ID + 230, ItemCategory.FILLER,
        ItemClassification.useful, count=2,
    ),
    "Edict Fund": ItemData(
        BASE_ID + 231, ItemCategory.FILLER,
        ItemClassification.useful, count=2,
    ),
    "Fleet Cap Increase (+10)": ItemData(
        BASE_ID + 240, ItemCategory.FILLER,
        ItemClassification.useful, count=3,
    ),
    "Fleet Cap Increase (+20)": ItemData(
        BASE_ID + 241, ItemCategory.FILLER,
        ItemClassification.useful, count=2,
    ),
    "Starbase Cap Increase (+1)": ItemData(
        BASE_ID + 242, ItemCategory.FILLER,
        ItemClassification.useful, count=2,
    ),
}

# =============================================================================
# Trap Items
# =============================================================================

TRAP_ITEMS: Dict[str, ItemData] = {
    "Pirate Surge": ItemData(
        BASE_ID + 300, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
    "Diplomatic Incident": ItemData(
        BASE_ID + 301, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
    "Research Setback": ItemData(
        BASE_ID + 302, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
    "Market Crash": ItemData(
        BASE_ID + 303, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
    "Space Amoeba Migration": ItemData(
        BASE_ID + 304, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
    "Border Friction": ItemData(
        BASE_ID + 305, ItemCategory.TRAP,
        ItemClassification.trap,
    ),
}

# =============================================================================
# Helpers
# =============================================================================

ALL_ITEMS: Dict[str, ItemData] = {
    **PROGRESSIVE_ITEMS,
    **UNIQUE_ITEMS,
    **FILLER_ITEMS,
    **TRAP_ITEMS,
}


def get_items_for_options(
    include_diplomacy: bool = True,
    include_warfare: bool = True,
    include_crisis: bool = True,
    traps_enabled: bool = False,
    dlc_utopia: bool = False,
    dlc_federations: bool = False,
    dlc_nemesis: bool = False,
    dlc_leviathans: bool = False,
    dlc_apocalypse: bool = False,
    dlc_megacorp: bool = False,
    dlc_overlord: bool = False,
) -> Dict[str, ItemData]:
    """Return the item pool filtered by the player's YAML options."""
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

    items: Dict[str, ItemData] = {}
    for name, data in ALL_ITEMS.items():
        # Filter by DLC
        if data.dlc not in enabled_dlcs:
            continue
        # Filter by category toggles (must match location filtering)
        if data.group == "diplomacy" and not include_diplomacy:
            continue
        if data.group == "warfare" and not include_warfare:
            continue
        if data.group == "crisis" and not include_crisis:
            continue
        # Traps
        if data.category == ItemCategory.TRAP and not traps_enabled:
            continue
        items[name] = data

    return items


def get_filler_item_names() -> List[str]:
    """Return a list of filler item names for the world's get_filler_item_name."""
    return [name for name, data in FILLER_ITEMS.items()]
