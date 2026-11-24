import json
from itertools import product
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from subscripts.fchUtil import compile_fch, parse_fch
from subscripts.playerDataUtil import ITEM_HASH_TO_PREFAB
from tests.test_editor import QtTestCase
from tests.test_lossless_editing import nested_wire
from tests.test_player_versions import string
from tests.test_serialization_boundaries import profile_wire, sign, stats_wire, world_wire
from ui.appearanceTab import AppearanceTab
from ui.backupManagerDialog import BackupManagerDialog
from ui.mainWindow import MainWindow


class DocumentLifecycleTests(QtTestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "current.fch"
        self.other = self.directory / "other.fch"
        self.target = self.directory / "output.fch"
        self.backups = self.directory / "backups"
        config = {"is_first_launch": False, "auto_backup": False, "backup_dir": str(self.backups)}
        with patch("ui.mainWindow.load_config", return_value=config), \
                patch("ui.mainWindow.is_valheim_running", return_value=False), \
                patch.object(MainWindow, "check_valheim_installation", return_value=False):
            self.window = self.widget(MainWindow)
        critical = patch.object(QMessageBox, "critical")
        self.critical = critical.start()
        self.addCleanup(critical.stop)
        self.original = profile_wire(nested_wire(34, 110, health=19.25))
        self.source.write_bytes(self.original)
        self.other_wire = profile_wire(nested_wire(33, 109), name="Other Viking")
        self.other.write_bytes(self.other_wire)
        self.assertTrue(self.window.load_file(self.source))

    def save_to(self, filename):
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(filename), "")):
            return self.window.save_save_file()

    def open_other(self):
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.other), "")), \
                patch("ui.mainWindow.save_config"):
            self.window.open_save_file()

    def respond(self, *, dirty, otherwise=QMessageBox.Yes):
        self.question.side_effect = lambda _, title, *args: dirty if title == "Unsaved Character Changes" else otherwise

    def test_each_major_edit_category_is_dirty_and_read_only_interactions_are_clean(self):
        window = self.window
        self.assertFalse(window.has_unsaved_changes())
        window.tabs.setCurrentWidget(window.worlds_tab)
        window.worlds_tab.world_search.setText("Nord")
        window.tabs.setCurrentWidget(window.character_tab)
        window.character_tab.copy_player_id()
        self.assertFalse(window.has_unsaved_changes())

        def change_skill():
            skills = window.skills_tab
            row = next(i for i in range(skills.table.rowCount())
                       if skills.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == 1)
            skills.table.cellWidget(row, 1).setValue(23.5)

        def change_inventory():
            window.inventory_tab.remove_slot_item(window.inventory_tab.slots[2, 1])

        for name, edit in (
            ("name", lambda: window.character_tab.name_input.setText("Renamed")),
            ("vitals", lambda: window.stats_tab.health_spin.setValue(18.5)),
            ("food", lambda: window.stats_tab.food_table.cellWidget(0, 1).setValue(10)),
            ("skill", change_skill),
            ("appearance", lambda: window.appearance_tab.model_combo.setCurrentIndex(0)),
            ("character flags", lambda: window.stats_tab.used_cheats_check.setChecked(True)),
            ("pockets", lambda: window.inventory_tab.wider_pockets_checkbox.setChecked(True)),
            ("inventory removal", change_inventory),
            ("bulk flags", lambda: window.inventory_tab.clear_all_cheated_flags()),
            ("direct inventory edit", lambda: window.player_data["inventory"][0].update(stack=11)),
        ):
            with self.subTest(name=name):
                self.respond(dirty=QMessageBox.Discard)
                self.assertTrue(window.load_file(self.source))
                edit()
                self.assertTrue(window.has_unsaved_changes())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_revert_successful_save_and_json_export_compare_effective_bytes(self):
        self.window.stats_tab.health_spin.setValue(17.25)
        self.assertTrue(self.window.has_unsaved_changes())
        self.window.stats_tab.health_spin.setValue(19.25)
        self.assertFalse(self.window.has_unsaved_changes())
        self.window.character_tab.name_input.setText("Pending")
        self.window.inventory_tab.wider_pockets_checkbox.setChecked(True)
        baseline = self.window.saved_digest
        output = self.directory / "draft.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output), "")):
            self.window.export_decompiled_json()
        self.assertEqual(json.loads(output.read_bytes())["character_name"], "Pending")
        self.assertTrue(self.window.has_unsaved_changes())
        self.assertEqual(self.window.saved_digest, baseline)
        self.assertTrue(self.save_to(self.target))
        self.assertEqual(self.window.current_revision.digest, self.window.saved_digest)
        self.assertFalse(self.window.has_unsaved_changes())
        self.assertEqual(self.window.root_save["character_name"], "Pending")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_open_cancel_failed_save_conflict_and_discard(self):
        self.window.stats_tab.health_spin.setValue(18.5)
        active_tabs = self.window.tabs
        self.respond(dirty=QMessageBox.Cancel)
        self.open_other()
        self.assertIs(self.window.tabs, active_tabs)
        self.respond(dirty=QMessageBox.Save)
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.open_other()
        self.window.character_tab.name_input.clear()
        with patch.object(QFileDialog, "getSaveFileName") as picker:
            self.open_other()
        picker.assert_not_called()
        self.assertEqual(self.warning.call_args.args[1], "Invalid Character Name")
        self.window.character_tab.name_input.setText("Wire Viking")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.target), "")), \
                patch("ui.mainWindow.write_fch", side_effect=OSError("failed write")):
            self.open_other()
        self.window.config["auto_backup"] = True
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.target), "")), \
                patch.object(self.window, "create_backup", side_effect=OSError("failed recovery copy")):
            self.open_other()
        self.assertIn("failed recovery copy", self.critical.call_args.args[2])
        self.source.write_bytes(self.other_wire)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.source), "")):
            self.open_other()
        self.assertEqual(self.warning.call_args.args[1], "Save Conflict")
        self.assertIs(self.window.tabs, active_tabs)
        self.assertEqual(self.window.stats_tab.health_spin.value(), 18.5)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), self.other_wire)
        self.respond(dirty=QMessageBox.Discard)
        self.open_other()
        self.assertEqual(self.window.root_save["character_name"], "Other Viking")
        self.assertFalse(self.window.has_unsaved_changes())

    def test_prepare_failure_and_source_change_preserve_active_widgets_and_pending_edits(self):
        self.window.character_tab.name_input.setText("Keep this edit")
        tabs = self.window.tabs
        with patch.object(AppearanceTab, "load_data", side_effect=RuntimeError("candidate tab failed")):
            self.assertFalse(self.window.load_file(self.other))
        self.assertIn("candidate tab failed", self.critical.call_args.args[2])
        self.question.assert_not_called()

        def change_during_confirmation(*args):
            self.other.write_bytes(self.original)
            return QMessageBox.Discard

        self.question.side_effect = change_during_confirmation
        self.assertFalse(self.window.load_file(self.other))
        self.assertIn("changed", self.critical.call_args.args[2])
        self.assertIs(self.window.tabs, tabs)
        self.assertEqual(self.window.character_tab.name_input.text(), "Keep this edit")
        self.assertTrue(self.window.has_unsaved_changes())

    def test_successful_save_to_the_open_candidate_reloads_the_saved_revision(self):
        self.window.character_tab.name_input.setText("Saved at candidate")
        self.respond(dirty=QMessageBox.Save)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.other), "")):
            self.open_other()
        self.assertEqual(self.window.root_save["character_name"], "Saved at candidate")
        self.assertEqual(self.other.read_bytes(), profile_wire(nested_wire(34, 110, health=19.25), name="Saved at candidate"))
        self.assertFalse(self.window.has_unsaved_changes())

    def test_backup_open_and_new_respect_cancel_and_explicit_discard(self):
        self.window.character_tab.name_input.setText("Keep pending name")
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        with patch.object(dialog, "get_selected_backup", return_value=self.other):
            self.respond(dirty=QMessageBox.Cancel)
            dialog.open_backup()
            self.assertEqual(self.window.character_tab.name_input.text(), "Keep pending name")
            self.respond(dirty=QMessageBox.Discard)
            dialog.open_backup()
        self.assertTrue(self.window.loaded_backup)
        self.assertFalse(self.window.has_unsaved_changes())
        self.window.stats_tab.health_spin.setValue(15)
        with patch.object(QInputDialog, "getText", return_value=("Blank template", True)) as name:
            self.respond(dirty=QMessageBox.Cancel)
            self.window.new_character()
            self.assertEqual(self.window.stats_tab.health_spin.value(), 15)
            self.respond(dirty=QMessageBox.Discard)
            self.window.new_character()
        self.assertIn("empty inventory", name.call_args.args[2])
        self.assertFalse(self.window.loaded_backup)
        self.assertTrue(self.window.has_unsaved_changes())
        self.assertIsNone(self.window.current_fch)

    def test_exit_and_window_close_share_the_same_guard(self):
        self.window.show()
        self.window.character_tab.name_input.setText("Unsaved name")
        self.respond(dirty=QMessageBox.Cancel)
        exit_action = next(action for action in self.window.findChildren(QAction) if action.text() == "Exit")
        exit_action.trigger()
        self.assertTrue(self.window.isVisible())
        self.respond(dirty=QMessageBox.Save)
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertFalse(self.window.close())
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.target), "")):
            self.assertTrue(self.window.close())
        self.assertEqual(parse_fch(self.target.read_bytes())["character_name"], "Unsaved name")
        self.assertFalse(self.window.has_unsaved_changes())

    def test_restore_over_open_file_rejects_cancel_and_saves_edits_separately(self):
        self.window.stats_tab.health_spin.setValue(18.5)
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        self.respond(dirty=QMessageBox.Cancel)
        dialog.restore_file(self.other, self.source)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertTrue(self.window.has_unsaved_changes())
        self.respond(dirty=QMessageBox.Discard)
        with patch("ui.backupManagerDialog.atomic_write", side_effect=OSError("failed restore write")):
            dialog.restore_file(self.other, self.source)
        self.assertEqual(self.window.stats_tab.health_spin.value(), 18.5)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.respond(dirty=QMessageBox.Save)
        with patch.object(QFileDialog, "getSaveFileName", side_effect=[(str(self.source), ""), (str(self.target), "")]):
            dialog.restore_file(self.other, self.source)
        self.assertEqual(self.source.read_bytes(), self.other_wire)
        self.assertEqual(self.target.read_bytes(), profile_wire(nested_wire(34, 110, health=18.5)))
        self.assertEqual(Path(self.window.current_fch), self.target)
        self.assertFalse(self.window.has_unsaved_changes())

    def test_compatibility_gate_precedes_layout_and_supported_loads_remain_clean(self):
        for version, wire in ((43, sign(struct.pack("<i", 43))),
                              (48, profile_wire(nested_wire(34, 110), version=48))):
            self.other.write_bytes(wire)
            with self.assertRaisesRegex(ValueError, f"Unsupported character profile version {version}"):
                parse_fch(wire)
            self.assertFalse(self.window.load_file(self.other))
            self.assertIn(f"Unsupported character profile version {version}", self.critical.call_args.args[2])
            self.assertEqual(self.window.current_fch, self.source)
        for profile, player, inventory in product((46, 47), (33, 34), (109, 110)):
            self.other.write_bytes(profile_wire(nested_wire(player, inventory), version=profile))
            self.assertTrue(self.window.load_file(self.other))
            self.assertFalse(self.window.has_unsaved_changes())
        self.question.assert_not_called()

    def test_absent_payload_is_metadata_only_and_present_empty_is_invalid(self):
        absent = profile_wire(None, worlds=[world_wire(11)])
        self.other.write_bytes(absent)
        self.assertTrue(self.window.load_file(self.other))
        self.assertIsNone(self.window.player_data)
        self.assertTrue(self.window.character_tab.name_input.isReadOnly())
        self.assertFalse(self.window.btn_save_save.isEnabled())
        self.assertFalse(self.window.has_unsaved_changes())
        self.assertIn("Profile only", self.window.file_label.text())
        self.assertEqual(self.window.worlds_tab.world_id_label.text(), "11")
        json_file = self.directory / "profile.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(json_file), "")):
            self.window.export_decompiled_json()
        self.assertIsNone(json.loads(json_file.read_bytes())["player_data"])
        compile_fch(json_file, self.target)
        self.assertEqual(self.target.read_bytes(), absent)
        self.source.write_bytes(profile_wire(b""))
        self.assertFalse(self.window.load_file(self.source))
        self.assertIn("Truncated", self.critical.call_args.args[2])
        self.assertEqual(self.window.current_fch, self.other)

    def test_blank_template_serializes_empty_inventory_generated_seed_and_intro_flag_off(self):
        with patch.object(QInputDialog, "getText", return_value=("Blank", True)), \
                patch("subscripts.newCharacter.generate_start_seed", return_value="BlankSeed1"), \
                patch("subscripts.newCharacter.generate_player_id", return_value=891):
            self.window.new_character()
        self.assertTrue(self.save_to(self.target))
        wire = self.target.read_bytes()
        # Independently locate the root and nested fields using their wire layouts.
        buckets = stats_wire(stat_count=205) * 10
        root_offset = 4 + struct.calcsize("<iii") + len(buckets)
        identity = b"\x00" + struct.pack("<i", 0) + string("Blank") + struct.pack("<q", 891) + string("BlankSeed1")
        self.assertEqual(wire[root_offset:root_offset + len(identity)], identity)
        nested_offset = root_offset + len(identity) + struct.calcsize("<BqBi")
        inventory_offset = nested_offset + struct.calcsize("<i4f") + 1 + 4
        self.assertEqual(struct.unpack_from("<iH", wire, inventory_offset), (110, 0))

    def test_appearance_changes_only_selected_prefab_on_the_wire(self):
        original = nested_wire(34, 110, model=0)
        original = original.replace(string("Hair1"), string("nohair"), 1).replace(string("Beard1"), string("nobeard"), 1)
        self.other.write_bytes(profile_wire(original))
        self.assertTrue(self.window.load_file(self.other))
        self.assertTrue(self.save_to(self.target))
        self.assertEqual(self.target.read_bytes(), profile_wire(original))
        appearance = self.window.appearance_tab
        self.respond(dirty=QMessageBox.Cancel)
        for combo, before, after in ((appearance.hair_combo, "nohair", "Hair38"),
                                     (appearance.beard_combo, "nobeard", "Beard19"),
                                     (appearance.hair_combo, "Hair38", "HairNone"),
                                     (appearance.beard_combo, "Beard19", "BeardNone")):
            combo.setCurrentIndex(combo.findData(after))
            self.assertTrue(self.save_to(self.target))
            original = original.replace(string(before), string(after), 1)
            self.assertEqual(self.target.read_bytes(), profile_wire(original))

    def test_catalog_result_rebinds_open_hash_only_slot_without_editing_character(self):
        from copy import deepcopy
        from tests.test_lossless_editing import SWORD_IRON

        window = self.window
        icon = self.directory / "new-icon.png"
        Image.new("RGBA", (8, 8), "red").save(icon)
        with patch.dict(ITEM_HASH_TO_PREFAB, {}, clear=True):
            self.assertTrue(window.load_file(self.source))
            slot = window.inventory_tab.slots[2, 1]
            unknown = window.inventory_tab.slots[3, 1]
            record = slot.item_data
            self.assertIn("Unknown item", slot.accessibleName())
            self.assertEqual(record["prefab_hash"], SWORD_IRON)
            data = deepcopy(window.player_data)
            with patch("ui.inventorySlot.get_item_icon_path", side_effect=lambda prefab, variant: icon if prefab else None) as icons:
                with patch("ui.mainWindow.load_saved_valheim_path", return_value=self.directory), \
                        patch("ui.mainWindow.is_valid_valheim_installation", return_value=True), \
                        patch("ui.mainWindow.scan_item_database", return_value={SWORD_IRON: "SwordIron"}):
                    window.update_item_database()
                    for _ in range(100):
                        if window.item_database_worker is None:
                            break
                        QTest.qWait(10)
                    self.assertIsNone(window.item_database_worker)
                icons.assert_any_call("SwordIron", -150)
                self.assertIn("Iron", slot.accessibleName())
                self.assertIn("Unknown item", unknown.accessibleName())
                self.assertFalse(slot.icon_label.pixmap().isNull())
                self.assertEqual(window.player_data, data)
                self.assertIs(slot.item_data, record)
                self.assertFalse(window.has_unsaved_changes())
                window.character_tab.name_input.setText("Pending catalog rename")
                window.refresh_item_catalog({SWORD_IRON: "SwordIron"})
                self.assertTrue(window.has_unsaved_changes())
                self.assertEqual(window.character_tab.name_input.text(), "Pending catalog rename")
                self.assertIs(slot.item_data, record)
        self.assertEqual(self.source.read_bytes(), self.original)
