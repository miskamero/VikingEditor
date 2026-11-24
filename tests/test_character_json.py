from contextlib import redirect_stderr
from copy import deepcopy
import io
from itertools import product
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from subscripts.fchUtil import character_json, compile_fch, main, parse_fch
from subscripts.playerDataUtil import unpack_player_data_hex
from tests.test_editor import QtTestCase
from tests.test_lossless_editing import nested_wire
from tests.test_player_versions import strings
from tests.test_serialization_boundaries import profile_wire, stats_wire, world_wire
from ui.itemEditDialog import ItemEditDialog
from ui.mainWindow import MainWindow


class CharacterJsonTests(QtTestCase):
    def setUp(self):
        super().setUp()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "source.fch"
        self.json_file = self.directory / "export.json"
        self.compiled = self.directory / "output.fch"
        config = {"is_first_launch": False, "auto_backup": False, "last_save_dir": str(self.directory)}
        with patch("ui.mainWindow.load_config", return_value=config), \
                patch("ui.mainWindow.is_valheim_running", return_value=False), \
                patch.object(MainWindow, "check_valheim_installation", return_value=False):
            self.window = self.widget(MainWindow)
        critical = patch.object(QMessageBox, "critical")
        self.critical = critical.start()
        self.addCleanup(critical.stop)

    def load_wire(self, original):
        self.source.write_bytes(original)
        self.assertTrue(self.window.load_file(self.source), self.critical.call_args)

    def export(self, filename=None):
        path = self.json_file if filename is None else filename
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.window.export_decompiled_json()

    def test_gui_and_cli_json_round_trip_all_eight_supported_combinations(self):
        for outer, player, inventory in product((46, 47), (33, 34), (109, 110)):
            with self.subTest(outer=outer, player=player, inventory=inventory):
                original = profile_wire(nested_wire(player, inventory) + b"\x00\x80\xff", version=outer,
                                        worlds=[world_wire(-3, map_data=b"")],
                                        profiles=[stats_wire([("Example world", 12.125)])])
                self.load_wire(original)
                self.export()
                report = json.loads(self.json_file.read_bytes())
                self.assertNotIn("player_data_hex", report)
                self.assertEqual(report["player_data"]["inventory_version"], inventory)
                self.assertEqual(report["player_data"]["trailing_data_hex"], "0080ff")
                self.assertEqual(main(["pack", str(self.json_file), str(self.compiled)]), 0)
                self.assertEqual(self.compiled.read_bytes(), original)
                self.assertEqual(main(["unpack", str(self.source), str(self.json_file)]), 0)
                self.assertEqual(main(["pack", str(self.json_file), str(self.compiled)]), 0)
                self.assertEqual(self.compiled.read_bytes(), original)
        self.critical.assert_not_called()

    def test_export_collects_all_editable_tabs_without_committing_document(self):
        suffix = b"\xfe\x00\xff"
        child = nested_wire(34, 110) + suffix
        worlds = [world_wire(-9)]
        original = profile_wire(child, worlds=worlds)
        self.load_wire(original)
        window = self.window
        window.character_tab.name_input.setText("Pending Viking")
        window.stats_tab.health_spin.setValue(19.25)
        window.appearance_tab.model_combo.setCurrentIndex(window.appearance_tab.model_combo.findData(1))
        window.inventory_tab.wider_pockets_checkbox.setChecked(True)

        def edit_item(dialog):
            dialog.crafter_name_input.setText("Pending crafter")
            dialog.apply_button.click()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            return dialog.result()

        with patch.object(ItemEditDialog, "exec", edit_item):
            window.inventory_tab.edit_slot_item(window.inventory_tab.slots[2, 1])
        skills = window.skills_tab
        row = next(i for i in range(skills.table.rowCount())
                   if skills.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == 1)
        skills.table.cellWidget(row, 1).setValue(18.5)
        snapshot = deepcopy((window.root_save, window.player_data))
        revision = window.current_revision
        label = window.file_label.text()
        pending = (window.character_tab.loaded_name_text, window.inventory_tab._loaded_rows)

        self.export("")
        self.assertFalse(self.json_file.exists())
        with patch("ui.mainWindow.atomic_write", side_effect=OSError("synthetic failing write")):
            self.export()
        self.assertFalse(self.json_file.exists())
        self.assertIn("synthetic failing write", self.critical.call_args.args[2])

        self.export()
        self.assertEqual((window.root_save, window.player_data), snapshot)
        self.assertEqual((window.character_tab.loaded_name_text, window.inventory_tab._loaded_rows), pending)
        self.assertEqual(window.current_revision, revision)
        self.assertEqual(window.file_label.text(), label)
        self.assertEqual(self.source.read_bytes(), original)
        self.information.assert_called_once()
        compile_fch(self.json_file, self.compiled)
        expected = nested_wire(34, 110, health=19.25, model=1, crafter="Pending crafter") + suffix
        expected = expected.replace(strings("unique"), strings("unique", "invrows 5", "invslot1"), 1)
        expected = expected.replace(struct.pack("<iiiff", 2, 1, 1, 12.5, 7.25),
                                    struct.pack("<iiiff", 2, 1, 1, 18.5, 7.25), 1)
        self.assertEqual(self.compiled.read_bytes(), profile_wire(expected, name="Pending Viking", worlds=worlds))

    def test_raw_only_and_identical_pair_supported_conflicts_require_explicit_choice(self):
        child = nested_wire(33, 109)
        original = profile_wire(child, version=46)
        data = parse_fch(original)
        self.json_file.write_bytes(character_json(data))
        compile_fch(self.json_file, self.compiled)
        self.assertEqual(self.compiled.read_bytes(), original)
        data["player_data"] = unpack_player_data_hex(data["player_data_hex"])
        compile_data = lambda: compile_fch(self.json_file, self.compiled)
        self.json_file.write_bytes(character_json(data))
        compile_data()
        self.assertEqual(self.compiled.read_bytes(), original)
        data["player_data"]["health"] = 77.0
        self.json_file.write_bytes(character_json(data))
        with self.assertRaisesRegex(ValueError, "disagree.*Remove player_data_hex"):
            compile_data()
        cli_error = io.StringIO()
        with redirect_stderr(cli_error):
            self.assertEqual(main(["pack", str(self.json_file), str(self.compiled)]), 1)
        self.assertIn("Remove player_data_hex", cli_error.getvalue())
        self.assertEqual(self.compiled.read_bytes(), original)
        del data["player_data_hex"]
        self.json_file.write_bytes(character_json(data))
        compile_data()
        self.assertEqual(self.compiled.read_bytes(), profile_wire(nested_wire(33, 109, health=77.0), version=46))

    def test_duplicate_json_keys_rejected_without_replacing_destination(self):
        self.compiled.write_bytes(profile_wire(nested_wire(34, 110)))
        original = self.compiled.read_bytes()
        self.json_file.write_text('{"player_data":{"health":15,"health":20}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key 'health'"):
            compile_fch(self.json_file, self.compiled)
        self.assertEqual(self.compiled.read_bytes(), original)
