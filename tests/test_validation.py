import unittest

from subscripts.itemValidation import validate_item, is_valid_item


class ItemValidationTests(unittest.TestCase):
    def item(self, **changes):
        return dict(dict(prefab="Wood", grid_x=0, grid_y=0), **changes)

    def test_minimal_valid_item(self):
        self.assertEqual(validate_item(self.item()), [])
        self.assertTrue(is_valid_item(self.item()))

    def test_non_dictionary(self):
        for value in (None, [], "Wood", 1):
            with self.subTest(value=value):
                self.assertEqual(validate_item(value), ["Item data must be a dictionary."])

    def test_prefab_required(self):
        for value in (None, "", "  ", 3):
            with self.subTest(value=value):
                self.assertFalse(is_valid_item(self.item(prefab=value)))

    def test_numeric_limits(self):
        for field, low, high in (("stack", 1, 9999), ("quality", 1, 99),
                                 ("variant", 0, 99), ("durability", 0, 99999),
                                 ("grid_x", 0, 7), ("grid_y", 0, 3)):
            for value in (low, high):
                with self.subTest(field=field, valid=value):
                    self.assertTrue(is_valid_item(self.item(**{field: value})))
            for value in (low - 1, high + 1, True, "1", None):
                with self.subTest(field=field, invalid=value):
                    self.assertFalse(is_valid_item(self.item(**{field: value})))

    def test_boolean_flags_are_strict(self):
        for field in ("equipped", "picked_up", "cheated"):
            for value in (True, False):
                with self.subTest(field=field, value=value):
                    self.assertTrue(is_valid_item(self.item(**{field: value})))
            for value in (0, 1, "false", None):
                with self.subTest(field=field, value=value):
                    self.assertIn(f"{field} must be a boolean.", validate_item(self.item(**{field: value})))

    def test_inventory_expansions(self):
        for rows in (4, 5, 6):
            player = {"uniques": [f"invrows {rows}"]}
            self.assertTrue(is_valid_item(self.item(grid_y=rows - 1), player))
            self.assertFalse(is_valid_item(self.item(grid_y=rows), player))

    def test_crafter_and_custom_data_types(self):
        for field, value in (("crafter_id", True), ("crafter_id", "123"),
                             ("crafter_name", 123), ("custom_data", [])):
            with self.subTest(field=field):
                self.assertFalse(is_valid_item(self.item(**{field: value})))

    def test_collects_multiple_errors(self):
        self.assertGreaterEqual(len(validate_item(self.item(prefab="", stack=0, cheated=1))), 3)

    def test_nonfinite_durability(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                self.assertFalse(is_valid_item(self.item(durability=value)))
