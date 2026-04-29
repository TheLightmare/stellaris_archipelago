"""Tests for item and location data integrity."""

import unittest

from ..items import (
    ALL_ITEMS,
    FILLER_ITEMS,
    PROGRESSIVE_ITEMS,
    TRAP_ITEMS,
    UNIQUE_ITEMS,
    get_filler_item_names,
    get_items_for_options,
)
from ..locations import (
    ALL_LOCATIONS,
    CRISIS_LOCATIONS,
    DIPLOMACY_LOCATIONS,
    EXPANSION_LOCATIONS,
    EXPLORATION_LOCATIONS,
    TECH_LOCATIONS,
    TRADITION_LOCATIONS,
    VICTORY_LOCATIONS,
    WARFARE_LOCATIONS,
    get_locations_for_options,
)


class TestItemData(unittest.TestCase):
    """Test item data integrity."""

    def test_no_duplicate_ids(self) -> None:
        """All item IDs are unique."""
        ids = [data.code for data in ALL_ITEMS.values()]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate item IDs found")

    def test_no_empty_names(self) -> None:
        """All item names are non-empty strings."""
        for name in ALL_ITEMS:
            self.assertIsInstance(name, str)
            self.assertGreater(len(name.strip()), 0)

    def test_all_items_combines_all_dicts(self) -> None:
        """ALL_ITEMS is the union of all sub-dictionaries."""
        expected = {
            **PROGRESSIVE_ITEMS,
            **UNIQUE_ITEMS,
            **FILLER_ITEMS,
            **TRAP_ITEMS,
        }
        self.assertEqual(set(ALL_ITEMS.keys()), set(expected.keys()))

    def test_filler_names_returns_only_filler(self) -> None:
        """get_filler_item_names only returns filler items."""
        filler_names = get_filler_item_names()
        for name in filler_names:
            self.assertIn(name, FILLER_ITEMS)

    def test_filter_removes_dlc_items(self) -> None:
        """Filtering with no DLCs removes DLC-gated items."""
        base_items = get_items_for_options(
            dlc_utopia=False,
            dlc_federations=False,
            dlc_nemesis=False,
            dlc_leviathans=False,
            dlc_apocalypse=False,
            dlc_megacorp=False,
            dlc_overlord=False,
        )
        for name, data in base_items.items():
            self.assertIsNone(
                data.dlc,
                f"Item '{name}' has dlc={data.dlc} but should be base-game only",
            )

    def test_filter_includes_dlc_items(self) -> None:
        """Filtering with Utopia enabled includes Utopia items."""
        utopia_items = get_items_for_options(dlc_utopia=True)
        utopia_names = {
            name for name, data in ALL_ITEMS.items()
            if data.dlc == "utopia"
        }
        for name in utopia_names:
            self.assertIn(name, utopia_items, f"Utopia item '{name}' missing")

    def test_filter_removes_traps_when_disabled(self) -> None:
        """Trap items are excluded when traps_enabled is False."""
        items = get_items_for_options(traps_enabled=False)
        for name in TRAP_ITEMS:
            self.assertNotIn(name, items)

    def test_filter_includes_traps_when_enabled(self) -> None:
        """Trap items are included when traps_enabled is True."""
        items = get_items_for_options(traps_enabled=True)
        for name in TRAP_ITEMS:
            # Only base-game traps (no DLC filter on traps)
            if TRAP_ITEMS[name].dlc is None:
                self.assertIn(name, items)


class TestLocationData(unittest.TestCase):
    """Test location data integrity."""

    def test_no_duplicate_ids(self) -> None:
        """All location IDs are unique."""
        ids = [data.code for data in ALL_LOCATIONS.values()]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate location IDs found")

    def test_no_empty_names(self) -> None:
        """All location names are non-empty strings."""
        for name in ALL_LOCATIONS:
            self.assertIsInstance(name, str)
            self.assertGreater(len(name.strip()), 0)

    def test_no_id_collisions_with_items(self) -> None:
        """No location ID collides with an item ID."""
        item_ids = {data.code for data in ALL_ITEMS.values()}
        location_ids = {data.code for data in ALL_LOCATIONS.values()}
        collisions = item_ids & location_ids
        self.assertEqual(
            len(collisions), 0,
            f"ID collisions between items and locations: {collisions}",
        )

    def test_victory_location_exists(self) -> None:
        """The Victory location exists."""
        self.assertIn("Victory", ALL_LOCATIONS)

    def test_filter_removes_dlc_locations(self) -> None:
        """Filtering with no DLCs removes DLC-gated locations."""
        base_locs = get_locations_for_options(
            dlc_utopia=False,
            dlc_federations=False,
            dlc_nemesis=False,
            dlc_leviathans=False,
            dlc_apocalypse=False,
            dlc_megacorp=False,
            dlc_overlord=False,
        )
        for name, data in base_locs.items():
            self.assertIsNone(
                data.dlc,
                f"Location '{name}' has dlc={data.dlc} but should be base-game only",
            )

    def test_filter_removes_diplomacy_when_disabled(self) -> None:
        """Diplomacy locations excluded when disabled."""
        locs = get_locations_for_options(include_diplomacy=False)
        for name, data in ALL_LOCATIONS.items():
            if data.category == "diplomacy":
                self.assertNotIn(name, locs)

    def test_filter_removes_warfare_when_disabled(self) -> None:
        """Warfare locations excluded when disabled."""
        locs = get_locations_for_options(include_warfare=False)
        for name, data in ALL_LOCATIONS.items():
            if data.category == "warfare":
                self.assertNotIn(name, locs)

    def test_filter_removes_crisis_when_disabled(self) -> None:
        """Crisis locations excluded when disabled."""
        locs = get_locations_for_options(include_crisis=False)
        for name, data in ALL_LOCATIONS.items():
            if data.category == "crisis":
                self.assertNotIn(name, locs)
