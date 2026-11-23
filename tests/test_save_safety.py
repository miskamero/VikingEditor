from contextlib import nullcontext
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch

from tests.test_editor import QtTestCase
from PySide6.QtWidgets import QFileDialog, QMessageBox
from subscripts.fchUtil import decompile_fch, write_fch
from ui.backupManagerDialog import BackupManagerDialog
from ui.mainWindow import MainWindow


class SaveSafetyTests(QtTestCase):
    def setUp(self):
        super().setUp()
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.backups = self.directory / "backups"
        config = {"is_first_launch": False, "backup_dir": str(self.backups), "auto_backup": False}
        with patch("ui.mainWindow.load_config", return_value=config), \
             patch("ui.mainWindow.is_valheim_running", return_value=False), \
             patch.object(MainWindow, "check_valheim_installation", return_value=False):
            self.window = self.widget(MainWindow)
        self.critical = self.enter_patch(patch.object(QMessageBox, "critical"))
        self.question.return_value = QMessageBox.Yes
        self.source = self.directory / "Source.fch"
        self.target = self.directory / "Target.fch"
        write_fch(self.root, self.source)
        write_fch(dict(self.root, character_name="Target"), self.target)
        self.original = self.target.read_bytes()
        self.assertTrue(self.window.load_file(str(self.source)))

    def enter_patch(self, mock):
        result = mock.start()
        self.addCleanup(mock.stop)
        return result

    def save_as(self, path):
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.window.save_save_file()

    def test_save_as_protects_destination_and_respects_source_backup_setting(self):
        source_bytes = self.source.read_bytes()
        for enabled in (False, True):
            with self.subTest(auto_backup=enabled):
                self.window.config["auto_backup"] = enabled
                before = set(self.backups.rglob("*.fch"))
                self.target.write_bytes(self.original)
                self.window.load_file(str(self.source))
                self.save_as(self.target)
                self.assertEqual(decompile_fch(self.target)["character_name"], self.root["character_name"])
                self.assertEqual(self.source.read_bytes(), source_bytes)
                self.assertEqual(self.target.read_bytes(), source_bytes)
                copies = set(self.backups.rglob("*.fch")) - before
                expected = [("Target", self.original)]
                if enabled:
                    expected.append((self.root["character_name"], source_bytes))
                self.assertCountEqual([(p.parent.name, p.read_bytes()) for p in copies], expected)
                self.assertEqual(self.window.current_fch, str(self.target))
        self.critical.assert_not_called()

    def test_normal_save_with_backups_disabled_and_new_destination(self):
        self.window.character_tab.name_input.setText("First edit")
        self.save_as(self.source)
        first = self.source.read_bytes()
        self.assertEqual(decompile_fch(self.source)["character_name"], "First edit")
        new = self.directory / "New.fch"
        self.window.character_tab.name_input.setText("Second edit")
        self.save_as(new)
        self.assertEqual(decompile_fch(new)["character_name"], "Second edit")
        self.assertEqual(self.window.current_fch, str(new))
        self.assertEqual(self.source.read_bytes(), first)
        self.assertFalse(list(self.backups.rglob("*.fch")))
        self.critical.assert_not_called()

    def test_retention_preserves_newest_and_protected_files(self):
        folder = self.backups / "Target"
        folder.mkdir(parents=True)
        paths = [folder / f"{i}.fch" for i in range(5)]
        for i, path in enumerate(paths):
            path.write_bytes(bytes([i]))
            os.utime(path, (10000 + i, 10000 + i))
        self.window.config["max_backups_per_character"] = 0
        self.window.cleanup_old_backups("Target")
        self.assertEqual(set(folder.iterdir()), set(paths))
        self.window.config["max_backups_per_character"] = 2
        self.window.cleanup_old_backups("Target", {paths[0].resolve()})
        self.assertEqual(set(folder.iterdir()), {paths[0], paths[3], paths[4]})
        for i in (0, 3, 4):
            self.assertEqual(paths[i].read_bytes(), bytes([i]))

    def test_save_as_failure_preserves_destination_and_document_identity(self):
        def partial_output(**kwargs):
            staged = NamedTemporaryFile(**kwargs)
            write = staged.write

            def fail_after_prefix(contents):
                write(contents[:8])
                raise OSError("partial write")

            staged.write = fail_after_prefix
            return staged

        source_bytes = self.source.read_bytes()
        for failure in ("backup", "write", "sync", "replace"):
            with self.subTest(failure=failure):
                before = set(self.backups.rglob("*.fch"))
                if failure == "backup":
                    fault = patch("ui.mainWindow.os.fsync", side_effect=OSError("backup failure"))
                elif failure == "write":
                    fault = patch("subscripts.fchUtil.tempfile.NamedTemporaryFile", partial_output)
                elif failure == "sync":
                    # First sync the safety copy, then fail while flushing the temporary save.
                    fault = patch("subscripts.fchUtil.os.fsync", side_effect=[None, OSError("write failure")])
                else:
                    fault = patch("subscripts.fchUtil.os.replace", side_effect=OSError("replace failure"))
                with fault:
                    self.save_as(self.target)
                self.critical.assert_called_once()
                self.critical.reset_mock()
                self.assertEqual(self.target.read_bytes(), self.original)
                self.assertEqual(self.source.read_bytes(), source_bytes)
                self.assertEqual(self.window.current_fch, str(self.source))
                self.assertEqual(set(self.directory.iterdir()), {self.target, self.source, self.backups})
                created = set(self.backups.rglob("*.fch")) - before
                self.assertEqual([p.read_bytes() for p in created], [] if failure == "backup" else [self.original])

    def test_checksum_mismatch_rejected_on_open_and_on_overwrite(self):
        corrupt = self.original[:-1] + bytes([self.original[-1] ^ 1])
        self.target.write_bytes(corrupt)
        self.assertFalse(self.window.load_file(str(self.target)))
        self.assertIn("checksum mismatch", self.critical.call_args.args[2])
        self.assertEqual(self.window.current_fch, str(self.source))
        self.critical.reset_mock()
        self.save_as(self.target)
        self.critical.assert_called_once()
        self.assertIn("checksum mismatch", self.critical.call_args.args[2])
        self.assertEqual(self.target.read_bytes(), corrupt)
        # The file can also change after a successful open, with automatic backups disabled.
        self.source.write_bytes(corrupt)
        self.critical.reset_mock()
        self.save_as(self.source)
        self.critical.assert_called_once()
        self.assertIn("checksum mismatch", self.critical.call_args.args[2])
        self.assertEqual(self.source.read_bytes(), corrupt)

    def test_restore_destinations_preserve_bytes_across_failures_and_cleanup_warning(self):
        selected = self.directory / "Target_2026-01-01_123456.fch"
        write_fch(dict(self.root, character_name="Restored"), selected)
        contents = selected.read_bytes()
        loaded_original = self.source.read_bytes()
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        self.enter_patch(patch.object(dialog, "get_selected_backup", return_value=selected))
        self.enter_patch(patch("ui.backupManagerDialog.get_valheim_character_save_directory",
                               return_value=self.directory))
        for restore in (dialog.restore_backup, dialog.restore_to_valheim):
            for failure in ("checksum", "backup", "write", "replace", "retention", None):
                with self.subTest(restore=restore.__name__, failure=failure):
                    self.source.write_bytes(loaded_original)
                    self.target.write_bytes(self.original)
                    self.window.load_file(str(self.source))
                    current = restore == dialog.restore_backup
                    destination = self.source if current else self.target
                    original = loaded_original if current else self.original
                    before = set(self.backups.rglob("*.fch"))
                    selected.write_bytes(contents if failure != "checksum" else
                                         contents[:-1] + bytes([contents[-1] ^ 1]))
                    self.critical.reset_mock()
                    self.information.reset_mock()
                    if failure == "backup":
                        fault = patch.object(self.window, "create_backup", side_effect=OSError("backup failed"))
                    elif failure == "write":
                        fault = patch("subscripts.fchUtil.os.fsync", side_effect=[None, OSError("write failed")])
                    elif failure == "replace":
                        fault = patch("subscripts.fchUtil.os.replace", side_effect=OSError("replace failed"))
                    elif failure == "retention":
                        fault = patch.object(self.window, "cleanup_old_backups", side_effect=OSError("cleanup failed"))
                    else:
                        fault = nullcontext()
                    with fault:
                        restore()
                    self.assertEqual(self.window.current_fch, str(self.source))
                    untouched = self.target if current else self.source
                    self.assertEqual(untouched.read_bytes(), self.original if current else loaded_original)
                    if failure in ("checksum", "backup", "write", "replace"):
                        self.assertEqual(destination.read_bytes(), original)
                        self.critical.assert_called_once()
                        if failure == "checksum":
                            self.assertIn("checksum mismatch", self.critical.call_args.args[2])
                    else:
                        self.critical.assert_not_called()
                        self.assertEqual(destination.read_bytes(), contents)
                        self.assertEqual(self.window.root_save["character_name"],
                                         "Restored" if current else self.root["character_name"])
                        created = set(self.backups.rglob("*.fch")) - before
                        self.assertEqual([p.read_bytes() for p in created], [original])
                        if failure == "retention":
                            self.assertIn("cleanup failed", self.information.call_args.args[2])

    def test_restore_requires_confirmation_to_replace_damaged_destination_and_keeps_copy(self):
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        damaged = self.original[:-1] + bytes([self.original[-1] ^ 1])
        self.target.write_bytes(damaged)
        self.question.return_value = QMessageBox.No
        dialog.restore_file(self.source, self.target)
        self.assertIn("checksum mismatch", self.question.call_args.args[2])
        self.assertEqual(self.target.read_bytes(), damaged)
        self.assertFalse(list(self.backups.rglob("*.fch")))
        self.question.return_value = QMessageBox.Yes
        dialog.restore_file(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual([p.read_bytes() for p in self.backups.rglob("*.fch")], [damaged])

    def test_restore_to_new_destination_copies_opaque_bytes_verbatim(self):
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        destination = self.directory / "new" / "Restored.fch"
        original = self.source.read_bytes() + b"opaque extension"
        self.source.write_bytes(original)
        dialog.restore_file(self.source, destination)
        self.assertEqual(destination.read_bytes(), original)
        self.assertFalse(list(self.backups.rglob("*.fch")))
        self.critical.assert_not_called()

    def test_failed_reload_after_restore_cannot_save_stale_form(self):
        self.window.load_file(str(self.target))
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        with patch.object(self.window, "load_file", return_value=False):
            dialog.restore_file(self.source, self.target)
        self.assertFalse(self.window.btn_save_save.isEnabled())
        self.assertIsNone(self.window.current_fch)
        self.assertIsNone(self.window.root_save)
