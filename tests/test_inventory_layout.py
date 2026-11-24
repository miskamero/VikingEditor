from copy import deepcopy
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from subscripts.inventoryLayout import effective_inventory_rows
from subscripts.itemValidation import validate_item
from tests.support import item
from tests.test_editor import QtTestCase
from tests.test_equipment_slots import equipment_fixture
from tests.test_lossless_editing import SWORD_IRON, character_wire, nested_wire
from tests.test_player_versions import string, strings
from ui.inventoryTab import InventoryTab
from ui.itemEditDialog import ItemEditDialog
from ui.mainWindow import MainWindow


class InventoryLayoutTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.tab = self.widget(InventoryTab)

    def test_saved_rows_follow_game_lookup_and_int32_parsing(self):
        cases = (
            ([], 4, True), (["invrows 4"], 4, True), (["invrows 5"], 5, True), (["invrows 6"], 6, True),
            (["invrows 0"], 0, False), (["invrows 3"], 3, False),
            (["invrows 7"], 7, False), (["invrows 9"], 9, False), (["InvRows 5"], 5, True),
            (["invrows -2147483648"], 0, False), (["invrows -1"], 0, False),
            (["invrows 2147483647"], 9, False), (["invrows 2147483648"], 4, False),
            (["invrows -2147483649"], 4, False), (["invrows 0x5"], 4, False), (["invrows 5_0"], 4, False),
            (["invrows ５"], 4, False), (["invrows +05\t"], 5, False), (["invrows 5\0"], 5, False),
            (["invrows +0000000000000000005"], 5, False), (["InvRows 5", "invrows 7"], 5, False),
            (["invrows 7", "InvRows 5"], 7, False), (["invrows 5", "invrows 5"], 5, False),
            (["invrows invalid", "invrows 7"], 4, False), (["invrows  7"], 4, False),
            (["invrows", "invrows 7"], 7, False), (["invrows 7 extra data"], 7, False),
            (["invrows 5", "InvSlot2"], 5, False),
        )
        for uniques, rows, editable in cases:
            with self.subTest(uniques=uniques):
                self.data["uniques"] = uniques
                before = deepcopy(self.data)
                self.tab.load_data(self.data)
                self.assertEqual(effective_inventory_rows(uniques), rows)
                self.assertEqual(self.tab.get_inventory_rows(), rows)
                self.assertEqual(set(self.tab.slots), {(x, y) for y in range(rows) for x in range(8)})
                self.assertEqual(self.tab.wider_pockets_checkbox.isEnabled(), editable)
                self.assertIn(f"{rows} rows", self.tab.dimensions_label.text())
                self.assertTrue(validate_item(item(grid_y=rows), self.data))
                if rows:
                    self.assertEqual(validate_item(item(grid_y=rows - 1), self.data), [])
                self.tab.save_changes()
                self.assertEqual(self.data, before)

    def test_add_and_paste_use_seventh_row_and_reject_a_removed_widget(self):
        self.data["uniques"] = ["InvRows 7"]
        self.tab.load_data(self.data)
        last = self.tab.slots[0, 6]

        def add(dialog):
            dialog.prefab_input.set_prefab("SwordIron")
            dialog.validate_and_accept()
            return dialog.result()

        with patch.object(ItemEditDialog, "exec", add):
            self.tab.add_item_to_slot(last)
        self.assertEqual(last.item_data["prefab"], "SwordIron")
        self.tab.copy_slot_item(last)
        self.tab.paste_slot_item(self.tab.slots[1, 6])
        self.assertEqual([(i["grid_x"], i["grid_y"]) for i in self.data["inventory"]], [(0, 6), (1, 6)])
        replacement = dict(self.data, uniques=["invrows 0"], inventory=[])
        self.tab.load_data(replacement)
        with patch("ui.inventoryTab.ItemEditDialog") as dialog:
            self.tab.add_item_to_slot(last)
        self.tab.paste_slot_item(last)
        dialog.assert_not_called()
        self.assertEqual(replacement["inventory"], [])

    def test_pockets_only_change_crossed_purchase_keys_and_preserve_case_and_order(self):
        other = ["mod:key", "invslot3", "invslot7", "invslot2 memory", "InvSlot99"]
        self.data["uniques"] = [*other, "InvRows 5", "invslot1"]
        self.tab.load_data(self.data)
        self.tab.deeper_pockets_checkbox.setChecked(True)
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data["uniques"], [*other, "InvRows 6", "invslot1", "invslot2"])
        self.tab.deeper_pockets_checkbox.setChecked(False)
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data["uniques"], [*other, "InvRows 5", "invslot1"])
        self.tab.wider_pockets_checkbox.setChecked(False)
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data["uniques"], other)

    def test_shrink_lists_all_affected_records_including_hidden_positions(self):
        self.data["uniques"] = ["invrows 6", "invslot1", "invslot2"]
        self.data["inventory"] = [item(grid_y=5), item(grid_x=1, grid_y=5), item(grid_x=8, grid_y=2),
                                  item(prefab="", prefab_hash=-4321, grid_y=10)]
        before = deepcopy(self.data)
        self.tab.load_data(self.data)
        self.assertEqual(self.tab.review_positions_button.text(), "Review Stored Positions (2)")
        messages = []

        def dismiss(dialog):
            messages.append(dialog.text())
            return QMessageBox.Ok

        with patch.object(QMessageBox, "exec", dismiss):
            self.tab.deeper_pockets_checkbox.setChecked(False)
            self.tab.wider_pockets_checkbox.setChecked(False)
        self.assertEqual(self.tab.get_inventory_rows(), 6)
        self.assertTrue(self.tab.wider_pockets_checkbox.isChecked())
        self.assertTrue(self.tab.deeper_pockets_checkbox.isChecked())
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data, before)
        self.assertEqual(len(messages), 2)
        for message, target in zip(messages, (5, 4)):
            self.assertIn(f"Shrinking to {target} rows", message)
            for text in ("(0, 5)", "(1, 5)", "(8, 2)", "(0, 10)", "hash -4321"):
                self.assertIn(text, message)

    def test_adding_explicit_height_requires_hidden_records_to_fit_next_spawn(self):
        hidden = item(grid_y=5)
        self.data["inventory"] = [hidden]
        self.tab.load_data(self.data)
        with patch.object(self.tab, "show_resize_blockers") as blocked:
            self.tab.wider_pockets_checkbox.setChecked(True)
        blocked.assert_called_once_with(5, [(1, hidden)])
        self.assertEqual(self.tab.get_inventory_rows(), 4)
        self.assertEqual(self.data["uniques"], [])
        self.tab.deeper_pockets_checkbox.setChecked(True)
        self.assertIs(self.tab.slots[0, 5].item_data, hidden)
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data["uniques"], ["invrows 6", "invslot1", "invslot2"])

    def test_reverting_staged_pockets_keeps_original_metadata(self):
        self.data["uniques"] = ["InvRows 4", "invslot7"]
        before = deepcopy(self.data)
        self.tab.load_data(self.data)
        self.tab.wider_pockets_checkbox.setChecked(True)
        self.assertEqual(self.tab.get_inventory_rows(), 5)
        self.tab.wider_pockets_checkbox.setChecked(False)
        self.assertTrue(self.tab.save_changes())
        self.assertEqual(self.data, before)

    def test_ambiguous_positions_block_operations_and_show_all_records(self):
        self.data["inventory"] = [item(), item(grid_x=1),
                                  item(prefab="", prefab_hash=-8123, grid_x=0)]
        self.tab.load_data(self.data)
        slot = self.tab.slots[0, 0]
        before = deepcopy(self.data)
        self.assertEqual(slot.property("slotState"), "restricted")
        self.assertEqual(slot.text(), "2 items")
        self.assertIn("hash -8123", slot.toolTip())
        self.assertFalse(slot.isEnabled())
        QApplication.clipboard().setText("unchanged")
        with patch("ui.inventoryTab.ItemEditDialog") as dialog:
            for operation in (self.tab.add_item_to_slot, self.tab.paste_slot_item, self.tab.remove_slot_item,
                              self.tab.edit_slot_item, self.tab.copy_slot_item):
                operation(slot)
        dialog.assert_not_called()
        self.question.assert_not_called()
        self.assertEqual(QApplication.clipboard().text(), "unchanged")
        self.assertEqual(self.data, before)
        self.tab.load_data(dict(self.data, inventory=[item()]))
        self.assertIs(self.tab.slots[0, 0], slot)
        self.assertTrue(slot.isEnabled())
        self.assertEqual(slot.property("slotState"), "occupied")

    def test_bulk_flag_clear_skips_colliding_records(self):
        first = item(cheated=True, cheated_flags=0xA5)
        duplicate = item(prefab="", prefab_hash=-123, cheated=True, cheated_flags=0x87)
        other = item(grid_x=1, cheated=True, cheated_flags=0x93)
        self.data["inventory"] = [first, other, duplicate]
        before = deepcopy(self.data)
        self.tab.load_data(self.data)
        self.question.return_value = QMessageBox.Yes
        self.tab.clear_all_cheated_flags()
        before["inventory"][1]["cheated"] = False
        self.assertEqual(self.data, before)

    def test_late_occupant_during_add_or_remove_does_not_create_or_worsen_collision(self):
        self.tab.load_data(self.data)
        slot = self.tab.slots[0, 0]
        first = item()

        def occupy(dialog):
            dialog.prefab_input.set_prefab("SwordIron")
            self.data["inventory"].append(first)
            return QDialog.Accepted

        with patch.object(ItemEditDialog, "exec", occupy):
            self.tab.add_item_to_slot(slot)
        self.assertEqual(self.data["inventory"], [first])
        self.assertIs(slot.item_data, first)
        second = item(prefab="", prefab_hash=-12345)

        def collide(*args):
            self.data["inventory"].append(second)
            return QMessageBox.Yes

        self.question.side_effect = collide
        self.tab.remove_slot_item(slot)
        self.assertEqual(self.data["inventory"], [first, second])
        self.assertEqual(slot.text(), "2 items")

    def test_ambiguous_slot_mod_cannot_replace_remove_or_place_items(self):
        tracked = item(custom_data={"ExtraSlotsEquippedSlot": "Helmet"})
        ordinary = item(grid_x=1)
        self.data["uniques"] = ["invrows 6"]
        self.data["inventory"] = [tracked, ordinary]
        self.tab.load_data(self.data)
        before = deepcopy(self.data)
        self.assertEqual(self.tab.slots[0, 0].text(), "Mod slot")
        self.assertEqual(self.tab.slots[2, 0].text(), "Read only")
        self.assertFalse(self.tab.wider_pockets_checkbox.isEnabled())
        self.tab.wider_pockets_checkbox.setChecked(False)
        self.assertEqual(self.tab.get_inventory_rows(), 6)
        self.tab.remove_slot_item(self.tab.slots[1, 0])

        def edit(dialog):
            self.assertFalse(dialog.prefab_input.isEnabled())
            self.assertFalse(dialog.equipped_input.isEnabled())
            dialog.prefab_input.set_prefab("SwordIron")
            dialog.equipped_input.setChecked(True)
            dialog.quality_input.setValue(3)
            return QDialog.Accepted

        with patch.object(ItemEditDialog, "exec", edit):
            self.tab.edit_slot_item(self.tab.slots[1, 0])
        self.tab.save_changes()
        before["inventory"][1]["quality"] = 3
        self.assertEqual(self.data, before)
        self.question.assert_not_called()

    def test_paste_refuses_slot_mod_metadata_even_in_an_ordinary_save(self):
        self.tab.load_data(self.data)
        clipboard = {"valheim_editor": "inventory_item", "inventory_version": 110,
                     "item": item(custom_data={"ExtraSlotsEquippedSlot": "Helmet"})}
        QApplication.clipboard().setText(json.dumps(clipboard))
        self.tab.paste_slot_item(self.tab.slots[0, 0])
        self.assertEqual(self.data["inventory"], [])
        self.warning.assert_called_once()

    def test_equipment_collision_is_reported_and_cannot_be_edited(self):
        data, root = equipment_fixture()
        data["inventory"].append(item(grid_y=5, prefab="", prefab_hash=-880))
        self.tab.load_data(data, root)
        self.assertEqual(self.tab.equipment_slots, [])
        details = []

        def dismiss(dialog):
            details.append(dialog.detailedText())
            return QMessageBox.Ok

        with patch.object(QMessageBox, "exec", dismiss):
            self.tab.review_stored_positions()
        self.assertIn("Multiple stored items", details[0])
        self.assertIn("hash -880", details[0])
        self.assertIn("HelmetBronze", details[0])


def wire_item(x, y, prefab=SWORD_IRON, *, flag=0xA5, marker=None):
    primary = 0x41 if marker is None else 0xC1
    record = struct.pack("<i4Bi", 10000, x, y, 0, primary, prefab)
    if marker is not None:
        record += b"\x01" + string("ExtraSlotsEquippedSlot") + string(marker)
    return record + bytes([flag])


def wire_character(inventory, records, uniques, *, health=20.12345):
    # Independent inventory records and uniques inserted into the prior wire fixture.
    original = nested_wire(34, inventory, health=health)
    start = struct.calcsize("<i4f") + len(string("ModPower")) + struct.calcsize("<f")
    end = original.index(strings("SwordIron"), start)
    tail = original[end:].replace(strings("unique"), strings(*uniques), 1)
    nested = original[:start] + struct.pack("<iH", inventory, len(records)) + b"".join(records) + tail
    return character_wire(46 if inventory == 109 else 47, nested)


class InventoryLayoutWireTests(QtTestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / "Input.fch"
        self.target = Path(temporary.name) / "Output.fch"
        with patch("ui.mainWindow.load_config", return_value={
            "is_first_launch": False, "auto_backup": False, "backup_dir": str(self.source.parent / "backups")
        }), patch("ui.mainWindow.is_valheim_running", return_value=False), \
                patch.object(MainWindow, "check_valheim_installation", return_value=False):
            self.window = self.widget(MainWindow)
        self.question.return_value = QMessageBox.Yes

    def save(self):
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.target), "")):
            self.window.save_save_file()

    def test_noop_and_unrelated_edit_preserve_duplicates_outside_items_and_flags(self):
        records = (wire_item(0, 0), wire_item(0, 0, -479, flag=0x87, marker="Helmet"),
                   wire_item(8, 12, -677, flag=0xFE), wire_item(1, 0, flag=0xDD))
        uniques = ("InvRows 7", "invrows 3", "invslot7")
        for inventory in (109, 110):
            with self.subTest(inventory=inventory):
                original = wire_character(inventory, records, uniques)
                self.source.write_bytes(original)
                self.assertTrue(self.window.load_file(self.source))
                self.assertEqual(self.window.inventory_tab.get_inventory_rows(), 7)
                self.assertEqual(self.window.inventory_tab.slots[0, 0].text(), "2 items")
                self.save()
                self.assertEqual(self.target.read_bytes(), original)
                self.window.stats_tab.health_spin.setValue(29.25)
                self.save()
                self.assertEqual(self.target.read_bytes(), wire_character(inventory, records, uniques, health=29.25))

    def test_valid_six_to_five_and_four_shrinks_reload_with_only_owned_keys_changed(self):
        records = (wire_item(0, 1, flag=0xA5), wire_item(7, 3, flag=0x8B))
        raw_keys = ("other", "InvRows 6", "invslot1", "invslot2", "invslot9")
        for version in (109, 110):
            self.source.write_bytes(wire_character(version, records, raw_keys))
            self.assertTrue(self.window.load_file(self.source))
            tab = self.window.inventory_tab
            tab.deeper_pockets_checkbox.setChecked(False)
            self.save()
            self.assertEqual(self.target.read_bytes(),
                             wire_character(version, records, ("other", "InvRows 5", "invslot1", "invslot9")))
            self.assertTrue(self.window.load_file(self.target))
            tab = self.window.inventory_tab
            self.assertEqual(tab.get_inventory_rows(), 5)
            tab.wider_pockets_checkbox.setChecked(False)
            self.save()
            self.assertEqual(self.target.read_bytes(), wire_character(version, records, ("other", "invslot9")))
            self.assertTrue(self.window.load_file(self.target))
            self.assertEqual(self.window.inventory_tab.get_inventory_rows(), 4)

    def test_save_rechecks_shrink_before_opening_picker(self):
        original = wire_character(110, (wire_item(0, 0),), ("invrows 6", "invslot1", "invslot2"))
        self.source.write_bytes(original)
        self.assertTrue(self.window.load_file(self.source))
        tab = self.window.inventory_tab
        tab.deeper_pockets_checkbox.setChecked(False)
        self.assertEqual(tab.get_inventory_rows(), 5)
        late_item = item(grid_y=5)
        self.window.player_data["inventory"].append(late_item)
        with patch.object(QFileDialog, "getSaveFileName") as picker, patch.object(tab, "show_resize_blockers") as blockers:
            self.window.save_save_file()
        picker.assert_not_called()
        blockers.assert_called_once_with(5, [(2, late_item)])
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(tab.get_inventory_rows(), 6)
        self.assertIs(tab.slots[0, 5].item_data, late_item)
