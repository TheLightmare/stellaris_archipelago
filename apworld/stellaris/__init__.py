"""Stellaris Archipelago World.

Integrates Paradox Interactive's Stellaris with the Archipelago
multiworld randomizer. Players complete in-game milestones to send
checks, and receive progressive unlocks from the multiworld.
"""

from typing import Any, Dict, List

from BaseClasses import ItemClassification, Tutorial
from Options import OptionGroup
from worlds.AutoWorld import WebWorld, World

from .items import (
    ALL_ITEMS,
    FILLER_ITEMS,
    TRAP_ITEMS,
    StellarisItem,
    get_filler_item_names,
    get_items_for_options,
)
from .locations import ALL_LOCATIONS, StellarisLocation, get_locations_for_options
from .options import (
    StellarisOptions,
    DlcApocalypse,
    DlcFederations,
    DlcLeviathans,
    DlcMegaCorp,
    DlcNemesis,
    DlcOverlord,
    DlcUtopia,
    EnergyLinkEnabled,
    EnergyLinkRate,
    GalaxySize,
    Goal,
    IncludeCrisis,
    IncludeDiplomacy,
    IncludeExploration,
    IncludeWarfare,
    TrapPercentage,
    TrapsEnabled,
)
from .regions import create_regions
from .rules import set_rules


class StellarisWebWorld(WebWorld):
    theme = "dirt"
    rich_text_options_doc = True

    bug_report_page = "https://github.com/ArchipelagoMW/Archipelago/issues"

    item_descriptions = {
        "Progressive Ship Class": "Each receipt unlocks the next ship tier: "
                                  "Destroyer, Cruiser, Battleship, Titan, Juggernaut.",
        "Progressive Weapons": "Advances all weapon types by one tier.",
        "Progressive Defenses": "Advances armor and shield technology by one tier.",
        "Progressive FTL": "Upgrades FTL capability: better hyperdrives, then Jump Drive, then Psi Jump Drive.",
        "Progressive Starbase": "Upgrades starbase capacity: Starport, Starhold, Star Fortress, Citadel.",
        "Progressive Colony Ship": "Unlocks colonization of increasingly hostile planet types.",
        "Progressive Administration": "Expands empire size and sector management capacity.",
        "Progressive Diplomacy": "Unlocks diplomatic actions: pacts, federations, custodianship.",
        "Progressive Megastructure": "Advances megastructure construction capability (requires Utopia).",
        "Mega-Engineering License": "Prerequisite unlock for researching Mega-Engineering and building megastructures.",
        "Ascension Path: Biological": "Unlocks the Biological Ascension path.",
        "Ascension Path: Synthetic": "Unlocks the Synthetic Ascension path.",
        "Ascension Path: Psionic": "Unlocks the Psionic Ascension path.",
        "L-Gate Insight": "Collect 7 to open the L-Cluster. Each one counts toward the threshold.",
        "Precursor Unlock": "Allows completion of a Precursor anomaly chain.",
        "Crisis Beacon": "Progression item related to endgame crisis events.",
        "Galactic Market Nomination": "Useful economic boost — helps secure the Galactic Market in your territory.",
        "Pirate Surge": "Trap: spawns a dangerous pirate fleet in your territory.",
        "Diplomatic Incident": "Trap: tanks your opinion with a random empire.",
        "Research Setback": "Trap: reduces current research progress.",
        "Market Crash": "Trap: temporarily crashes your internal market prices.",
        "Space Amoeba Migration": "Trap: hostile space amoebas appear in your borders.",
        "Border Friction": "Trap: generates border friction with neighboring empires.",
    }

    location_descriptions = {
        "Explore the L-Cluster": "Requires 7 L-Gate Insight items to open the L-Gates.",
        "Complete a Precursor Chain": "Requires the Precursor Unlock item.",
        "Build a Megastructure": "Requires Mega-Engineering License and Progressive Megastructure.",
        "Complete a Megastructure": "Requires Mega-Engineering License and two Progressive Megastructure receipts.",
        "Complete Biological Ascension": "Requires the Ascension Path: Biological item.",
        "Complete Synthetic Ascension": "Requires the Ascension Path: Synthetic item.",
        "Complete Psionic Ascension": "Requires the Ascension Path: Psionic item.",
        "Victory": "Standard Stellaris victory — used as the default goal.",
        "Defeat the Endgame Crisis": "Requires top-tier military progression to defeat the crisis.",
        "Form the Galactic Imperium": "Requires maximum diplomatic progression (Federations DLC).",
    }

    option_groups = [
        OptionGroup("Gameplay", [
            Goal,
            GalaxySize,
            IncludeExploration,
            IncludeDiplomacy,
            IncludeWarfare,
            IncludeCrisis,
        ]),
        OptionGroup("Traps", [
            TrapsEnabled,
            TrapPercentage,
        ]),
        OptionGroup("EnergyLink", [
            EnergyLinkEnabled,
            EnergyLinkRate,
        ]),
        OptionGroup("DLC", [
            DlcUtopia,
            DlcFederations,
            DlcNemesis,
            DlcLeviathans,
            DlcApocalypse,
            DlcMegaCorp,
            DlcOverlord,
        ]),
    ]

    options_presets = {
        "Base Game Quick": {
            "goal": 0,
            "galaxy_size": 0,
            "include_diplomacy": True,
            "include_warfare": True,
            "include_crisis": False,
            "traps_enabled": False,
            "dlc_utopia": True,
            "dlc_federations": False,
            "dlc_nemesis": False,
            "dlc_leviathans": False,
            "dlc_apocalypse": False,
            "dlc_megacorp": False,
            "dlc_overlord": False,
        },
        "Full DLC Experience": {
            "goal": 1,
            "galaxy_size": 2,
            "include_diplomacy": True,
            "include_warfare": True,
            "include_crisis": True,
            "traps_enabled": True,
            "trap_percentage": 10,
            "dlc_utopia": True,
            "dlc_federations": True,
            "dlc_nemesis": True,
            "dlc_leviathans": True,
            "dlc_apocalypse": True,
            "dlc_megacorp": True,
            "dlc_overlord": True,
        },
        "Ascension Challenge": {
            "goal": 2,
            "galaxy_size": 1,
            "include_diplomacy": True,
            "include_warfare": True,
            "include_crisis": True,
            "traps_enabled": True,
            "trap_percentage": 15,
            "dlc_utopia": True,
            "dlc_federations": False,
            "dlc_nemesis": False,
            "dlc_leviathans": True,
            "dlc_apocalypse": False,
            "dlc_megacorp": False,
            "dlc_overlord": False,
        },
    }

    tutorials = [
        Tutorial(
            "Stellaris Archipelago Setup Guide",
            "A guide to setting up Stellaris for Archipelago multiworld.",
            "English",
            "setup_guide.md",
            "setup_guide/en",
            ["Stellaris AP Contributors"],
        )
    ]


class StellarisWorld(World):
    """Stellaris — a grand strategy 4X game set in space.

    Explore the galaxy, research technologies, expand your empire,
    and face endgame crises — all while trading items with other
    Archipelago worlds.
    """

    game = "Stellaris"
    web = StellarisWebWorld()
    topology_present = True
    options_dataclass = StellarisOptions
    options: StellarisOptions

    # Build ID lookup tables from the data modules
    item_name_to_id = {name: data.code for name, data in ALL_ITEMS.items()}
    location_name_to_id = {name: data.code for name, data in ALL_LOCATIONS.items()}

    # Internal state
    _regions: Dict = {}
    energy_link_enabled: bool = False

    def generate_early(self) -> None:
        """Validate options and configure the world."""
        if self.options.goal == 2 and not self.options.dlc_utopia:
            raise Exception(
                "Goal 'Ascension' requires Utopia DLC to be enabled."
            )
        if self.options.goal == 3 and not self.options.dlc_federations:
            raise Exception(
                "Goal 'Galactic Emperor' requires Federations DLC to be enabled."
            )
        self.energy_link_enabled = bool(self.options.energy_link_enabled)

    def create_regions(self) -> None:
        """Create the region graph and populate with locations."""
        self._regions = create_regions(self)

    def create_items(self) -> None:
        """Create the item pool, balanced to match location count."""
        active_items = get_items_for_options(
            include_diplomacy=bool(self.options.include_diplomacy),
            include_warfare=bool(self.options.include_warfare),
            include_crisis=bool(self.options.include_crisis),
            traps_enabled=bool(self.options.traps_enabled),
            dlc_utopia=bool(self.options.dlc_utopia),
            dlc_federations=bool(self.options.dlc_federations),
            dlc_nemesis=bool(self.options.dlc_nemesis),
            dlc_leviathans=bool(self.options.dlc_leviathans),
            dlc_apocalypse=bool(self.options.dlc_apocalypse),
            dlc_megacorp=bool(self.options.dlc_megacorp),
            dlc_overlord=bool(self.options.dlc_overlord),
            randomized_techs=set(self.options.randomized_techs.value),
        )

        # Count locations
        total_locations = sum(
            1 for region in self.multiworld.regions
            if region.player == self.player
            for _ in region.locations
        )

        # Add non-filler items
        item_pool: List[StellarisItem] = []
        for name, data in active_items.items():
            if data.classification != ItemClassification.filler:
                for _ in range(data.count):
                    item_pool.append(
                        StellarisItem(name, data.classification, data.code, self.player)
                    )

        # If we have more non-filler items than locations, trim useful items
        if len(item_pool) > total_locations:
            excess = len(item_pool) - total_locations
            # Remove useful items first (keep progression)
            useful_indices = [
                i for i, item in enumerate(item_pool)
                if item.classification == ItemClassification.useful
            ]
            for idx in reversed(useful_indices[:excess]):
                item_pool.pop(idx)

        # Fill remaining with filler (+ traps if enabled)
        remaining = total_locations - len(item_pool)
        if remaining > 0:
            filler_names = get_filler_item_names()
            trap_names = list(TRAP_ITEMS.keys()) if self.options.traps_enabled else []
            trap_count = (
                int(remaining * self.options.trap_percentage / 100)
                if trap_names else 0
            )
            filler_count = remaining - trap_count

            for _ in range(filler_count):
                name = self.random.choice(filler_names)
                data = FILLER_ITEMS[name]
                item_pool.append(
                    StellarisItem(name, data.classification, data.code, self.player)
                )

            for _ in range(trap_count):
                name = self.random.choice(trap_names)
                data = TRAP_ITEMS[name]
                item_pool.append(
                    StellarisItem(name, data.classification, data.code, self.player)
                )

        self.multiworld.itempool += item_pool

    def set_rules(self) -> None:
        """Set access rules and completion condition using events."""
        set_rules(self._regions, self.player, self.options)

        goal = self.options.goal.value

        if goal == 0:
            # Victory — event in Endgame region, reachable once Endgame is entered
            self._place_goal_event(
                "Goal: Victory", self._regions["Endgame"],
            )
        elif goal == 1:
            # Crisis Averted — same rules as reaching "Defeat the Endgame Crisis"
            self._place_goal_event(
                "Goal: Crisis Averted", self._regions["Endgame"],
                lambda state, p=self.player: (
                    state.has("Progressive Ship Class", p, 4)
                    and state.has("Progressive Weapons", p, 4)
                    and state.has("Progressive Defenses", p, 3)
                ),
            )
        elif goal == 2:
            # Ascension — any of the three paths
            self._place_goal_event(
                "Goal: Ascension Complete", self._regions["Late Game"],
                lambda state, p=self.player: (
                    state.has("Ascension Path: Biological", p)
                    or state.has("Ascension Path: Synthetic", p)
                    or state.has("Ascension Path: Psionic", p)
                ),
            )
        elif goal == 3:
            # Galactic Emperor — max diplomacy
            self._place_goal_event(
                "Goal: Galactic Emperor", self._regions["Late Game"],
                lambda state, p=self.player: (
                    state.has("Progressive Diplomacy", p, 3)
                ),
            )
        elif goal == 4:
            # All Checks — reachable when every location can be reached
            all_location_names = [
                loc.name
                for region in self.multiworld.regions
                if region.player == self.player
                for loc in region.locations
            ]
            player = self.player
            self._place_goal_event(
                "Goal: All Checks Complete", self._regions["Endgame"],
                lambda state, locs=all_location_names, p=player: all(
                    state.can_reach_location(ln, p) for ln in locs
                ),
            )

    def _place_goal_event(self, event_name: str, region, rule=None) -> None:
        """Create an event location + locked event item and set as completion condition."""
        event_location = StellarisLocation(self.player, event_name, None, region)
        if rule:
            event_location.access_rule = rule
        event_item = StellarisItem(event_name, ItemClassification.progression, None, self.player)
        event_location.place_locked_item(event_item)
        region.locations.append(event_location)
        self.multiworld.completion_condition[self.player] = (
            lambda state, name=event_name, p=self.player: state.has(name, p)
        )

    def create_item(self, name: str) -> "StellarisItem":
        """Create an item by name. Required by AP framework."""
        item_data = ALL_ITEMS.get(name)
        if item_data:
            return StellarisItem(name, item_data.classification, item_data.code, self.player)
        raise KeyError(f"No item named '{name}' in Stellaris")

    def get_filler_item_name(self) -> str:
        return self.random.choice(get_filler_item_names())

    def fill_slot_data(self) -> Dict[str, Any]:
        """Data sent to the client for connection setup."""
        return {
            "goal": self.options.goal.value,
            "energy_link_enabled": self.energy_link_enabled,
            "energy_link_rate": self.options.energy_link_rate.value,
            "galaxy_size": self.options.galaxy_size.value,
            # Catalog tech keys the player chose to randomize. The bridge
            # uses this to (a) send tech-blocking flags at connect time,
            # (b) build the dynamic ITEM_EFFECT_MAP for "Tech: <X>" items,
            # (c) compute TECH_LOCATION_IDS for the slot.
            "randomized_techs": sorted(self.options.randomized_techs.value),
        }
