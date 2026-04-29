"""YAML options for the Stellaris Archipelago world."""

from dataclasses import dataclass
from Options import (
    Choice,
    DefaultOnToggle,
    PerGameCommonOptions,
    Range,
    Toggle,
)


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
