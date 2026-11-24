from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog

from tests.support import WOOD_PREFAB_HASH, item, playerDataUtil as player
from tests.test_editor import QtTestCase
from subscripts.fchUtil import compile_fch, decompile_fch
from ui.inventoryTab import InventoryTab
from ui.itemEditDialog import ItemEditDialog


class CrafterTests(QtTestCase):
    def test_rename_preserves_large_id_and_does_not_mutate_original(self):
        original = item(crafter_id=9007199254740993, crafter_name="Original")
        before = deepcopy(original)
        dialog = self.widget(ItemEditDialog, original)
        self.assertTrue(dialog.crafter_group.isChecked())
        self.assertEqual(dialog.crafter_id_input.text(), str(original["crafter_id"]))
        self.assertEqual(dialog.crafter_name_input.text(), "Original")
        dialog.crafter_name_input.setText("Åsa ⚒ <b>Viking</b>")
        self.assertIn("Crafted by Åsa ⚒ <b>Viking</b>", dialog.preview_summary.text())
        self.assertEqual(dialog.preview_summary.textFormat(), Qt.PlainText)
        dialog.apply_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.get_updated_data()["crafter_id"], original["crafter_id"])
        self.assertEqual(dialog.get_updated_data()["crafter_name"], "Åsa ⚒ <b>Viking</b>")
        self.assertEqual(original, before)

    def test_cancel_preserves_attribution(self):
        original = item(crafter_id=123, crafter_name="Original")
        before = deepcopy(original)
        dialog = self.widget(ItemEditDialog, original)
        dialog.crafter_name_input.setText("Changed")
        dialog.crafter_id_input.setText("456")
        dialog.crafter_group.setChecked(False)
        dialog.reject()
        self.assertEqual(original, before)

    def test_uncrafted_item_stays_uncrafted(self):
        dialog = self.widget(ItemEditDialog, item())
        self.assertFalse(dialog.crafter_group.isChecked())
        self.assertFalse(dialog.crafter_name_input.isEnabled())
        self.assertFalse(dialog.crafter_id_input.isEnabled())
        self.assertNotIn("Crafted by", dialog.preview_summary.text())
        dialog.apply_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.get_updated_data()["crafter_id"], 0)
        self.assertEqual(dialog.get_updated_data()["crafter_name"], "")

    def test_remove_and_restore_attribution_before_applying(self):
        dialog = self.widget(ItemEditDialog, item(crafter_id=123, crafter_name="Åsa"))
        dialog.crafter_group.setChecked(False)
        self.assertEqual(dialog.get_updated_data()["crafter_id"], 0)
        self.assertEqual(dialog.get_updated_data()["crafter_name"], "")
        self.assertNotIn("Crafted by", dialog.preview_summary.text())
        dialog.crafter_group.setChecked(True)
        self.assertTrue(dialog.crafter_name_input.isEnabled())
        self.assertEqual(dialog.get_updated_data()["crafter_id"], 123)
        self.assertEqual(dialog.get_updated_data()["crafter_name"], "Åsa")

    def test_invalid_ids_cannot_be_applied(self):
        for value in ("", "abc", "1.5", "1e6", "1_000", "0", str(2**63), str(-(2**63) - 1)):
            with self.subTest(value=value):
                dialog = self.widget(ItemEditDialog, item(crafter_id=123, crafter_name="Åsa"))
                dialog.crafter_id_input.setText(value)
                self.warning.reset_mock()
                dialog.apply_button.click()
                self.assertEqual(dialog.result(), QDialog.Rejected)
                self.warning.assert_called_once()
                # Removing attribution remains possible even with invalid text.
                dialog.crafter_group.setChecked(False)
                dialog.apply_button.click()
                self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_ids_round_trip_without_truncation(self):
        for crafter_id in (-(2**63), 2**63 - 1, 9007199254740993):
            with self.subTest(crafter_id=crafter_id):
                original = item()
                dialog = self.widget(ItemEditDialog, original)
                dialog.crafter_group.setChecked(True)
                dialog.crafter_name_input.setText("Åsa ⚒")
                dialog.crafter_id_input.setText(str(crafter_id))
                dialog.apply_button.click()
                self.assertEqual(dialog.result(), QDialog.Accepted)
                original.update(dialog.get_updated_data())
                self.data["inventory"] = [original]
                loaded = player.unpack_player_data_hex(player.pack_player_data_hex(self.data))
                self.assertEqual(loaded["inventory"][0]["crafter_id"], crafter_id)
                self.assertEqual(loaded["inventory"][0]["crafter_name"], "Åsa ⚒")

    def edit_modal(self, action, changes):
        errors = []

        def apply():
            dialog = self.app.activeModalWidget()
            try:
                changes(dialog)
                dialog.apply_button.click()
                self.assertEqual(dialog.result(), QDialog.Accepted)
            except Exception as error:
                errors.append(error)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(0, apply)
        action()
        if errors:
            raise errors[0]

    def test_inventory_edit_and_remove_persist_in_character_file(self):
        original = item(prefab_hash=WOOD_PREFAB_HASH, crafter_id=9007199254740993, crafter_name="Original",
                        custom_data={"note": "keep"}, cheated=True)
        self.data["inventory"] = [original]
        tab = self.widget(InventoryTab)
        tab.load_data(self.data)
        for remove in (False, True):
            with self.subTest(remove=remove):
                before = deepcopy(original)

                def changes(dialog):
                    dialog.crafter_name_input.setText("Åsa ⚒")
                    dialog.crafter_group.setChecked(not remove)

                self.edit_modal(lambda: tab.edit_slot_item(tab.slots[(0, 0)]), changes)
                expected = dict(before, crafter_id=0 if remove else before["crafter_id"],
                                crafter_name="" if remove else "Åsa ⚒")
                self.assertEqual(original, expected)
                tab.save_changes()
                self.root["player_data_hex"] = player.pack_player_data_hex(self.data)
                with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
                    source = Path(directory) / "source.json"
                    target = Path(directory) / "character.fch"
                    source.write_text(json.dumps(self.root), encoding="utf-8")
                    compile_fch(str(source), str(target))
                    payload = decompile_fch(str(target))["player_data_hex"]
                loaded, = player.unpack_player_data_hex(payload)["inventory"]
                for key, value in expected.items():
                    self.assertEqual(loaded[key], value, key)
                with patch.dict(player.ITEM_HASH_TO_PREFAB, {}, clear=True):
                    offline = player.unpack_player_data_hex(payload)
                    self.assertEqual(offline["inventory"], [dict(loaded, prefab="")])
                    self.assertEqual(player.pack_player_data_hex(offline), payload)
                reopened = self.widget(ItemEditDialog, loaded)
                self.assertEqual(reopened.crafter_group.isChecked(), not remove)
                self.assertEqual(reopened.crafter_name_input.text(), expected["crafter_name"])

    def test_add_inventory_item_with_attribution(self):
        tab = self.widget(InventoryTab)
        tab.load_data(self.data)

        def changes(dialog):
            dialog.prefab_input.set_prefab("SwordIron")
            dialog.crafter_group.setChecked(True)
            dialog.crafter_name_input.setText("Åsa")
            dialog.crafter_id_input.setText("1234567890123")

        self.edit_modal(lambda: tab.add_item_to_slot(tab.slots[(0, 0)]), changes)
        self.assertEqual(len(self.data["inventory"]), 1)
        self.assertEqual(self.data["inventory"][0]["crafter_id"], 1234567890123)
        self.assertEqual(self.data["inventory"][0]["crafter_name"], "Åsa")
