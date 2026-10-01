"""Tests for randomized-tech logic (prerequisite chains, item classes)."""

from BaseClasses import ItemClassification

from . import StellarisTestBase
from ..data.tech_catalog import TECH_CATALOG, all_keys
from ..rules import gating_tech_keys, tech_prerequisite_items


# tech_droid_workers (tier 2) requires tech_robotic_workers (tier 1).
# tech_synthetic_workers (tier 4) requires tech_droid_workers.
CHAIN = ["tech_robotic_workers", "tech_droid_workers", "tech_synthetic_workers"]

MID_GAME_ITEMS = [
    "Progressive Ship Class", "Progressive Starbase", "Progressive Weapons",
]


class TestPrerequisiteHelpers(StellarisTestBase):
    """Pure-function checks on the rule helpers."""
    options = {"randomized_techs": CHAIN}

    def test_gating_keys(self) -> None:
        self.assertEqual(
            gating_tech_keys(CHAIN),
            ["tech_droid_workers", "tech_robotic_workers"],
        )

    def test_prerequisite_items(self) -> None:
        rules = tech_prerequisite_items(CHAIN)
        self.assertEqual(rules["Research Droids"], ["Tech: Robotic Workers"])
        self.assertEqual(rules["Research Synthetics"], ["Tech: Droids"])
        # The root of the chain has no randomized prerequisite.
        self.assertNotIn("Research Robotic Workers", rules)

    def test_unselected_prereq_is_ignored(self) -> None:
        # Only droids selected: its prerequisite stays vanilla, so no rule.
        self.assertEqual(tech_prerequisite_items(["tech_droid_workers"]), {})
        self.assertEqual(gating_tech_keys(["tech_droid_workers"]), [])


class TestPrerequisiteChain(StellarisTestBase):
    """A randomized tech whose prerequisite is also randomized needs that
    prerequisite's Tech: item before its location is in logic."""
    options = {"randomized_techs": CHAIN}

    def _pool_item(self, name):
        return next(i for i in self.multiworld.itempool
                    if i.player == self.player and i.name == name)

    def test_gating_items_are_progression(self) -> None:
        self.assertEqual(
            self._pool_item("Tech: Robotic Workers").classification,
            ItemClassification.progression,
        )
        self.assertEqual(
            self._pool_item("Tech: Droids").classification,
            ItemClassification.progression,
        )
        # The end of the chain gates nothing, so it stays useful.
        self.assertEqual(
            self._pool_item("Tech: Synthetics").classification,
            ItemClassification.useful,
        )

    def test_create_item_honours_classification(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.create_item("Tech: Robotic Workers").classification,
            ItemClassification.progression,
        )

    def test_droids_needs_robotic_workers_item(self) -> None:
        # Droids is a tier-2 tech -> Mid Game region.
        self.collect_by_name(MID_GAME_ITEMS)
        self.assertTrue(self.can_reach_location("Research Robotic Workers"))
        self.assertFalse(self.can_reach_location("Research Droids"))
        self.collect_by_name(["Tech: Robotic Workers"])
        self.assertTrue(self.can_reach_location("Research Droids"))

    def test_chain_is_transitive(self) -> None:
        items = self.get_items_by_name("Progressive Ship Class")[:3]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:3]
        items += self.get_items_by_name("Progressive Defenses")[:2]
        self.collect(items)
        # Synthetics (tier 4 -> Late Game) needs Tech: Droids directly;
        # Droids itself is reachable only with Tech: Robotic Workers.
        self.assertFalse(self.can_reach_location("Research Synthetics"))
        self.collect_by_name(["Tech: Droids"])
        self.assertTrue(self.can_reach_location("Research Synthetics"))

    def test_slot_data_lists_selection(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.fill_slot_data()["randomized_techs"], sorted(CHAIN),
        )


class TestMegaEngineeringKeepsLicenseRule(StellarisTestBase):
    """The prerequisite rule must AND with an existing location rule."""
    options = {
        "dlc_utopia": 1,
        "randomized_techs": ["tech_mega_engineering", "tech_zero_point_power"],
    }

    def test_both_rules_apply(self) -> None:
        items = self.get_items_by_name("Progressive Ship Class")[:4]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:4]
        items += self.get_items_by_name("Progressive Defenses")[:3]
        self.collect(items)
        self.assertFalse(self.can_reach_location("Research Mega-Engineering"))
        self.collect_by_name(["Tech: Zero Point Power"])
        self.assertFalse(self.can_reach_location("Research Mega-Engineering"))
        self.collect_by_name(["Mega-Engineering License"])
        self.assertTrue(self.can_reach_location("Research Mega-Engineering"))


class TestEveryTechRandomized(StellarisTestBase):
    """Worst case: every catalog tech on with every DLC. Exercises the
    inherited WorldTestBase fill/reachability tests on the full graph."""
    options = {
        "dlc_utopia": 1, "dlc_federations": 1, "dlc_nemesis": 1,
        "dlc_leviathans": 1, "dlc_apocalypse": 1, "dlc_megacorp": 1,
        "dlc_overlord": 1, "dlc_first_contact": 1, "dlc_ancient_relics": 1,
        "dlc_machine_age": 1, "dlc_distant_stars": 1, "dlc_astral_planes": 1,
        "randomized_techs": all_keys(),
    }

    def test_every_catalog_location_present(self) -> None:
        names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        for t in TECH_CATALOG:
            self.assertIn(f"Research {t.display}", names)

    def test_items_equal_locations(self) -> None:
        location_count = sum(
            1 for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
            if loc.address is not None
        )
        item_count = sum(
            1 for item in self.multiworld.itempool
            if item.player == self.player
        )
        self.assertEqual(item_count, location_count)


class TestDlcTechDropped(StellarisTestBase):
    """A tech from a disabled DLC is dropped everywhere: no location,
    no item, not in slot_data (so the client never blocks it)."""
    options = {
        "dlc_first_contact": 0,
        "randomized_techs": ["tech_cloaking_1", "tech_robotic_workers"],
    }

    def test_dropped_consistently(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.fill_slot_data()["randomized_techs"], ["tech_robotic_workers"],
        )
        names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Research Cloaking I", names)
        self.assertIn("Research Robotic Workers", names)
        pool = {i.name for i in self.multiworld.itempool if i.player == self.player}
        self.assertNotIn("Tech: Cloaking I", pool)
        self.assertIn("Tech: Robotic Workers", pool)
