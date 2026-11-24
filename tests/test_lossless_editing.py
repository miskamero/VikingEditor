from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from tests.test_editor import QtTestCase
from tests.test_player_versions import string, wire_payload
from ui.itemEditDialog import ItemEditDialog
from ui.mainWindow import MainWindow


FOODS = (("Bread", 30.12345), ("ModFood", 400000.125), (" Third ", -0.12345), ("LastFood", 1.01234))
NAME = "  Wire Viking  "
CRAFTED_BY = "\u00c5sa"
# Verified prefab hash from the game's stable-hash routine for SwordIron.
SWORD_IRON = -110263489


def food_bytes(foods):
    return struct.pack("<i", len(foods)) + b"".join(
        string(name) + struct.pack("<f", remaining) for name, remaining in foods
    )


def nested_wire(player, inventory, *, health=20.12345, model=17, power="ModPower", foods=FOODS,
                crafter=CRAFTED_BY, cheat_byte=0xA5, prefab_hash=SWORD_IRON):
    original, _, flag, _ = wire_payload(player, inventory)
    item_end = flag + 1
    # Keep the independent fixture's later collections and version-specific tail.
    prefix = struct.pack("<i4f", player, 24.12345, health, 40.12345, 1.5)
    prefix += string(power) + struct.pack("<f", 123.12345)
    prefix += struct.pack("<iH", inventory, 2)
    prefix += struct.pack("<i4BHHiq", 2147483647, 2, 1, 7, 255, 65535, 65535, -150, 1234567890123)
    prefix += string(crafter) + struct.pack("<i", prefab_hash)
    prefix += b"\x02" + string("note") + string("crafted") + string("mod") + string("opaque")
    prefix += bytes([cheat_byte])
    tail = original[item_end:].replace(
        struct.pack("<6fi", 1, .5, .25, 0, 1, .5, 1),
        struct.pack("<6fi", 1.25, .12345, .25, -.25, 1, .54321, model),
        1,
    )
    tail = tail.replace(food_bytes((("Bread", 300.5),)), food_bytes(foods), 1)
    tail = tail.replace(struct.pack("<3fi", 50, 25, 12.5, 3), struct.pack("<3fi", 31.12345, 25.12345, -0.0, 3), 1)
    return prefix + tail


def character_wire(outer, nested):
    # Independent PlayerProfile.SavePlayerToDisk framing, 205 stats and ten profile groups.
    stats = bytes(205 * 4) + bytes(3 * 4) + struct.pack("<i", 5) + bytes(10 * 4)
    body = struct.pack("<iii", outer, 205, 10) + stats * 10
    body += b"\x01" + struct.pack("<i", 0) + string(NAME) + struct.pack("<q", 1234)
    body += string("seed") + struct.pack("<BqBi", 1, 1770000000, 1, len(nested)) + nested
    return struct.pack("<i", len(body)) + body + struct.pack("<i", 64) + hashlib.sha512(body).digest()


class LosslessGuiTests(QtTestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "source.fch"
        self.output = self.directory / "output.fch"
        with patch("ui.mainWindow.load_config", return_value={
            "is_first_launch": False, "auto_backup": False, "backup_dir": str(self.directory / "backups")
        }), patch("ui.mainWindow.is_valheim_running", return_value=False), \
                patch.object(MainWindow, "check_valheim_installation", return_value=False):
            self.window = self.widget(MainWindow)
        critical = patch.object(QMessageBox, "critical")
        self.critical = critical.start()
        self.addCleanup(critical.stop)
        self.question.return_value = QMessageBox.Yes

    def load_wire(self, outer=47, player=34, inventory=110, *, backup=False, **changes):
        wire = character_wire(outer, nested_wire(player, inventory, **changes))
        self.source.write_bytes(wire)
        self.assertTrue(self.window.load_file(self.source, backup=backup), self.critical.call_args)
        return wire

    def save_to(self, path):
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.window.save_save_file()

    def test_eight_versions_noop_and_one_field_edits_are_byte_exact(self):
        for outer, player, inventory in itertools.product((46, 47), (33, 34), (109, 110)):
            with self.subTest(outer=outer, player=player, inventory=inventory):
                original = self.load_wire(outer, player, inventory)
                self.assertEqual(self.window.stats_tab.food_table.rowCount(), 4)
                self.assertEqual(self.window.stats_tab.gp_combo.currentData(), "ModPower")
                self.assertEqual(self.window.appearance_tab.model_combo.currentData(), 17)
                self.save_to(self.output)
                self.assertEqual(self.output.read_bytes(), original)
                self.window.tabs.setCurrentWidget(self.window.stats_tab)
                self.window.stats_tab.health_spin.setValue(19.25)
                self.window.tabs.setCurrentWidget(self.window.appearance_tab)
                expected = character_wire(outer, nested_wire(player, inventory, health=19.25))
                for _ in range(2):
                    self.save_to(self.output)
                    self.assertEqual(self.output.read_bytes(), expected)
                self.assertEqual(self.source.read_bytes(), original)
        self.critical.assert_not_called()

    def test_food_edit_and_removal_preserve_other_records_and_explicit_power_model_changes(self):
        self.load_wire()
        vitals = self.window.stats_tab
        appearance = self.window.appearance_tab
        self.assertFalse(vitals.btn_add_food.isEnabled())
        vitals.food_table.cellWidget(0, 1).setValue(25.5)
        vitals.food_table.item(2, 0).setText("Replacement")
        vitals.food_table.selectRow(3)
        vitals.btn_remove_food.click()
        self.assertEqual(vitals.food_table.rowCount(), 3)
        power = "GP_Eikthyr"
        vitals.gp_combo.setCurrentIndex(vitals.gp_combo.findData(power))
        appearance.model_combo.setCurrentIndex(appearance.model_combo.findData(1))
        expected_foods = (("Bread", 25.5), FOODS[1], ("Replacement", FOODS[2][1]))
        self.save_to(self.output)
        self.assertEqual(self.output.read_bytes(),
                         character_wire(47, nested_wire(34, 110, power=power, model=1, foods=expected_foods)))
        vitals.gp_combo.setCurrentIndex(vitals.gp_combo.findData(""))
        self.save_to(self.output)
        self.assertEqual(self.output.read_bytes(),
                         character_wire(47, nested_wire(34, 110, power="", model=1, foods=expected_foods)))

    def test_new_document_and_backup_reset_pending_values_and_unlisted_choices(self):
        self.load_wire()
        vitals = self.window.stats_tab
        appearance = self.window.appearance_tab
        vitals.health_spin.setValue(49)
        original = self.load_wire(power="AnotherMod", model=-171, backup=True)
        self.assertEqual(vitals.gp_combo.currentData(), "AnotherMod")
        self.assertEqual(vitals.gp_combo.findData("ModPower"), -1)
        self.assertEqual(appearance.model_combo.currentData(), -171)
        self.assertEqual(appearance.model_combo.findData(17), -1)
        self.save_to(self.output)
        self.assertEqual(self.output.read_bytes(), original)
        with patch.object(QInputDialog, "getText", return_value=("New Character", True)):
            self.window.new_character()
        self.assertEqual(vitals.gp_combo.currentData(), "")
        self.assertEqual(vitals.gp_combo.findData("AnotherMod"), -1)
        self.assertEqual(appearance.model_combo.currentData(), 0)
        self.assertEqual(appearance.model_combo.findData(-171), -1)
        self.assertEqual(vitals.food_table.rowCount(), 0)
        self.assertEqual(vitals.health_spin.value(), 25)
        self.save_to(self.output)
        self.critical.assert_not_called()

    def test_accepting_same_preview_color_preserves_the_original_channels(self):
        original = self.load_wire()
        appearance = self.window.appearance_tab
        with patch("ui.appearanceTab.QColorDialog.getColor", side_effect=lambda color, *args: color):
            appearance.choose_skin_color()
        self.save_to(self.output)
        self.assertEqual(self.output.read_bytes(), original)
        with patch("ui.appearanceTab.QColorDialog.getColor", return_value=QColor(255, 0, 0)):
            appearance.choose_skin_color()
        self.save_to(self.output)
        nested = nested_wire(34, 110).replace(struct.pack("<3f", 1.25, .12345, .25), struct.pack("<3f", 1, 0, 0), 1)
        self.assertEqual(self.output.read_bytes(), character_wire(47, nested))

    def test_canceled_and_failed_save_preserve_pending_edit_for_retry(self):
        original = self.load_wire()
        vitals = self.window.stats_tab
        vitals.health_spin.setValue(11.5)
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.window.save_save_file()
        self.assertFalse(self.output.exists())
        with patch("ui.mainWindow.write_fch", side_effect=OSError("temporary write failure")):
            self.save_to(self.output)
        self.critical.assert_called_once()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), original)
        self.save_to(self.output)
        self.assertEqual(self.output.read_bytes(), character_wire(47, nested_wire(34, 110, health=11.5)))

    def apply_item(self, edit=None, *, accept=True):
        inventory = self.window.inventory_tab
        def interact(dialog):
            if edit:
                edit(dialog)
            if accept:
                dialog.apply_button.click()
                self.assertEqual(dialog.result(), QDialog.Accepted)
            else:
                dialog.reject()
            return dialog.result()

        with patch.object(ItemEditDialog, "exec", interact):
            inventory.edit_slot_item(inventory.slots[(2, 1)])

    def test_item_apply_cancel_and_single_crafter_edit_preserve_every_other_byte(self):
        for prefab_hash in (SWORD_IRON, -1234567):
            with self.subTest(prefab_hash=prefab_hash):
                original = self.load_wire(prefab_hash=prefab_hash)
                self.apply_item()
                self.apply_item(lambda dialog: dialog.stack_input.setValue(1), accept=False)
                self.save_to(self.output)
                self.assertEqual(self.output.read_bytes(), original)
                crafter = "New crafter \u03a9"
                self.apply_item(lambda dialog: dialog.crafter_name_input.setText(crafter))
                self.save_to(self.output)
                self.assertEqual(self.output.read_bytes(), character_wire(
                    47, nested_wire(34, 110, prefab_hash=prefab_hash, crafter=crafter),
                ))
        self.warning.assert_not_called()
        self.critical.assert_not_called()

    def test_individual_and_bulk_clear_match_game_semantics(self):
        for version in (109, 110):
            for bulk in (False, True):
                with self.subTest(inventory=version, bulk=bulk):
                    original = self.load_wire(inventory=version)
                    tab = self.window.inventory_tab
                    record = tab.slots[(2, 1)].item_data
                    self.assertEqual(record["cheated_flags"], 0xA5)
                    self.assertIs(record["cheated"], version == 110)
                    self.assertEqual(tab.clear_cheated_button.isEnabled(), version == 110)
                    if bulk:
                        tab.clear_all_cheated_flags()
                    else:
                        def clear(dialog):
                            self.assertEqual(dialog.cheated_input.isEnabled(), version == 110)
                            self.assertEqual(dialog.cheated_input.isChecked(), version == 110)
                            dialog.cheated_input.setChecked(False)
                        self.apply_item(clear)
                    self.save_to(self.output)
                    expected = original if version == 109 else character_wire(
                        47, nested_wire(34, 110, cheat_byte=0xA4),
                    )
                    self.assertEqual(self.output.read_bytes(), expected)

    def test_clipboard_preserves_raw_metadata_without_reinterpreting_other_versions(self):
        clipboard = QApplication.clipboard()
        for inventory in (109, 110):
            with self.subTest(inventory=inventory):
                self.load_wire(inventory=inventory)
                tab = self.window.inventory_tab
                record = deepcopy(tab.slots[(2, 1)].item_data)
                tab.copy_slot_item(tab.slots[(2, 1)])
                text = clipboard.text()
                self.assertEqual(json.loads(text)["inventory_version"], inventory)
                tab.paste_slot_item(tab.slots[(4, 1)])
                self.assertEqual(tab.slots[(4, 1)].item_data, dict(record, grid_x=4))
                self.load_wire(inventory=219 - inventory)
                clipboard.setText(text)
                tab.paste_slot_item(tab.slots[(4, 1)])
                self.assertIsNone(tab.slots[(4, 1)].item_data)
                self.assertEqual(self.warning.call_args.args[1], "Incompatible Item Flag")

    def test_untagged_clipboard_with_opaque_low_bit_requires_a_fresh_copy_for_inventory_110(self):
        self.load_wire(inventory=109)
        inventory = self.window.inventory_tab
        legacy = json.dumps({"valheim_editor": "inventory_item", "item": inventory.slots[(2, 1)].item_data})
        self.load_wire(inventory=110)
        QApplication.clipboard().setText(legacy)
        inventory.paste_slot_item(inventory.slots[(4, 1)])
        self.assertIsNone(inventory.slots[(4, 1)].item_data)
        self.assertEqual(self.warning.call_args.args[1], "Unknown Inventory Version")
