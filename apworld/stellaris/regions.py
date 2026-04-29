"""Region definitions for the Stellaris Archipelago world.

Regions represent logical game phases. Locations are assigned to regions
based on their timing, and access rules gate progression between regions
based on received progressive items.

Region Graph:
    Menu → Early Game → Mid Game → Late Game → Endgame
"""

from typing import Dict, List

from BaseClasses import MultiWorld, Region

from .locations import (
    LocationTiming,
    StellarisLocation,
    get_locations_for_options,
)


REGION_NAMES = {
    LocationTiming.EARLY: "Early Game",
    LocationTiming.MID: "Mid Game",
    LocationTiming.LATE: "Late Game",
    LocationTiming.ENDGAME: "Endgame",
}


def create_regions(world) -> Dict[str, Region]:
    """Create all regions and assign locations to them.

    Returns a dict of region_name → Region for rule attachment.
    """
    multiworld: MultiWorld = world.multiworld
    player: int = world.player
    options = world.options

    # Determine which locations are active
    active_locations = get_locations_for_options(
        include_exploration=bool(options.include_exploration),
        include_diplomacy=bool(options.include_diplomacy),
        include_warfare=bool(options.include_warfare),
        include_crisis=bool(options.include_crisis),
        dlc_utopia=bool(options.dlc_utopia),
        dlc_federations=bool(options.dlc_federations),
        dlc_nemesis=bool(options.dlc_nemesis),
        dlc_leviathans=bool(options.dlc_leviathans),
        dlc_apocalypse=bool(options.dlc_apocalypse),
        dlc_megacorp=bool(options.dlc_megacorp),
        dlc_overlord=bool(options.dlc_overlord),
        randomized_techs=set(options.randomized_techs.value),
    )

    # Create regions
    menu_region = Region("Menu", player, multiworld)
    regions: Dict[str, Region] = {"Menu": menu_region}

    for timing, region_name in REGION_NAMES.items():
        region = Region(region_name, player, multiworld)
        regions[region_name] = region

    # Assign locations to regions
    for loc_name, loc_data in active_locations.items():
        region_name = REGION_NAMES[loc_data.timing]
        region = regions[region_name]
        location = StellarisLocation(player, loc_name, loc_data.code, region)
        region.locations.append(location)

    # Connect regions linearly: Menu → Early → Mid → Late → Endgame
    menu_region.connect(regions["Early Game"])
    regions["Early Game"].connect(regions["Mid Game"], "Early to Mid")
    regions["Mid Game"].connect(regions["Late Game"], "Mid to Late")
    regions["Late Game"].connect(regions["Endgame"], "Late to Endgame")

    # Register all regions
    multiworld.regions += list(regions.values())

    return regions
