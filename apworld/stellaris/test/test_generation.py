"""Tests for basic Stellaris world generation."""

from . import StellarisTestBase


class TestDefaultGeneration(StellarisTestBase):
    """Test that a world generates successfully with default options."""

    def test_regions_created(self) -> None:
        """All expected regions exist."""
        region_names = {r.name for r in self.multiworld.regions if r.player == self.player}
        self.assertIn("Menu", region_names)
        self.assertIn("Early Game", region_names)
        self.assertIn("Mid Game", region_names)
        self.assertIn("Late Game", region_names)
        self.assertIn("Endgame", region_names)

    def test_regions_connected(self) -> None:
        """Regions are connected in the expected linear chain."""
        menu = self.get_region("Menu")
        exit_names = [e.name for e in menu.exits]
        self.assertTrue(len(exit_names) > 0, "Menu must have at least one exit")

        early = self.get_region("Early Game")
        early_exit_names = [e.name for e in early.exits]
        self.assertIn("Early to Mid", early_exit_names)

        mid = self.get_region("Mid Game")
        mid_exit_names = [e.name for e in mid.exits]
        self.assertIn("Mid to Late", mid_exit_names)

        late = self.get_region("Late Game")
        late_exit_names = [e.name for e in late.exits]
        self.assertIn("Late to Endgame", late_exit_names)

    def test_locations_exist(self) -> None:
        """At least one location exists in the world."""
        location_count = sum(
            1 for region in self.multiworld.regions
            if region.player == self.player
            for _ in region.locations
        )
        self.assertGreater(location_count, 0)

    def test_items_equal_locations(self) -> None:
        """Item pool count matches location count."""
        location_count = sum(
            1 for region in self.multiworld.regions
            if region.player == self.player
            for _ in region.locations
        )
        item_count = sum(
            1 for item in self.multiworld.itempool
            if item.player == self.player
        )
        self.assertEqual(item_count, location_count)

    def test_completion_condition_set(self) -> None:
        """A completion condition is defined for the player."""
        self.assertIn(self.player, self.multiworld.completion_condition)
        self.assertIsNotNone(self.multiworld.completion_condition[self.player])

    def test_create_item(self) -> None:
        """create_item works for known item names."""
        world = self.multiworld.worlds[self.player]
        item = world.create_item("Progressive Ship Class")
        self.assertEqual(item.name, "Progressive Ship Class")
        self.assertEqual(item.player, self.player)

    def test_create_item_unknown_raises(self) -> None:
        """create_item raises for unknown item names."""
        world = self.multiworld.worlds[self.player]
        with self.assertRaises(Exception):
            world.create_item("Nonexistent Item That Does Not Exist")

    def test_get_filler_item_name(self) -> None:
        """get_filler_item_name returns a valid filler item."""
        world = self.multiworld.worlds[self.player]
        filler_name = world.get_filler_item_name()
        from ..items import FILLER_ITEMS
        self.assertIn(filler_name, FILLER_ITEMS)

    def test_slot_data(self) -> None:
        """fill_slot_data returns expected keys."""
        world = self.multiworld.worlds[self.player]
        slot_data = world.fill_slot_data()
        self.assertIn("goal", slot_data)
        self.assertIn("energy_link_enabled", slot_data)
        self.assertIn("energy_link_rate", slot_data)
        self.assertIn("galaxy_size", slot_data)
