"""YAML options for the Stellaris Archipelago world."""

from dataclasses import dataclass
from Options import (
    Choice,
    DefaultOnToggle,
    OptionSet,
    PerGameCommonOptions,
    Range,
    Toggle,
)

from .data.tech_catalog import all_keys as _all_tech_keys
from .data.tech_catalog import default_selection as _default_tech_selection


class Goal(Choice):
    """Win condition for completing this Stellaris world.

    Victory: Achieve any standard Stellaris victory condition.
    Crisis Averted: Defeat the endgame crisis.
    Ascension: Complete any ascension path (requires Utopia DLC).
    Galactic Emperor: Form the Galactic Imperium (requires Federations DLC).
    All Checks: Complete every location in the pool.
    """
    display_name = "Goal"
    option_victory = 0
    option_crisis_averted = 1
    option_ascension = 2
    option_galactic_emperor = 3
    option_all_checks = 4
    default = 0


class GalaxySize(Choice):
    """Galaxy size affects pacing and the number of systems available
    for exploration checks."""
    display_name = "Galaxy Size"
    option_small = 0
    option_medium = 1
    option_large = 2
    option_huge = 3
    default = 1


class IncludeExploration(DefaultOnToggle):
    """Include exploration-based locations (surveying, anomalies, first contact)."""
    display_name = "Include Exploration Checks"


class IncludeDiplomacy(DefaultOnToggle):
    """Include diplomacy-based locations (federations, galactic community, envoys)."""
    display_name = "Include Diplomacy Checks"


class IncludeWarfare(DefaultOnToggle):
    """Include warfare-based locations (winning wars, fleet power, conquering)."""
    display_name = "Include Warfare Checks"


class IncludeCrisis(DefaultOnToggle):
    """Include endgame crisis locations. Disabling removes crisis-related
    checks and items from the pool."""
    display_name = "Include Crisis Checks"


class TrapPercentage(Range):
    """Percentage of filler items that become traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 30
    default = 0


class TrapsEnabled(Toggle):
    """Enable trap items in the item pool."""
    display_name = "Traps Enabled"


class EnergyLinkEnabled(DefaultOnToggle):
    """Enable EnergyLink integration. Allows depositing and withdrawing
    energy credits to/from the shared multiworld energy pool."""
    display_name = "EnergyLink"


class EnergyLinkRate(Range):
    """Energy Credits per EnergyLink unit. Higher values mean each
    EnergyLink unit is worth more EC."""
    display_name = "EnergyLink Rate"
    range_start = 50
    range_end = 500
    default = 100


# --- DLC Toggles ---

class DlcUtopia(DefaultOnToggle):
    """Enable Utopia content (ascension paths, megastructures, hive minds).
    NOTE: As of 2026, Utopia has been folded into the base game.
    This toggle exists for players on older Stellaris versions."""
    display_name = "DLC: Utopia (now base game)"


class DlcFederations(Toggle):
    """Enable Federations DLC content (federation levels, galactic community,
    custodian/imperium)."""
    display_name = "DLC: Federations"


class DlcNemesis(Toggle):
    """Enable Nemesis DLC content (become the crisis, espionage)."""
    display_name = "DLC: Nemesis"


class DlcLeviathans(Toggle):
    """Enable Leviathans DLC content (leviathan encounters, enclaves)."""
    display_name = "DLC: Leviathans"


class DlcApocalypse(Toggle):
    """Enable Apocalypse DLC content (titans, colossi)."""
    display_name = "DLC: Apocalypse"


class DlcMegaCorp(Toggle):
    """Enable MegaCorp DLC content (megacorp civics, caravaneers)."""
    display_name = "DLC: MegaCorp"


class DlcOverlord(Toggle):
    """Enable Overlord DLC content (subject specialization, holdings)."""
    display_name = "DLC: Overlord"


class DlcFirstContact(Toggle):
    """Enable First Contact DLC content (cloaking, pre-FTL techs)."""
    display_name = "DLC: First Contact"


class DlcAncientRelics(Toggle):
    """Enable Ancient Relics DLC content (archaeotech, relics)."""
    display_name = "DLC: Ancient Relics"


class DlcMachineAge(Toggle):
    """Enable The Machine Age DLC content (machine ascension paths,
    synthetic queen techs)."""
    display_name = "DLC: The Machine Age"


class DlcDistantStars(Toggle):
    """Enable Distant Stars DLC content (L-Cluster techs)."""
    display_name = "DLC: Distant Stars"


class DlcAstralPlanes(Toggle):
    """Enable Astral Planes DLC content (astral techs)."""
    display_name = "DLC: Astral Planes"


# --- Tech Randomization ---

class RandomizedTechs(OptionSet):
    """Stellaris technologies randomized through the multiworld.

    Each tech in this set:
      - Becomes a location 'Research <Tech>' in the player's pool.
      - Is BLOCKED from the vanilla research pool (replaced by an AP-tech).
      - Has a matching 'Tech: <Tech>' item placed in the multiworld; the
        only way to get the vanilla effects is to receive that item.

    Default is empty (no vanilla techs randomized). Pick techs here or
    via the Tech Config dashboard tab. Techs belonging to a DLC whose
    toggle is off are ignored."""
    display_name = "Randomized Techs"
    valid_keys = frozenset(_all_tech_keys())
    default = frozenset(_default_tech_selection())


@dataclass
class StellarisOptions(PerGameCommonOptions):
    goal: Goal
    galaxy_size: GalaxySize
    include_exploration: IncludeExploration
    include_diplomacy: IncludeDiplomacy
    include_warfare: IncludeWarfare
    include_crisis: IncludeCrisis
    traps_enabled: TrapsEnabled
    trap_percentage: TrapPercentage
    energy_link_enabled: EnergyLinkEnabled
    energy_link_rate: EnergyLinkRate
    dlc_utopia: DlcUtopia
    dlc_federations: DlcFederations
    dlc_nemesis: DlcNemesis
    dlc_leviathans: DlcLeviathans
    dlc_apocalypse: DlcApocalypse
    dlc_megacorp: DlcMegaCorp
    dlc_overlord: DlcOverlord
    dlc_first_contact: DlcFirstContact
    dlc_ancient_relics: DlcAncientRelics
    dlc_machine_age: DlcMachineAge
    dlc_distant_stars: DlcDistantStars
    dlc_astral_planes: DlcAstralPlanes
    randomized_techs: RandomizedTechs


def enabled_dlcs(options: "StellarisOptions") -> frozenset:
    """The set of DLC flag strings enabled by this options set.

    ``None`` (base game) is always included. Keys match the ``dlc``
    field used in items.py, locations.py, and data/tech_catalog.py.
    """
    flags = {None}
    for flag, opt in (
        ("utopia", options.dlc_utopia),
        ("federations", options.dlc_federations),
        ("nemesis", options.dlc_nemesis),
        ("leviathans", options.dlc_leviathans),
        ("apocalypse", options.dlc_apocalypse),
        ("megacorp", options.dlc_megacorp),
        ("overlord", options.dlc_overlord),
        ("first_contact", options.dlc_first_contact),
        ("ancient_relics", options.dlc_ancient_relics),
        ("machine_age", options.dlc_machine_age),
        ("distant_stars", options.dlc_distant_stars),
        ("astral_planes", options.dlc_astral_planes),
    ):
        if opt:
            flags.add(flag)
    return frozenset(flags)
