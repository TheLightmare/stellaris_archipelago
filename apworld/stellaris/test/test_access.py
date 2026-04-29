"""Tests for Stellaris access rules."""

from . import StellarisTestBase


class TestRegionAccess(StellarisTestBase):
    """Test that region transitions require the correct items."""

    def test_early_game_accessible(self) -> None:
        """Early Game is reachable from Menu with no items."""
        self.assertTrue(self.can_reach_region("Early Game"))

    def test_mid_game_requires_items(self) -> None:
        """Mid Game is not reachable without progression items."""
        self.assertFalse(self.can_reach_region("Mid Game"))

    def test_mid_game_accessible_with_items(self) -> None:
        """Mid Game is reachable with the required progressive items."""
        self.collect_by_name(["Progressive Ship Class", "Progressive Starbase", "Progressive Weapons"])
        self.assertTrue(self.can_reach_region("Mid Game"))

    def test_late_game_requires_items(self) -> None:
        """Late Game requires higher-tier progressive items."""
        # Only give enough for mid game
        self.collect_by_name(["Progressive Ship Class", "Progressive Starbase", "Progressive Weapons"])
        self.assertFalse(self.can_reach_region("Late Game"))

    def test_late_game_accessible_with_items(self) -> None:
        """Late Game is reachable with sufficient progressive items."""
        items = self.get_items_by_name("Progressive Ship Class")[:3]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:3]
        items += self.get_items_by_name("Progressive Defenses")[:2]
        self.collect(items)
        self.assertTrue(self.can_reach_region("Late Game"))

    def test_endgame_requires_items(self) -> None:
        """Endgame requires top-tier progression items."""
        # Give enough for late game but not endgame
        items = self.get_items_by_name("Progressive Ship Class")[:3]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:3]
        items += self.get_items_by_name("Progressive Defenses")[:2]
        self.collect(items)
        self.assertFalse(self.can_reach_region("Endgame"))

    def test_endgame_accessible_with_items(self) -> None:
        """Endgame is reachable with top-tier progressive items."""
        items = self.get_items_by_name("Progressive Ship Class")[:4]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:4]
        items += self.get_items_by_name("Progressive Defenses")[:3]
        self.collect(items)
        self.assertTrue(self.can_reach_region("Endgame"))


class TestLocationAccess(StellarisTestBase):
    """Test that specific locations have correct access rules."""

    def test_early_locations_accessible(self) -> None:
        """Early game locations are accessible without items."""
        self.assertTrue(self.can_reach_location("Survey 5 Systems"))

    def test_l_cluster_requires_insights(self) -> None:
        """L-Cluster requires 7 L-Gate Insights."""
        # Give enough items to reach Late Game (where the L-Cluster location is)
        items = self.get_items_by_name("Progressive Ship Class")[:3]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:3]
        items += self.get_items_by_name("Progressive Defenses")[:2]
        self.collect(items)
        # Should not be reachable without L-Gate Insights
        self.assertFalse(self.can_reach_location("Explore the L-Cluster"))

    def test_l_cluster_accessible_with_insights(self) -> None:
        """L-Cluster is reachable with 7 L-Gate Insights and region access."""
        items = self.get_items_by_name("Progressive Ship Class")[:3]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:3]
        items += self.get_items_by_name("Progressive Defenses")[:2]
        items += self.get_items_by_name("L-Gate Insight")[:7]
        self.collect(items)
        self.assertTrue(self.can_reach_location("Explore the L-Cluster"))

    def test_fleet_power_100k_requires_progression(self) -> None:
        """100k fleet power requires Ship Class 2 and Weapons 2."""
        # Give enough to reach mid game
        items = self.get_items_by_name("Progressive Ship Class")[:1]
        items += self.get_items_by_name("Progressive Starbase")[:1]
        items += self.get_items_by_name("Progressive Weapons")[:1]
        self.collect(items)
        self.assertFalse(self.can_reach_location("Achieve 100k Fleet Power"))

    def test_fleet_power_100k_accessible(self) -> None:
        """100k fleet power is reachable with required items."""
        items = self.get_items_by_name("Progressive Ship Class")[:2]
        items += self.get_items_by_name("Progressive Starbase")[:1]
        items += self.get_items_by_name("Progressive Weapons")[:2]
        self.collect(items)
        self.assertTrue(self.can_reach_location("Achieve 100k Fleet Power"))


class TestCrisisAccess(StellarisTestBase):
    """Test crisis location access rules."""

    def test_defeat_crisis_requires_top_tier(self) -> None:
        """Defeating the crisis requires top-tier military items."""
        # Give enough for endgame region access but not crisis-specific requirements
        items = self.get_items_by_name("Progressive Ship Class")[:4]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:4]
        items += self.get_items_by_name("Progressive Defenses")[:3]
        self.collect(items)
        # Need Weapons 5 for crisis, only have 4
        self.assertFalse(self.can_reach_location("Defeat the Endgame Crisis"))

    def test_defeat_crisis_accessible(self) -> None:
        """Defeating the crisis is reachable with full military items."""
        items = self.get_items_by_name("Progressive Ship Class")[:4]
        items += self.get_items_by_name("Progressive Starbase")[:3]
        items += self.get_items_by_name("Progressive Weapons")[:5]
        items += self.get_items_by_name("Progressive Defenses")[:3]
        self.collect(items)
        self.assertTrue(self.can_reach_location("Defeat the Endgame Crisis"))
