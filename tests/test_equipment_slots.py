"""Synthetic fixtures from the pinned upstream EAQ schema; no private saves."""
import base64
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tests.support import item, create_empty_player_data, create_new_character, playerDataUtil as player
from tests.test_editor import QtTestCase
from subscripts.equipmentSlots import EAQ_EQUIPMENT, eaq_equipment
from subscripts.fchUtil import BinaryReader, compile_fch, decompile_fch
from ui.inventoryTab import InventoryTab
from ui.itemEditDialog import ItemEditDialog
from PySide6.QtWidgets import QDialog


def backup(rows=4, width=8, version=1):
    # ZPackage strings, four int32 fields, then WriteCompressed's byte array.
    # Payload stays opaque: this fixture tests the header, not backup recovery.
    payload = b"opaque compressed snapshot"
    wire = struct.pack("<i", version) + b"\x04date\x05world"
    wire += struct.pack("<5i", 1, width, 3, rows, len(payload)) + payload
    return base64.b64encode(wire).decode("ascii")


def equipment_fixture(rows=4):
    data, root = create_empty_player_data(), create_new_character("Equipment test")
    data["custom_data"] = {"eaqs_visible_rows": str(rows), "eaqs_backup": backup(rows), "other.mod": "opaque"}
    data["inventory"] = [item(), item(
        prefab="HelmetBronze", grid_y=rows + 1, equipped=True, durability=17.123,
        custom_data={"eaqs_player": str(root["player_id"]), "eaqs_slot": "Helmet", "unknown": "retain me"},
        world_level=7, cheated=True)]
    return data, root


class EquipmentRecognitionTests(unittest.TestCase):
    def test_all_equipment_indices_and_extra_rows(self):
        for rows in (4, 6, 9):
            data, root = equipment_fixture(rows)
            template = data["inventory"][1]
            data["inventory"] = []
            for x, name in reversed(list(enumerate(EAQ_EQUIPMENT))):
                equipment = deepcopy(template)
                equipment["grid_x"] = x
                equipment["custom_data"]["eaqs_slot"] = name
                data["inventory"].append(equipment)
            before = deepcopy(data)
            result = eaq_equipment(data, root)
            self.assertEqual([name for name, _ in result], list(EAQ_EQUIPMENT))
            self.assertIs(result[0][1], data["inventory"][-1])
            self.assertEqual(data, before)

    def test_memory_markers_are_not_current_slots(self):
        for change in ({"grid_y": 0}, {"grid_y": 4}, {"grid_x": 1},
                       {"custom_data": {"eaqs_player": "other", "eaqs_slot": "Helmet"}},
                       {"custom_data": {"eaqs_slot": "Helmet"}}):
            with self.subTest(change=change):
                data, root = equipment_fixture()
                data["inventory"][1].update(change)
                self.assertEqual(eaq_equipment(data, root), [])
        data, root = equipment_fixture()
        data["inventory"].append(deepcopy(data["inventory"][1]))
        self.assertEqual(eaq_equipment(data, root), [])
        self.assertEqual(eaq_equipment(data, None), [])

    def test_missing_malformed_and_conflicting_layouts_are_preserved(self):
        for change in ({"eaqs_backup": "not base64"}, {"eaqs_backup": "AAAAAA=="},
                       {"eaqs_backup": backup(width=10)}, {"eaqs_backup": backup(version=2)},
                       {"eaqs_backup": backup(rows=5)}, {"eaqs_visible_rows": "4.0"},
                       {"eaqs_visible_rows": "-1"}, {"eaqs_visible_rows": ""},
                       {"ExtraSlotsDeferredInventory": "opaque"}, {"EquipmentSlotInventory": "old"}):
            with self.subTest(change=change):
                data, root = equipment_fixture()
                data["custom_data"].update(change)
                before = deepcopy(data)
                self.assertEqual(eaq_equipment(data, root), [])
                self.assertEqual(data, before)
        for key in ("eaqs_visible_rows", "eaqs_backup"):
            data, root = equipment_fixture()
            del data["custom_data"][key]
            self.assertEqual(eaq_equipment(data, root), [])
        data, root = equipment_fixture()
        data["known_texts"]["<|>EquipmentSlotInventory"] = "legacy package"
        self.assertEqual(eaq_equipment(data, root), [])
        del data["known_texts"]["<|>EquipmentSlotInventory"]
        data["inventory"][0]["custom_data"]["ExtraSlotsEquippedSlot"] = "Helmet"
        self.assertEqual(eaq_equipment(data, root), [])

    def test_versions_unknown_data_and_checksums_round_trip(self):
        for outer in (46, 47):
            for nested in (33, 34):
                for inventory in (109, 110):
                    with self.subTest(outer=outer, nested=nested, inventory=inventory):
                        data, root = equipment_fixture(7)
                        data.update(version=nested, inventory_version=inventory)
                        data["inventory"].append(item(prefab="", prefab_hash=-1234567, grid_y=12,
                                                      custom_data={"mod": "unknown item state"}))
                        data["trailing_data_hex"] = "ff00fe"
                        packed = player.pack_player_data_hex(data)
                        decoded = player.unpack_player_data_hex(packed)
                        self.assertEqual(player.pack_player_data_hex(decoded), packed)
                        self.assertEqual(decoded["inventory"][1]["custom_data"], data["inventory"][1]["custom_data"])
                        self.assertEqual(len(eaq_equipment(decoded, root)), 1)
                        decoded["inventory"][1]["quality"] = 3
                        edited = player.pack_player_data_hex(decoded)
                        reloaded = player.unpack_player_data_hex(edited)
                        self.assertEqual(reloaded, decoded)
                        self.assertEqual(reloaded["custom_data"], data["custom_data"])
                        root.update(version=outer, player_data_hex=edited)
                        with tempfile.TemporaryDirectory() as directory:
                            source, output = Path(directory) / "test.json", Path(directory) / "test.fch"
                            source.write_text(json.dumps(root), encoding="utf-8")
                            with redirect_stdout(io.StringIO()):
                                compile_fch(str(source), str(output))
                                self.assertEqual(decompile_fch(str(output)), root)
                            reader = BinaryReader(output.read_bytes())
                            self.assertEqual(hashlib.sha512(reader.read_byte_array()).digest(), reader.read_byte_array())


class EquipmentUITests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.data, self.root = equipment_fixture(7)
        self.tab = self.widget(InventoryTab)
        self.tab.load_data(self.data, self.root)

    def test_dedicated_cells_preserve_vanilla_grid_and_opaque_data(self):
        before = deepcopy(self.data)
        self.assertFalse(self.tab.equipment_group.isHidden())
        self.assertEqual(len(self.tab.slots), 32)
        self.assertIs(self.tab.slots[(0, 0)].item_data, self.data["inventory"][0])
        self.assertIs(self.tab.equipment_slots[0].item_data, self.data["inventory"][1])
        self.assertFalse(self.tab.wider_pockets_checkbox.isEnabled())
        self.tab.clear_all_cheated_flags()
        self.tab.save_changes()
        self.assertEqual(self.data, before)

    def test_supported_edit_changes_only_requested_properties(self):
        before = deepcopy(self.data)
        def edit(dialog):
            self.assertFalse(dialog.prefab_input.isEnabled())
            self.assertFalse(dialog.stack_input.isEnabled())
            self.assertFalse(dialog.equipped_input.isEnabled())
            dialog.quality_input.setValue(3)
            dialog.cheated_input.setChecked(False)
            dialog.validate_and_accept()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            return dialog.result()
        with patch.object(ItemEditDialog, "exec", edit):
            self.tab.equipment_slots[0].click()
        before["inventory"][1].update(quality=3, cheated=False)
        self.assertEqual(self.data, before)  # Includes original durability precision.
        self.warning.assert_not_called()

    def test_equipment_remains_reachable_with_expanded_vanilla_inventory(self):
        self.data["uniques"] = ["invrows 6", "invslot1", "invslot2"]
        self.tab.load_data(self.data, self.root)
        self.tab.resize(1100, 700)
        self.tab.show()
        self.app.processEvents()
        self.assertEqual(len(self.tab.slots), 48)
        self.assertGreater(self.tab.scroll_area.verticalScrollBar().maximum(), 0)
        self.tab.scroll_area.ensureWidgetVisible(self.tab.equipment_slots[0])
        self.assertGreater(self.tab.scroll_area.verticalScrollBar().value(), 0)

    def test_cancel_and_accept_without_edits_preserve_every_field(self):
        before = deepcopy(self.data)
        for result in (QDialog.Rejected, QDialog.Accepted):
            with patch.object(ItemEditDialog, "exec", return_value=result):
                self.tab.equipment_slots[0].click()
            self.assertEqual(self.data, before)

    def test_unknown_prefab_and_out_of_range_properties_are_read_only(self):
        for changes in ({"prefab": "", "prefab_hash": -12345}, {"quality": 123}):
            data, root = equipment_fixture()
            data["inventory"][1].update(changes)
            self.tab.load_data(data, root)
            before = deepcopy(data)
            self.assertFalse(self.tab.equipment_slots[0].isEnabled())
            with patch("ui.inventoryTab.ItemEditDialog") as dialog:
                self.tab.edit_equipment_item(self.tab.equipment_slots[0])
            dialog.assert_not_called()
            self.tab.save_changes()
            self.assertEqual(data, before)

    def test_switching_save_cannot_apply_stale_equipment_edits(self):
        before = deepcopy(self.data)
        stale = self.tab.equipment_slots[0]
        replacement = create_empty_player_data()
        def switch(dialog):
            dialog.quality_input.setValue(5)
            self.tab.load_data(replacement)
            return QDialog.Accepted
        with patch.object(ItemEditDialog, "exec", switch):
            stale.click()
        self.assertEqual(self.data, before)
        self.assertTrue(self.tab.equipment_group.isHidden())
        self.assertTrue(self.tab.wider_pockets_checkbox.isEnabled())
        self.assertTrue(all(slot.isEnabled() for slot in self.tab.slots.values()))
        with patch("ui.inventoryTab.ItemEditDialog") as dialog:
            self.tab.edit_equipment_item(stale)
        dialog.assert_not_called()

    def test_unsupported_storage_is_opaque_including_unrelated_vanilla_edit(self):
        for key in ("ExtraSlotsDeferredInventory", "ExtraSlotsInventoryBackup", "EquipmentSlotInventory",
                    "QuickSlotInventory", "ExtendedPlayerData", "unrecognized.mod"):
            with self.subTest(key=key):
                data = create_empty_player_data()
                data["custom_data"] = {key: "opaque value"}
                data["uniques"] = ["invrows 9", "invslot7"]
                data["inventory"] = [item(), item(grid_y=10, custom_data={"mod": "opaque"})]
                self.tab.load_data(data)
                before = deepcopy(data)
                def edit(dialog):
                    dialog.quality_input.setValue(2)
                    return QDialog.Accepted
                with patch.object(ItemEditDialog, "exec", edit):
                    self.tab.slots[(0, 0)].click()
                self.tab.save_changes()
                before["inventory"][0]["quality"] = 2
                self.assertEqual(data, before)
                self.assertEqual(self.tab.equipment_slots, [])
                packed = player.pack_player_data_hex(data)
                decoded = player.unpack_player_data_hex(packed)
                self.assertEqual(decoded["custom_data"], data["custom_data"])
                self.assertEqual(decoded["inventory"][1]["custom_data"], {"mod": "opaque"})
                self.assertEqual(player.pack_player_data_hex(decoded), packed)


if __name__ == "__main__":
    unittest.main()
