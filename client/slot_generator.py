"""Generate dynamic Stellaris mod files from AP slot data.

When the client connects to the AP server, it receives the full mapping
of locations → items (who gets what when you complete each check). This
script generates:

1. Technology definitions - one researchable tech per AP location, named
   after the item it contains (e.g. "Mothwing Cloak for PlayerB")
2. Localisation - tech names and descriptions with player/game info
3. Scripted effects - on_research_complete hooks for each tech

The generated files go into the Stellaris mod directory and are loaded
when the game starts.

Usage:
    from slot_generator import generate_mod_files

    # slot_data comes from the AP server after connecting
    slot_data = [
        {"location_id": 7472000, "location_name": "Survey 5 Systems",
         "item_name": "Mothwing Cloak", "player_name": "Alice",
         "game": "Hollow Knight", "classification": "progression"},
        ...
    ]
    generate_mod_files(slot_data, stellaris_mod_dir)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("StellarisClient")

# Research cost per location timing
COST_BY_TIMING = {
    "early": 500,
    "mid": 1500,
    "late": 3000,
    "endgame": 5000,
}

# Research area rotation (spreads AP techs across all 3 areas)
AREAS = ["physics", "society", "engineering"]
CATEGORIES = {
    "physics": "field_manipulation",
    "society": "statecraft",
    "engineering": "voidcraft",
}

# Classification → tier for research weight
CLASSIFICATION_TIER = {
    "progression": 1,
    "useful": 1,
    "filler": 2,
    "trap": 2,
}



# Vanilla tech metadata - used to give AP techs proper tier/area/prerequisites
# so they appear at the right time in the tech tree instead of all at once.
# AP techs that replace a vanilla tech inherit its position in the tree.
VANILLA_TECH_DATA = {
    "tech_planetary_unification": {"tier": 1, "area": "society", "prereqs": ["tech_planetary_government"]},
    "tech_eco_simulation": {"tier": 1, "area": "society", "prereqs": ["tech_industrial_farming"]},
    "tech_powered_exoskeletons": {"tier": 1, "area": "engineering", "prereqs": ["tech_basic_industry"]},
    "tech_alloys_1": {"tier": 1, "area": "engineering", "prereqs": ["tech_basic_industry"]},
    "tech_luxuries_1": {"tier": 1, "area": "engineering", "prereqs": ["tech_basic_industry"]},
    "tech_mineral_purification_1": {"tier": 1, "area": "engineering", "prereqs": ["tech_mining_1"]},
    "tech_alloys_2": {"tier": 3, "area": "engineering", "prereqs": ["tech_alloys_1"]},
    "tech_gene_crops": {"tier": 2, "area": "society", "prereqs": ["tech_eco_simulation"]},
    "tech_colonial_centralization": {"tier": 2, "area": "society", "prereqs": ["tech_planetary_unification"]},
    "tech_interstellar_economics": {"tier": 3, "area": "society", "prereqs": ["tech_space_trading"]},
    "tech_galactic_markets": {"tier": 4, "area": "society", "prereqs": ["tech_interstellar_economics"]},
    "tech_administrative_ai": {"tier": 1, "area": "physics", "prereqs": ["tech_basic_science_lab_1"]},
    "tech_global_research_initiative": {"tier": 3, "area": "physics", "prereqs": ["tech_basic_science_lab_2"]},
    "tech_robotic_workers": {"tier": 1, "area": "engineering", "prereqs": ["tech_powered_exoskeletons"]},
    "tech_droid_workers": {"tier": 2, "area": "engineering", "prereqs": ["tech_robotic_workers"]},
    "tech_synthetic_workers": {"tier": 4, "area": "engineering", "prereqs": ["tech_droid_workers"]},
    "tech_gene_tailoring": {"tier": 3, "area": "society", "prereqs": ["tech_genome_mapping"]},
    "tech_cloning": {"tier": 2, "area": "society", "prereqs": ["tech_genome_mapping"]},
    "tech_glandular_acclimation": {"tier": 3, "area": "society", "prereqs": ["tech_gene_tailoring"]},
    "tech_psionic_theory": {"tier": 3, "area": "society", "prereqs": []},
    "tech_telepathy": {"tier": 3, "area": "society", "prereqs": ["tech_psionic_theory"]},
    "tech_sensors_2": {"tier": 2, "area": "physics", "prereqs": ["tech_sensors_1"]},
    "tech_sensors_3": {"tier": 3, "area": "physics", "prereqs": ["tech_sensors_2"]},
    "tech_doctrine_fleet_size_1": {"tier": 1, "area": "society", "prereqs": []},
    "tech_doctrine_fleet_size_3": {"tier": 3, "area": "society", "prereqs": ["tech_doctrine_fleet_size_2"]},
    "tech_doctrine_fleet_size_5": {"tier": 5, "area": "society", "prereqs": ["tech_doctrine_fleet_size_4"]},
    "tech_doctrine_navy_size_1": {"tier": 1, "area": "society", "prereqs": []},
    "tech_doctrine_navy_size_3": {"tier": 3, "area": "society", "prereqs": ["tech_doctrine_navy_size_2"]},
    "tech_centralized_command": {"tier": 3, "area": "society", "prereqs": ["tech_interstellar_fleet_traditions"]},
    "tech_habitat_1": {"tier": 3, "area": "engineering", "prereqs": ["tech_starbase_3"]},
    "tech_habitat_2": {"tier": 4, "area": "engineering", "prereqs": ["tech_habitat_1"]},
    "tech_climate_restoration": {"tier": 4, "area": "society", "prereqs": ["tech_terrestrial_sculpting"]},
    "tech_mine_exotic_gases": {"tier": 2, "area": "engineering", "prereqs": []},
    "tech_mine_volatile_motes": {"tier": 2, "area": "physics", "prereqs": []},
    "tech_mine_rare_crystals": {"tier": 2, "area": "engineering", "prereqs": []},
    "tech_capital_productivity_1": {"tier": 2, "area": "society", "prereqs": ["tech_planetary_unification"]},
    "tech_capital_productivity_3": {"tier": 4, "area": "society", "prereqs": ["tech_capital_productivity_2"]},
    "tech_global_defense_grid": {"tier": 2, "area": "society", "prereqs": ["tech_ground_defense_planning"]},
    "tech_planetary_shield_generator": {"tier": 3, "area": "physics", "prereqs": ["tech_shields_3"]},
    "tech_galactic_administration": {"tier": 3, "area": "society", "prereqs": ["tech_colonial_centralization"]},
}

# Map location names to vanilla tech keys for tier/area inheritance.
#
# Only locations with location_type="tech" in the apworld actually hit this
# map (slot_generator filters to tech_slots before lookup). The entries
# below for "Research X" milestone locations are intentionally kept as
# documentation: if they're ever promoted to tech-type locations (so they
# replace the vanilla tech in the research pool), the bridge already knows
# which vanilla tech each one shadows and can block it via the
# ap_tech_blocked_<tech_key> flag.
LOCATION_TO_VANILLA_TECH = {
    "Research Planetary Unification": "tech_planetary_unification",
    "Research Eco Simulation": "tech_eco_simulation",
    "Research Powered Exoskeletons": "tech_powered_exoskeletons",
    "Research Alloy Foundries": "tech_alloys_1",
    "Research Luxury Goods": "tech_luxuries_1",
    "Research Mineral Purification": "tech_mineral_purification_1",
    "Research Advanced Alloys": "tech_alloys_2",
    "Research Gene Crops": "tech_gene_crops",
    "Research Colonial Centralization": "tech_colonial_centralization",
    "Research Interstellar Economics": "tech_interstellar_economics",
    "Research Galactic Markets": "tech_galactic_markets",
    "Research Administrative AI": "tech_administrative_ai",
    "Research Global Research Initiative": "tech_global_research_initiative",
    "Research Robotic Workers": "tech_robotic_workers",
    "Research Droids": "tech_droid_workers",
    "Research Synthetics": "tech_synthetic_workers",
    "Research Gene Tailoring": "tech_gene_tailoring",
    "Research Cloning": "tech_cloning",
    "Research Glandular Acclimation": "tech_glandular_acclimation",
    "Research Psionic Theory": "tech_psionic_theory",
    "Research Telepathy": "tech_telepathy",
    "Research Sensors II": "tech_sensors_2",
    "Research Sensors III": "tech_sensors_3",
    "Research Fleet Size I": "tech_doctrine_fleet_size_1",
    "Research Fleet Size III": "tech_doctrine_fleet_size_3",
    "Research Fleet Size V": "tech_doctrine_fleet_size_5",
    "Research Navy Size I": "tech_doctrine_navy_size_1",
    "Research Navy Size III": "tech_doctrine_navy_size_3",
    "Research Centralized Command": "tech_centralized_command",
    "Research Habitats I": "tech_habitat_1",
    "Research Habitats II": "tech_habitat_2",
    "Research Climate Restoration": "tech_climate_restoration",
    "Research Exotic Gas Extraction": "tech_mine_exotic_gases",
    "Research Volatile Motes Extraction": "tech_mine_volatile_motes",
    "Research Rare Crystal Mining": "tech_mine_rare_crystals",
    "Research Capital Productivity I": "tech_capital_productivity_1",
    "Research Capital Productivity III": "tech_capital_productivity_3",
    "Research Global Defense Grid": "tech_global_defense_grid",
    "Research Planetary Shield Generator": "tech_planetary_shield_generator",
    "Research Galactic Administration": "tech_galactic_administration",
}

# Timing → fallback tier for non-vanilla-tech locations
TIMING_TO_TIER = {"early": 1, "mid": 2, "late": 3, "endgame": 4}


def generate_mod_files(
    slot_data: List[Dict],
    mod_dir: Path,
    player_name: str = "Unknown",
) -> Optional[List[str]]:
    """Generate dynamic tech + localisation files from AP slot data.

    Args:
        slot_data: List of dicts with keys:
            location_id, location_name, item_name, player_name,
            game, classification, is_own_item (bool)
        mod_dir: Path to the Stellaris mod directory
            (e.g. Documents/Paradox Interactive/Stellaris/mod/archipelago_multiworld)
        player_name: This player's name in the AP session

    Returns:
        True if files were generated successfully.
    """
    if not slot_data:
        logger.warning("No slot data to generate files from")
        return False

    tech_lines = []
    loc_lines = []
    effect_lines = []
    event_lines = []

    tech_lines.append("# Auto-generated by Stellaris AP client - DO NOT EDIT")
    tech_lines.append("# These techs represent AP locations. Researching them sends checks.")
    tech_lines.append("# Milestone locations (survey, colonize, etc.) are detected automatically.")
    tech_lines.append("")

    effect_lines.append("# Auto-generated AP tech completion effects")
    effect_lines.append("")

    event_lines.append("# Auto-generated AP tech completion events")
    event_lines.append("namespace = ap_slot")
    event_lines.append("namespace = ap_slot_check")
    event_lines.append("")

    loc_lines.append("l_english:")

    # Filter to only "tech" type locations - milestones are handled
    # by ap_check_detection.txt and fire automatically during gameplay
    tech_slots = [s for s in slot_data
                  if s.get("location_type", "tech") == "tech"]
    milestone_slots = [s for s in slot_data
                       if s.get("location_type", "tech") == "milestone"]

    if milestone_slots:
        logger.info(
            f"Skipping {len(milestone_slots)} milestone locations "
            f"(detected automatically during gameplay)"
        )

    for i, slot in enumerate(tech_slots):
        loc_id = slot["location_id"]
        loc_name = slot["location_name"]
        item_name = slot["item_name"]
        recipient = slot.get("player_name", "Someone")
        game = slot.get("game", "Unknown Game")
        classification = slot.get("classification", "filler")
        is_own = slot.get("is_own_item", False)

        tech_key = f"ap_slot_{i}"

        # Look up vanilla tech data for this location
        vanilla_key = LOCATION_TO_VANILLA_TECH.get(loc_name)
        vanilla = VANILLA_TECH_DATA.get(vanilla_key, {}) if vanilla_key else {}

        if vanilla:
            # Inherit position from the vanilla tech this replaces
            area = vanilla["area"]
            tier = vanilla["tier"]
            prereqs = vanilla["prereqs"]
            # Cost scales with tier: ~500 per tier
            cost = max(500, tier * 600)
        else:
            # Non-vanilla locations: use timing-based tier
            timing = slot.get("timing", "mid")
            area = AREAS[i % 3]
            tier = TIMING_TO_TIER.get(timing, 2)
            prereqs = []
            cost = COST_BY_TIMING.get(timing, 1500)

        category = CATEGORIES[area]

        # Color coding by classification
        if classification == "progression":
            item_color = "§B"  # blue
            icon_suffix = "progression"
        elif classification == "useful":
            item_color = "§G"  # green
            icon_suffix = "useful"
        elif classification == "trap":
            item_color = "§R"  # red
            icon_suffix = "trap"
        else:
            item_color = "§H"  # white/default
            icon_suffix = "filler"

        # --- Technology definition ---
        tech_lines.append(f"{tech_key} = {{")
        tech_lines.append(f"\tcost = {cost}")
        tech_lines.append(f"\tarea = {area}")
        tech_lines.append(f"\ttier = {tier}")
        tech_lines.append(f"\tcategory = {{ {category} }}")
        tech_lines.append(f"\tweight = 50")
        # is_rare = yes → shiny border + stays in research hand permanently
        tech_lines.append(f"\tis_rare = yes")
        if prereqs:
            tech_lines.append(f"\tprerequisites = {{ {' '.join(prereqs)} }}")
        tech_lines.append(f"")
        tech_lines.append(f"\tpotential = {{")
        tech_lines.append(f"\t\thas_country_flag = ap_connected")
        tech_lines.append(f"\t\tNOT = {{ has_country_flag = ap_slot_{i}_sent }}")
        tech_lines.append(f"\t}}")
        tech_lines.append(f"")
        tech_lines.append(f"\tweight_modifier = {{")
        tech_lines.append(f"\t\tfactor = 1")
        tech_lines.append(f"\t}}")
        tech_lines.append(f"")
        tech_lines.append(f"\tai_weight = {{ factor = 0 }}")
        tech_lines.append(f"}}")
        tech_lines.append(f"")

        # --- Localisation ---
        if is_own:
            desc_text = (
                f"Completing this research sends a discovery back to "
                f"§Gourselves§! through the Archipelago Network.\\n\\n"
                f"Reward: {item_color}{item_name}§!"
            )
            tech_title = f"{item_color}{item_name}§! (Self)"
        else:
            desc_text = (
                f"Completing this research transmits a discovery to "
                f"§Y{recipient}§! playing §H{game}§!.\\n\\n"
                f"Sending: {item_color}{item_name}§!"
            )
            tech_title = f"{item_color}{item_name}§! for §Y{recipient}§!"

        loc_lines.append(f' {tech_key}:0 "{tech_title}"')
        loc_lines.append(f' {tech_key}_desc:0 "{desc_text}"')

        # --- Check event loc (shown when the tech is completed) ---
        if is_own:
            check_desc = (
                f"Our research into the Archipelago Network has yielded results. "
                f"A discovery has looped back to §Gour own civilization§!.\\n\\n"
                f"Received: {item_color}{item_name}§!"
            )
        else:
            check_desc = (
                f"Our research into the Archipelago Network is complete. "
                f"The results have been §Ytransmitted§! across the dimensional barrier.\\n\\n"
                f"Sent: {item_color}{item_name}§! to §Y{recipient}§! ({game})"
            )
        loc_lines.append(f' ap_slot_check.{i}.name:0 "Discovery Transmitted!"')
        loc_lines.append(f' ap_slot_check.{i}.desc:0 "{check_desc}"')
        loc_lines.append(f' ap_slot_check.{i}.a:0 "For the multiverse!"')

        # --- Per-slot check event ---
        event_lines.append(f"country_event = {{")
        event_lines.append(f"    id = ap_slot_check.{i}")
        event_lines.append(f"    is_triggered_only = yes")
        event_lines.append(f"    title = ap_slot_check.{i}.name")
        event_lines.append(f"    desc = ap_slot_check.{i}.desc")
        event_lines.append(f"    picture = GFX_evt_satellite_in_orbit")
        event_lines.append(f"    option = {{ name = ap_slot_check.{i}.a }}")
        event_lines.append(f"}}")
        event_lines.append(f"")

        # --- Scripted effect (called when tech is researched) ---
        # NOTE: Does NOT grant the vanilla tech - that tech was "sent to
        # another world" and must come from another player's progress.
        effect_lines.append(f"ap_on_research_{tech_key} = {{")
        effect_lines.append(f'\tset_country_flag = ap_slot_{i}_sent')
        effect_lines.append(f'\tlog = "AP_CHECK|{loc_id}|{loc_name}"')
        effect_lines.append(f"\tcountry_event = {{ id = ap_slot_check.{i} }}")
        effect_lines.append(f"}}")
        effect_lines.append(f"")

    # --- Monthly scanner: detect completed AP techs ---
    # Uses has_technology instead of last_increased_tech because dynamic
    # tech keys may not be recognized at event parse time.
    # Runs monthly - catches any tech completion reliably.
    event_lines.append("# Monthly: detect completed AP slot techs and send checks")
    event_lines.append("country_event = {")
    event_lines.append("    id = ap_slot.1")
    event_lines.append("    is_triggered_only = yes")
    event_lines.append("    hide_window = yes")
    event_lines.append("")
    event_lines.append("    trigger = {")
    event_lines.append("        is_ai = no")
    event_lines.append("        has_country_flag = ap_connected")
    event_lines.append("    }")
    event_lines.append("")
    event_lines.append("    immediate = {")
    for i, slot in enumerate(tech_slots):
        tech_key = f"ap_slot_{i}"
        event_lines.append(f"        if = {{")
        event_lines.append(f"            limit = {{")
        event_lines.append(f"                has_technology = {tech_key}")
        event_lines.append(f"                NOT = {{ has_country_flag = ap_slot_{i}_sent }}")
        event_lines.append(f"            }}")
        event_lines.append(f"            ap_on_research_{tech_key} = yes")
        event_lines.append(f"        }}")
    event_lines.append("    }")
    event_lines.append("}")
    event_lines.append("")

    # --- Write files ---
    try:
        tech_dir = mod_dir / "common" / "technology"
        tech_dir.mkdir(parents=True, exist_ok=True)
        (tech_dir / "ap_dynamic_techs.txt").write_text(
            "\n".join(tech_lines), encoding="utf-8"
        )

        loc_dir = mod_dir / "localisation" / "english"
        loc_dir.mkdir(parents=True, exist_ok=True)
        with open(loc_dir / "ap_dynamic_l_english.yml", "wb") as f:
            f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
            f.write("\n".join(loc_lines).encode("utf-8"))

        eff_dir = mod_dir / "common" / "scripted_effects"
        eff_dir.mkdir(parents=True, exist_ok=True)
        (eff_dir / "ap_dynamic_effects.txt").write_text(
            "\n".join(effect_lines), encoding="utf-8"
        )

        evt_dir = mod_dir / "events"
        evt_dir.mkdir(parents=True, exist_ok=True)
        (evt_dir / "ap_dynamic_events.txt").write_text(
            "\n".join(event_lines), encoding="utf-8"
        )

        # Copy tech icon DDS for each generated tech
        # Stellaris maps tech_key → gfx/interface/icons/technologies/<tech_key>.dds
        icon_dir = mod_dir / "gfx" / "interface" / "icons" / "technologies"
        icon_dir.mkdir(parents=True, exist_ok=True)
        source_icon = icon_dir / "ap_slot_tech.dds"
        if source_icon.exists():
            import shutil
            for i in range(len(tech_slots)):
                dest = icon_dir / f"ap_slot_{i}.dds"
                shutil.copy2(source_icon, dest)
            logger.info(f"Copied tech icon for {len(tech_slots)} slot techs")
        else:
            logger.warning(
                f"Source icon not found at {source_icon} - "
                f"techs will show missing icon"
            )

        # Hook AP slot tech detection into monthly pulse
        # (not on_tech_increased - dynamic tech keys may fail last_increased_tech)
        on_action_dir = mod_dir / "common" / "on_actions"
        on_action_dir.mkdir(parents=True, exist_ok=True)
        on_action_content = (
            "# Auto-generated - monthly scan for completed AP slot techs\n"
            "on_monthly_pulse_country = {\n"
            "    events = {\n"
            "        ap_slot.1\n"
            "    }\n"
            "}\n"
        )
        (on_action_dir / "ap_dynamic_on_actions.txt").write_text(
            on_action_content, encoding="utf-8"
        )

        logger.info(
            f"Generated {len(tech_slots)} AP slot techs in {mod_dir} "
            f"({len(milestone_slots)} milestones skipped)"
        )

        # Return vanilla techs to block (bridge sends flags via pipe)
        blocked_techs = []
        for slot in tech_slots:
            vk = LOCATION_TO_VANILLA_TECH.get(slot.get("location_name"))
            if vk:
                blocked_techs.append(vk)
        return blocked_techs

    except Exception as e:
        logger.error(f"Failed to generate mod files: {e}")
        return None


def clear_dynamic_files(mod_dir: Path):
    """Remove previously generated dynamic files."""
    for pattern in [
        "common/technology/ap_dynamic_techs.txt",
        "common/scripted_effects/ap_dynamic_effects.txt",
        "common/on_actions/ap_dynamic_on_actions.txt",
        "events/ap_dynamic_events.txt",
        "localisation/english/ap_dynamic_l_english.yml",
    ]:
        path = mod_dir / pattern
        if path.exists():
            path.unlink()
            logger.info(f"Removed {path}")

    # Remove generated icon copies (ap_slot_0.dds, ap_slot_1.dds, ...)
    icon_dir = mod_dir / "gfx" / "interface" / "icons" / "technologies"
    if icon_dir.exists():
        for f in icon_dir.glob("ap_slot_*.dds"):
            if f.name != "ap_slot_tech.dds":  # keep the source icon
                f.unlink()
                logger.info(f"Removed {f}")


# =========================================================================
# Example / test
# =========================================================================

if __name__ == "__main__":
    import json
    import sys

    # Example slot data for testing
    example_slots = [
        {
            "location_id": 7472000, "location_name": "Survey 5 Systems",
            "item_name": "Mothwing Cloak", "player_name": "Alice",
            "game": "Hollow Knight", "classification": "progression",
            "is_own_item": False, "location_type": "milestone",
        },
        {
            "location_id": 7472001, "location_name": "Survey 10 Systems",
            "item_name": "Progressive Ship Class", "player_name": "You",
            "game": "Stellaris", "classification": "progression",
            "is_own_item": True, "location_type": "milestone",
        },
        {
            "location_id": 7472100, "location_name": "Research 5 Technologies",
            "item_name": "500 Geo", "player_name": "Alice",
            "game": "Hollow Knight", "classification": "filler",
            "is_own_item": False, "location_type": "milestone",
        },
        {
            "location_id": 7472300, "location_name": "Win First War",
            "item_name": "Pirate Surge", "player_name": "You",
            "game": "Stellaris", "classification": "trap",
            "is_own_item": True, "location_type": "milestone",
        },
    ]

    logging.basicConfig(level=logging.INFO)
    mod_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./test_output")
    generate_mod_files(example_slots, mod_dir)
    print(f"Generated test files in {mod_dir}")
    print(f"Check:")
    print(f"  {mod_dir}/common/technology/ap_dynamic_techs.txt")
    print(f"  {mod_dir}/localisation/english/ap_dynamic_l_english.yml")
