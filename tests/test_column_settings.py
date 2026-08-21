from __future__ import annotations

import json
import unittest

from wb_app.column_settings import (
    ColumnPreference,
    default_column_preferences,
    normalize_column_preferences,
    serialize_column_preferences,
    visible_column_ids,
)
from wb_app.ui import OVERVIEW_COLUMN_SPECS, SCENARIO_COLUMN_SPECS


class ColumnSettingsTests(unittest.TestCase):
    def test_invalid_setting_restores_all_default_columns(self) -> None:
        preferences = normalize_column_preferences("not-json")

        self.assertEqual(preferences, default_column_preferences())
        self.assertEqual(
            visible_column_ids(preferences),
            visible_column_ids(default_column_preferences()),
        )

    def test_saved_order_visibility_and_new_columns_are_preserved(self) -> None:
        raw = json.dumps(
            {
                "version": 1,
                "columns": [
                    {"id": "revenue", "visible": True},
                    {"id": "article", "visible": False},
                    {"id": "unknown", "visible": True},
                    {"id": "revenue", "visible": False},
                ],
            }
        )

        preferences = normalize_column_preferences(raw)

        self.assertEqual(preferences[0], ColumnPreference("revenue", True))
        self.assertEqual(preferences[1], ColumnPreference("article", False))
        self.assertEqual(preferences[-1].column_id, "net_margin")
        self.assertNotIn("unknown", [item.column_id for item in preferences])
        self.assertEqual(len(preferences), len(OVERVIEW_COLUMN_SPECS))

    def test_serialization_round_trip_keeps_user_choice(self) -> None:
        preferences = default_column_preferences()
        moved = preferences.pop(-1)
        preferences.insert(0, moved)
        preferences[1] = ColumnPreference(preferences[1].column_id, False)

        restored = normalize_column_preferences(serialize_column_preferences(preferences))

        self.assertEqual(restored, preferences)

    def test_all_hidden_setting_falls_back_to_safe_default(self) -> None:
        raw = [
            {"id": column_id, "visible": False}
            for column_id, _heading, _width in OVERVIEW_COLUMN_SPECS
        ]

        self.assertEqual(normalize_column_preferences(raw), default_column_preferences())

    def test_scenario_preferences_are_independent(self) -> None:
        preferences = default_column_preferences(SCENARIO_COLUMN_SPECS)
        moved = preferences.pop(-1)
        preferences.insert(0, moved)
        preferences[1] = ColumnPreference(preferences[1].column_id, False)

        restored = normalize_column_preferences(
            serialize_column_preferences(preferences, SCENARIO_COLUMN_SPECS),
            SCENARIO_COLUMN_SPECS,
        )

        self.assertEqual(restored, preferences)
        self.assertEqual(restored[0].column_id, "net_total")


if __name__ == "__main__":
    unittest.main()
