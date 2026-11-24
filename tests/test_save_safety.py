from contextlib import nullcontext
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import patch

from tests.test_editor import QtTestCase
from PySide6.QtWidgets import QFileDialog, QMessageBox
from subscripts.backupOwnership import owned_backup, ownership_path
from subscripts.fchUtil import decompile_fch, read_file_snapshot, write_fch
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
        paths = [self.window.create_backup(self.target, "Target") for _ in range(5)]
        for i, path in enumerate(paths):
            os.utime(path, (10000 + i, 10000 + i))
        unrelated = folder / "unrelated.fch"
        unrelated.write_bytes(self.original)
        os.utime(unrelated, (1, 1))
        self.window.config["max_backups_per_character"] = 0
        self.window.cleanup_old_backups("Target")
        self.assertEqual(set(folder.glob("*.fch")), {*paths, unrelated})
        self.window.config["max_backups_per_character"] = 1
        self.window.cleanup_old_backups("Target", {paths[0].resolve()})
        self.assertEqual(set(folder.glob("*.fch")), {paths[0], paths[4], unrelated})
        self.assertEqual(set(folder.glob("*.json")), {ownership_path(paths[0]), ownership_path(paths[4])})
        for retained in (paths[0], paths[4], unrelated):
            self.assertEqual(retained.read_bytes(), self.original)

    def test_save_as_failure_preserves_destination_and_document_identity(self):
        def partial_output(**kwargs):
            staged = NamedTemporaryFile(**kwargs)
            if Path(kwargs["dir"]) != self.directory:
                return staged
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
                    fault = patch("subscripts.fchUtil.os.fsync", side_effect=[None, None, OSError("write failure")])
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
        self.critical.assert_not_called()
        self.assertIn("changed", self.warning.call_args.args[2])
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
                        fault = patch("subscripts.fchUtil.os.fsync", side_effect=[None, None, OSError("write failed")])
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
        self.question.return_value = QMessageBox.No
        dialog.restore_file(self.source, destination)
        self.assertFalse(destination.exists())
        self.assertIn("passed checksum verification", self.question.call_args.args[2])
        self.assertIn(str(destination), self.question.call_args.args[2])
        self.assertEqual(self.question.call_args.args[-1], QMessageBox.No)
        self.question.return_value = QMessageBox.Yes
        dialog.restore_file(self.source, destination)
        self.assertEqual(destination.read_bytes(), original)
        self.assertFalse(list(self.backups.rglob("*.fch")))
        self.critical.assert_not_called()

    def test_checksum_valid_structural_failure_requires_archival_confirmation_and_clears_active_form(self):
        from tests.test_player_versions import wire_payload
        from tests.test_serialization_boundaries import profile_wire

        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        original = self.target.read_bytes()
        self.assertTrue(self.window.load_file(self.target))
        nested = wire_payload()[0]
        for archival, detail in ((profile_wire(nested[:-1]), "Nested player data:"),
                                 (profile_wire(nested, version=48), "Unsupported character profile version 48")):
            self.source.write_bytes(archival)
            self.question.return_value = QMessageBox.No
            dialog.restore_file(self.source, self.target)
            self.assertIn(detail, self.question.call_args.args[2])
            self.assertEqual(self.target.read_bytes(), original)
            self.assertTrue(self.window.btn_save_save.isEnabled())
        self.question.return_value = QMessageBox.Yes
        dialog.restore_file(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), archival)
        self.assertEqual([copy.read_bytes() for copy in self.backups.rglob("*.fch")], [original])
        self.assertIsNone(self.window.root_save)
        self.assertFalse(self.window.btn_save_save.isEnabled())
        self.assertIn("restored verbatim", self.information.call_args.args[2])

    def test_failed_reload_after_restore_cannot_save_stale_form(self):
        self.window.load_file(str(self.target))
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        with patch.object(self.window, "load_file", return_value=False):
            dialog.restore_file(self.source, self.target)
        self.assertFalse(self.window.btn_save_save.isEnabled())
        self.assertIsNone(self.window.current_fch)
        self.assertIsNone(self.window.root_save)

    def test_external_valid_replacement_survives_with_or_without_backup(self):
        for enabled in (False, True):
            with self.subTest(auto_backup=enabled):
                self.assertTrue(self.window.load_file(str(self.source)))
                self.window.config["auto_backup"] = enabled
                snapshot = self.window.current_revision
                before = self.source.stat()
                # Keep size and mtime identical so only the revision check can detect this.
                current_name = decompile_fch(self.source)["character_name"]
                external_name = "A" * len(current_name) if current_name[0] != "A" else "B" * len(current_name)
                write_fch(dict(self.root, character_name=external_name), self.source)
                os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
                external = self.source.read_bytes()
                self.assertEqual(len(external), before.st_size)
                self.save_as(self.source)
                self.assertEqual(self.source.read_bytes(), external)
                self.assertEqual(self.window.current_revision, snapshot)
                self.assertEqual(self.warning.call_args.args[1], "Save Conflict")
                self.assertFalse(list(self.backups.rglob("*.fch")))
        self.critical.assert_not_called()

    def test_external_deletion_and_byte_identical_replacement_conflict(self):
        original = self.source.read_bytes()
        twin = self.directory / "Twin.fch"
        twin.write_bytes(original)
        self.source.unlink()
        self.save_as(self.source)
        self.assertFalse(self.source.exists())
        self.assertEqual(self.warning.call_args.args[1], "Save Conflict")
        twin.replace(self.source)
        self.save_as(self.source)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.warning.call_count, 2)
        self.information.assert_not_called()

    def test_successful_saves_update_revision_and_can_repeat(self):
        self.window.config["auto_backup"] = True
        previous = self.source.read_bytes()
        for name in ("First revision", "Second revision"):
            self.window.character_tab.name_input.setText(name)
            before = set(self.backups.rglob("*.fch"))
            self.save_as(self.source)
            self.assertEqual(self.window.current_revision, read_file_snapshot(self.source).revision)
            created = set(self.backups.rglob("*.fch")) - before
            self.assertEqual([p.read_bytes() for p in created], [previous])
            self.assertEqual(decompile_fch(self.source)["character_name"], name)
            previous = self.source.read_bytes()
        self.warning.assert_not_called()

    def test_save_as_detects_change_during_explicit_overwrite_confirmation(self):
        newer = self.source.read_bytes()
        def change_target(*args):
            self.target.write_bytes(newer)
            return QMessageBox.Yes

        self.question.side_effect = change_target
        self.save_as(self.target)
        self.assertEqual(self.target.read_bytes(), newer)
        self.assertEqual([p.read_bytes() for p in self.backups.rglob("*.fch")], [self.original])
        self.assertEqual(self.warning.call_args.args[1], "Save Conflict")
        self.assertEqual(self.window.current_fch, str(self.source))

    def test_recheck_occurs_after_staging_and_fsync(self):
        fsync = os.fsync
        newer = self.target.read_bytes()
        def change_after_sync(fd):
            fsync(fd)
            self.source.write_bytes(newer)

        with patch("subscripts.fchUtil.os.fsync", side_effect=change_after_sync):
            self.save_as(self.source)
        self.assertEqual(self.source.read_bytes(), newer)
        self.assertEqual(self.warning.call_args.args[1], "Save Conflict")

    def test_new_destination_cannot_clobber_file_appearing_during_publish(self):
        destination = self.directory / "New.fch"
        publish_name = "rename" if os.name == "nt" else "link"
        publish = getattr(os, publish_name)
        newer = self.target.read_bytes()
        def create_before_publish(staged, target):
            Path(target).write_bytes(newer)
            publish(staged, target)

        with patch(f"subscripts.fchUtil.os.{publish_name}", side_effect=create_before_publish):
            self.save_as(destination)
        self.assertEqual(destination.read_bytes(), newer)
        self.assertEqual(self.warning.call_args.args[1], "Save Conflict")

    def test_conflict_can_save_to_a_different_file(self):
        newer = self.target.read_bytes()
        self.source.write_bytes(newer)
        alternative = self.directory / "Alternate.fch"
        self.window.config["auto_backup"] = True
        self.warning.return_value = QMessageBox.Yes
        with patch.object(QFileDialog, "getSaveFileName",
                          side_effect=[(str(self.source), ""), (str(alternative), "")]):
            self.window.save_save_file()
        self.assertEqual(self.source.read_bytes(), newer)
        self.assertEqual(self.window.current_revision, read_file_snapshot(alternative).revision)
        self.assertEqual(decompile_fch(alternative)["character_name"], self.root["character_name"])
        self.assertFalse(list(self.backups.rglob("*.fch")))

    def test_save_and_restore_recheck_after_backup_creation(self):
        for operation in ("save", "restore"):
            with self.subTest(operation=operation):
                self.target.write_bytes(self.original)
                self.assertTrue(self.window.load_file(str(self.target)))
                self.window.config["auto_backup"] = True
                backup = self.window.create_backup
                newer = self.source.read_bytes()
                before = set(self.backups.rglob("*.fch"))
                def create_then_change(*args, **kwargs):
                    result = backup(*args, **kwargs)
                    self.target.write_bytes(newer)
                    return result

                with patch.object(self.window, "create_backup", side_effect=create_then_change):
                    if operation == "save":
                        self.save_as(self.target)
                    else:
                        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
                        dialog.restore_file(self.source, self.target)
                created = set(self.backups.rglob("*.fch")) - before
                self.assertEqual([p.read_bytes() for p in created], [self.original])
                self.assertEqual(self.target.read_bytes(), newer)
                self.assertIn("Conflict", self.warning.call_args.args[1])

    def test_restore_to_loaded_file_checks_revision_and_can_retry_elsewhere(self):
        newer = self.target.read_bytes()
        self.source.write_bytes(newer)
        copy = self.directory / "restored.fch"
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        dialog.restore_file(self.target, self.source)
        self.assertEqual(self.source.read_bytes(), newer)
        self.assertEqual(self.warning.call_args.args[1], "Restore Conflict")
        self.assertFalse(list(self.backups.rglob("*.fch")))
        self.warning.return_value = QMessageBox.Yes
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(copy), "")):
            dialog.restore_file(self.target, self.source)
        self.assertEqual(copy.read_bytes(), self.original)
        self.assertEqual(self.source.read_bytes(), newer)

    def test_stale_or_corrupt_ownership_never_confers_deletion_rights(self):
        variants = ("missing", "malformed", "wrong digest", "replaced", "wrong source")
        retained = []
        for variant in variants:
            with self.subTest(variant=variant):
                path = self.window.create_backup(self.target, "Target")
                marker = ownership_path(path)
                if variant == "missing":
                    marker.unlink()
                elif variant == "malformed":
                    marker.write_text("{", encoding="utf-8")
                elif variant == "replaced":
                    twin = self.directory / "twin.fch"
                    twin.write_bytes(self.original)
                    twin.replace(path)
                else:
                    data = json.loads(marker.read_text(encoding="utf-8"))
                    data.update({"sha256": "0"} if variant == "wrong digest" else {"source": "../Target.fch"})
                    marker.write_text(json.dumps(data), encoding="utf-8")
                self.assertIsNone(owned_backup(self.backups, path))
                retained.append(path)
        latest = self.window.create_backup(self.target, "Target")
        self.window.config["max_backups_per_character"] = 1
        self.window.cleanup_old_backups("Target")
        self.assertTrue(all(p.read_bytes() == self.original for p in [latest, *retained]))

    def test_manager_individual_and_bulk_delete_only_managed_backups(self):
        first = self.window.create_backup(self.target, "Target")
        second = self.window.create_backup(self.target, "Target")
        historical = first.parent / "Target_2025-01-01_010203.fch"
        historical.write_bytes(self.original)
        unrelated = first.parent / "unrelated.fch"
        unrelated.write_bytes(self.original)
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        for path in (unrelated, historical, first):
            with patch.object(dialog, "get_selected_backup", return_value=path):
                dialog.delete_backup()
        self.assertFalse(first.exists())
        self.assertFalse(ownership_path(first).exists())
        self.assertEqual(dialog.backup_list.count(), 2)
        dialog.character_filter.setCurrentIndex(dialog.character_filter.findData("Target"))
        dialog.delete_all_backups()
        self.assertFalse(second.exists())
        self.assertEqual(historical.read_bytes(), self.original)
        self.assertEqual(unrelated.read_bytes(), self.original)
        restored = self.directory / "historical-restored.fch"
        dialog.restore_file(historical, restored)
        self.assertEqual(restored.read_bytes(), self.original)

    def test_marker_write_failure_leaves_original_and_unmanaged_recovery_intact(self):
        with patch("subscripts.fchUtil.os.fsync", side_effect=[None, OSError("marker failed")]):
            self.save_as(self.target)
        self.assertEqual(self.target.read_bytes(), self.original)
        recovery, = self.backups.rglob("*.fch")
        self.assertEqual(recovery.read_bytes(), self.original)
        self.assertIsNone(owned_backup(self.backups, recovery))
        self.assertIn("marker failed", self.critical.call_args.args[2])

    def test_restore_does_not_prune_the_selected_backup(self):
        selected = self.window.create_backup(self.source, self.target.stem)
        original = selected.read_bytes()
        os.utime(selected, (1, 1))
        self.window.config["max_backups_per_character"] = 1
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        dialog.restore_file(selected, self.target)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(selected.read_bytes(), original)
        recovery, = set(selected.parent.glob("*.fch")) - {selected}
        self.assertEqual(recovery.read_bytes(), self.original)

    def test_real_save_directories_under_backup_root_are_never_managed_groups(self):
        saves_root = self.directory / "Valheim"
        self.window.config["backup_dir"] = str(saves_root)
        current = saves_root / "characters_local" / "characters_local_2025-01-01_010101.fch"
        legacy = saves_root / "characters" / "Source.fch"
        for path in (current, legacy):
            path.parent.mkdir(parents=True)
            path.write_bytes(self.original)
        self.window.config["max_backups_per_character"] = 1
        for name in ("characters", "characters_local"):
            self.window.cleanup_old_backups(name)
        dialog = self.widget(BackupManagerDialog, saves_root, self.window)
        self.assertEqual(dialog.backup_list.count(), 0)
        self.assertEqual(dialog.character_filter.count(), 1)
        self.assertFalse(dialog.delete_all_button.isEnabled())
        for path in (legacy, current):
            with patch.object(dialog, "get_selected_backup", return_value=path):
                dialog.delete_backup()
            self.assertEqual(path.read_bytes(), self.original)
        collision = self.window.create_backup(self.target, "characters_local")
        self.assertNotEqual(collision.parent, current.parent)
        self.assertIsNotNone(owned_backup(saves_root, collision))

    def test_delete_checks_ownership_again_after_confirmation(self):
        backup = self.window.create_backup(self.target, "Target")
        replacement = self.directory / "replacement.fch"
        replacement.write_bytes(self.original)
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        def replace_before_delete(*args):
            replacement.replace(backup)
            return QMessageBox.Yes

        self.question.side_effect = replace_before_delete
        with patch.object(dialog, "get_selected_backup", return_value=backup):
            dialog.delete_backup()
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertIn("file was kept", self.critical.call_args.args[2])

    def test_direct_restore_uses_original_filename_and_confirms_current_local_path(self):
        profile = self.directory / "Windows profile"
        base = profile / "AppData" / "LocalLow" / "IronGate" / "Valheim"
        legacy = base / "characters" / self.target.name
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(self.source.read_bytes())
        local = base / "characters_local" / self.target.name
        selected = self.window.create_backup(self.target, "Display Name")
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        with patch.dict(os.environ, {"USERPROFILE": str(profile)}), \
             patch("ui.valheim_detection.sys.platform", "win32"), \
             patch.object(dialog, "get_selected_backup", return_value=selected):
            self.question.return_value = QMessageBox.No
            dialog.restore_to_valheim()
            self.assertIn(str(local), self.question.call_args.args[2])
            self.assertFalse(local.parent.exists())
            self.question.return_value = QMessageBox.Yes
            dialog.restore_to_valheim()
        self.assertEqual(local.read_bytes(), self.original)
        self.assertEqual(legacy.read_bytes(), self.source.read_bytes())
        self.assertIn(str(local), self.information.call_args.args[2])

    def test_explicit_legacy_location_can_be_opened_and_restored(self):
        legacy = self.directory / "characters" / "legacy.fch"
        legacy.parent.mkdir()
        legacy.write_bytes(self.source.read_bytes())
        self.window.config["last_save_dir"] = str(legacy.parent)
        self.assertEqual(self.window.last_save_dir(), str(legacy.parent))
        self.assertTrue(self.window.load_file(str(legacy)))
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        with patch.object(dialog, "get_selected_backup", return_value=self.target):
            dialog.restore_backup()
        self.assertEqual(legacy.read_bytes(), self.original)
        self.assertEqual(self.window.current_revision, read_file_snapshot(legacy).revision)

    def test_default_browser_uses_local_folder_or_existing_parent(self):
        base = self.directory / "Valheim"
        legacy = base / "characters"
        legacy.mkdir(parents=True)
        local = base / "characters_local"
        self.window.config["last_save_dir"] = str(self.directory / "missing")
        with patch("ui.mainWindow.get_valheim_character_save_directory", return_value=local):
            self.assertEqual(self.window.last_save_dir(), str(base))
            local.mkdir()
            self.assertEqual(self.window.last_save_dir(), str(local))

    def test_save_and_restore_do_not_write_into_steam_cloud(self):
        cloud = self.directory / "Steam" / "userdata" / "123" / "892970" / "remote" / "characters"
        target = cloud / "Target.fch"
        self.save_as(target)
        dialog = self.widget(BackupManagerDialog, self.backups, self.window)
        dialog.restore_file(self.source, target)
        self.assertFalse(cloud.exists())
        self.assertEqual(self.critical.call_count, 2)
        for call in self.critical.call_args_list:
            self.assertIn("Steam Cloud", call.args[2])
