"""Tests for Stellaris option variations and DLC filtering."""

from . import StellarisTestBase


class TestNoDlcGeneration(StellarisTestBase):
    """Test generation with all DLCs disabled."""
    options = {
        "dlc_utopia": 0,
        "dlc_federations": 0,
        "dlc_nemesis": 0,
        "dlc_leviathans": 0,
        "dlc_apocalypse": 0,
        "dlc_megacorp": 0,
        "dlc_overlord": 0,
    }

    def test_generates_successfully(self) -> None:
        """World generates without errors when all DLCs are off."""
        self.assertTrue(len(self.multiworld.itempool) > 0)

    def test_no_utopia_locations(self) -> None:
        """Utopia-exclusive locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Build a Megastructure", location_names)
        self.assertNotIn("Complete a Megastructure", location_names)
        self.assertNotIn("Complete Biological Ascension", location_names)
        self.assertNotIn("Complete Synthetic Ascension", location_names)
        self.assertNotIn("Complete Psionic Ascension", location_names)

    def test_no_federations_locations(self) -> None:
        """Federations-exclusive locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Form or Join a Federation", location_names)
        self.assertNotIn("Federation Level 3", location_names)
        self.assertNotIn("Become Custodian", location_names)
        self.assertNotIn("Form the Galactic Imperium", location_names)

    def test_no_leviathans_locations(self) -> None:
        """Leviathans-exclusive locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Defeat a Leviathan", location_names)

    def test_items_equal_locations(self) -> None:
        """Item pool still balances with location count."""
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


class TestUtopiaGeneration(StellarisTestBase):
    """Test generation with Utopia enabled."""
    options = {
        "dlc_utopia": 1,
    }

    def test_utopia_locations_present(self) -> None:
        """Utopia locations are included when enabled."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertIn("Build a Megastructure", location_names)
        self.assertIn("Complete Biological Ascension", location_names)

    def test_utopia_items_present(self) -> None:
        """Utopia items are in the pool when enabled."""
        item_names = {
            item.name
            for item in self.multiworld.itempool
            if item.player == self.player
        }
        self.assertIn("Mega-Engineering License", item_names)
        self.assertIn("Ascension Path: Biological", item_names)


class TestNoDiplomacy(StellarisTestBase):
    """Test generation with diplomacy checks disabled."""
    options = {
        "include_diplomacy": 0,
    }

    def test_no_diplomacy_locations(self) -> None:
        """Diplomacy locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Sign a Non-Aggression Pact", location_names)
        self.assertNotIn("Sign a Defensive Pact", location_names)
        self.assertNotIn("Integrate a Subject", location_names)

    def test_items_still_balance(self) -> None:
        """Item count matches location count with diplomacy off."""
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


class TestNoWarfare(StellarisTestBase):
    """Test generation with warfare checks disabled."""
    options = {
        "include_warfare": 0,
    }

    def test_no_warfare_locations(self) -> None:
        """Warfare locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Win First War", location_names)
        self.assertNotIn("Achieve 50k Fleet Power", location_names)
        self.assertNotIn("Destroy a Fallen Empire", location_names)


class TestNoCrisis(StellarisTestBase):
    """Test generation with crisis checks disabled."""
    options = {
        "include_crisis": 0,
    }

    def test_no_crisis_locations(self) -> None:
        """Crisis locations are excluded."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertNotIn("Survive the Crisis 10 Years", location_names)
        self.assertNotIn("Defeat the Endgame Crisis", location_names)


class TestTrapsEnabled(StellarisTestBase):
    """Test generation with traps enabled."""
    options = {
        "traps_enabled": 1,
        "trap_percentage": 20,
    }

    def test_traps_in_pool(self) -> None:
        """Trap items appear in the pool when enabled."""
        from BaseClasses import ItemClassification
        trap_count = sum(
            1 for item in self.multiworld.itempool
            if item.player == self.player
            and item.classification == ItemClassification.trap
        )
        self.assertGreater(trap_count, 0)


class TestTrapsDisabled(StellarisTestBase):
    """Test generation with traps disabled (default)."""
    options = {
        "traps_enabled": 0,
    }

    def test_no_traps_in_pool(self) -> None:
        """No trap items in the pool when disabled."""
        from BaseClasses import ItemClassification
        trap_count = sum(
            1 for item in self.multiworld.itempool
            if item.player == self.player
            and item.classification == ItemClassification.trap
        )
        self.assertEqual(trap_count, 0)


class TestGoalCrisisAverted(StellarisTestBase):
    """Test the Crisis Averted goal."""
    options = {
        "goal": 1,
    }

    def test_completion_condition_set(self) -> None:
        """Completion condition exists for crisis goal."""
        self.assertIn(self.player, self.multiworld.completion_condition)

    def test_generates_successfully(self) -> None:
        """World generates without errors."""
        self.assertTrue(len(self.multiworld.itempool) > 0)


class TestGoalAscension(StellarisTestBase):
    """Test the Ascension goal (requires Utopia)."""
    options = {
        "goal": 2,
        "dlc_utopia": 1,
    }

    def test_completion_condition_set(self) -> None:
        """Completion condition exists for ascension goal."""
        self.assertIn(self.player, self.multiworld.completion_condition)

    def test_ascension_locations_present(self) -> None:
        """Ascension locations exist for this goal."""
        location_names = {
            loc.name
            for region in self.multiworld.regions
            if region.player == self.player
            for loc in region.locations
        }
        self.assertIn("Complete Biological Ascension", location_names)


class TestGoalAllChecks(StellarisTestBase):
    """Test the All Checks goal."""
    options = {
        "goal": 4,
    }

    def test_completion_condition_set(self) -> None:
        """Completion condition exists for all-checks goal."""
        self.assertIn(self.player, self.multiworld.completion_condition)
