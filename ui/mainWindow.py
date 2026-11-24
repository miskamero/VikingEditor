import json
import os
import sys
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QThread, Signal
from pathlib import Path

from ui.settingsDialog import SettingsDialog
from ui.theme import apply_theme
from ui.backupManagerDialog import BackupManagerDialog

from ui.inventoryTab import InventoryTab
from ui.skillsTab import SkillsTab
from ui.statsTab import StatsTab
from ui.appearanceTab import AppearanceTab
from ui.progressTab import ProgressTab
from ui.statisticsTab import StatisticsTab
from ui.characterTab import CharacterTab
from ui.worldsTab import WorldsTab

from data.info import INFO_TEXT

from ui.valheim_detection import (
    is_valheim_running,
    valheim_warning_message,
    find_valheim_installation,
    is_valid_valheim_installation,
    load_saved_valheim_path,
    load_config,
    save_config,
    get_valheim_character_save_directory,
    is_steam_cloud_path,
)

from subscripts.fchUtil import (
    parse_fch,
    read_file_snapshot,
    require_destination_revision,
    require_revision,
    RevisionConflict,
    verified_payload,
    write_fch
)
from subscripts.backupOwnership import (
    VALHEIM_SAVE_FOLDERS, managed_backups, plain_directory, remove_owned_backup, write_backup,
)

from subscripts.newCharacter import (
    create_new_character
)

from subscripts.playerDataUtil import (
    unpack_player_data_hex,
    pack_player_data_hex,
    reload_item_database
)

from subscripts.itemDatabase import (
    ITEM_DATABASE_PATH,
    load_item_icons,
    update_item_database as scan_item_database
)

class ItemDatabaseWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, valheim_dir):
        super().__init__()
        self.valheim_dir = valheim_dir
        self.cancel_requested = False

    def run(self):
        try:
            item_database = scan_item_database(
                self.valheim_dir,
                progress_callback=self.update_progress,
                cancel_callback=self.is_cancelled
            )

            self.finished.emit(item_database)

        except Exception as e:
            self.error.emit(str(e))

    def update_progress(self, current, total, message):
        self.progress.emit(current, total, message)

    def is_cancelled(self):
        return self.cancel_requested

    def cancel(self):
        self.cancel_requested = True

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config = load_config()
        dark = self.config.get("theme") == "dark"
        apply_theme(dark)

        if is_valheim_running():
            warning_msg = valheim_warning_message()
            msg = QMessageBox(self)
            msg.setWindowTitle("Valheim Running Warning")
            msg.setText(warning_msg)
            msg.setIcon(QMessageBox.Warning)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

        self.root_save = None       # Container data (.fch level dict)
        self.player_data = None     # Decoded character attributes dict
        self.current_fch = None
        self.current_revision = None
        self.loaded_backup = False

        self.setWindowTitle("Viking Editor")
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)

        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        view_menu = menu_bar.addMenu("View")
        self.dark_mode_action = view_menu.addAction("Dark Mode")
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(dark)
        self.dark_mode_action.toggled.connect(self.set_dark_mode)
        help_menu = menu_bar.addMenu("Help")

        new_character_action = file_menu.addAction("New Character...")
        open_save_action = file_menu.addAction("Open Save File")
        backup_manager_action = file_menu.addAction("Manage Backups...")
        export_json_action = file_menu.addAction("Export Decompiled JSON...")

        file_menu.addSeparator()

        self.update_items_action = file_menu.addAction("Update Item Database")
        settings_action = file_menu.addAction("Settings")

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        about_action = help_menu.addAction("About Viking Editor")

        new_character_action.triggered.connect(self.new_character)
        open_save_action.triggered.connect(self.open_save_file)
        backup_manager_action.triggered.connect(self.show_backup_manager)
        export_json_action.triggered.connect(self.export_decompiled_json)

        self.update_items_action.triggered.connect(self.update_item_database)
        settings_action.triggered.connect(self.show_settings)

        exit_action.triggered.connect(self.close)

        about_action.triggered.connect(self.show_about)

        main_layout = QVBoxLayout(central)

        button_layout = QHBoxLayout()

        self.btn_open_save = QPushButton("Open Save")
        self.btn_save_save = QPushButton("Save As...")

        button_layout.addWidget(self.btn_open_save)
        button_layout.addWidget(self.btn_save_save)

        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        button_layout.addWidget(self.file_label, 1)
        main_layout.addLayout(button_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.inventory_tab = InventoryTab()
        self.skills_tab = SkillsTab()
        self.stats_tab = StatsTab()
        self.appearance_tab = AppearanceTab()
        self.progress_tab = ProgressTab()
        self.statistics_tab = StatisticsTab()

        self.character_tab = CharacterTab()
        self.worlds_tab = WorldsTab()

        self.tabs.addTab(self.inventory_tab, "Inventory")
        self.tabs.addTab(self.skills_tab, "Skills")
        self.tabs.addTab(self.stats_tab, "Vitals")
        self.tabs.addTab(self.appearance_tab, "Appearance")
        self.tabs.addTab(self.progress_tab, "Progress")
        self.tabs.addTab(self.statistics_tab, "Statistics")

        self.tabs.addTab(self.character_tab, "Character")
        self.tabs.addTab(self.worlds_tab, "Worlds")

        self.btn_open_save.clicked.connect(self.open_save_file)
        self.btn_save_save.clicked.connect(self.save_save_file)

        self.btn_save_save.setEnabled(False)
        self.tabs.setEnabled(False)
        if self.check_valheim_installation():
            self.check_item_database()

        if self.config.get("is_first_launch", True):
            self.show_about()
            self.config["is_first_launch"] = False
            save_config(self.config)

    def set_dark_mode(self, enabled):
        apply_theme(enabled)
        self.config["theme"] = "dark" if enabled else "light"
        save_config(self.config)

    def get_backup_directory(self):
        backup_dir = self.config.get("backup_dir", "").strip()

        if backup_dir:
            return Path(backup_dir)

        if getattr(sys, "frozen", False):
            editor_dir = Path(sys.executable).resolve().parent
        else:
            editor_dir = Path(__file__).resolve().parent.parent

        return editor_dir / "backups"

    def create_backup(self, filename, character_name=None, *, allow_damaged=False, snapshot=None):
        backup_root = self.get_backup_directory()
        if is_steam_cloud_path(backup_root):
            raise ValueError("Choose a backup directory outside Steam Cloud storage.")

        if character_name is None:
            character_name = self.root_save.get("character_name", "Viking").strip()

        if not character_name:
            character_name = "Viking"

        if character_name in (".", "..") or Path(character_name).name != character_name:
            raise ValueError("Character name cannot be used as a backup folder.")

        # A shared root may be the Valheim data directory itself.
        group = f"Backup - {character_name}" if character_name.lower() in VALHEIM_SAVE_FOLDERS else character_name
        character_backup_dir = backup_root / group
        character_backup_dir.mkdir(
            parents=True,
            exist_ok=True
        )
        if not plain_directory(character_backup_dir):
            raise ValueError("The character backup directory must be a regular directory.")

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H%M%S%f"
        )

        backup_filename = (
            f"{group}_{timestamp}.fch"
        )

        backup_path = character_backup_dir / backup_filename

        snapshot = snapshot if snapshot is not None else read_file_snapshot(filename)
        if snapshot is None:
            raise RevisionConflict(filename)
        if not allow_damaged:
            verified_payload(snapshot.contents)
        write_backup(backup_path, snapshot.contents, Path(filename).name)

        return backup_path

    def cleanup_old_backups(self, character_name, protected=()):
        max_backups = self.config.get(
            "max_backups_per_character",
            15
        )

        if type(max_backups) is not int or max_backups < 0:
            raise ValueError("Invalid backup retention limit.")
        if max_backups == 0:
            return

        root = self.get_backup_directory()
        if is_steam_cloud_path(root):
            raise ValueError("Steam Cloud storage cannot be used for backup retention.")
        backups = sorted(
            managed_backups(root, root / character_name),
            key=lambda backup: backup[0].stat().st_mtime_ns,
            reverse=True
        )

        for old_backup, revision in backups[max_backups:]:
            if old_backup.resolve() not in protected:
                remove_owned_backup(root, old_backup, revision)

    def backup_summary(self, backups, destination, *, source=None):
        if not backups:
            return "No backup was created."
        message = "Recovery copies:\n" + "\n".join(map(str, backups))
        protected = {path.resolve() for path in backups}
        protected.add(Path(destination).resolve())
        if source is not None:
            protected.add(Path(source).resolve())
        for directory in {backup.parent for backup in backups}:
            try:
                self.cleanup_old_backups(directory.name, protected)
            except (OSError, ValueError) as exc:
                message += f"\nCould not remove old backups: {exc}"
        return message

    def show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("About Viking Editor")
        msg.setText(INFO_TEXT)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        msg.exec()

    def show_settings(self):
        dialog = SettingsDialog(self.config, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            self.config.update(settings)
            save_config(self.config)

    def show_backup_manager(self):
        dialog = BackupManagerDialog(
            self.get_backup_directory(),
            self
        )
        dialog.exec()

    def check_valheim_installation(self):
        valheim_dir = load_saved_valheim_path()

        if valheim_dir is not None:
            if is_valid_valheim_installation(valheim_dir):
                return True

        valheim_dir = find_valheim_installation()

        if valheim_dir is not None:
            self.config["valheim_dir"] = str(valheim_dir)
            save_config(self.config)
            return True

        choice = QMessageBox.question(
            self,
            "Valheim Installation Not Found",
            "The editor could not automatically find your Valheim installation.\n\n"
            "Would you like to select the Valheim installation folder manually?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if choice != QMessageBox.StandardButton.Yes:
            return False

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Valheim Installation Folder"
        )

        if not selected_dir:
            return False

        valheim_dir = Path(selected_dir)

        if not is_valid_valheim_installation(valheim_dir):
            QMessageBox.critical(
                self,
                "Invalid Valheim Installation",
                "The selected folder does not appear to be a valid "
                "Valheim installation.\n\n"
                "Please select the folder containing:\n"
                "valheim_Data\\StreamingAssets\\SoftRef\\Bundles"
            )
            return False

        self.config["valheim_dir"] = str(valheim_dir)
        save_config(self.config)

        return True

    def check_item_database(self):
        if ITEM_DATABASE_PATH.exists():
            return

        self.update_item_database()

    def update_item_database(self):
        valheim_dir = load_saved_valheim_path()

        if valheim_dir is None or not is_valid_valheim_installation(valheim_dir):
            if not self.check_valheim_installation():
                return

            valheim_dir = load_saved_valheim_path()

        if valheim_dir is None:
            return

        valheim_dir = Path(valheim_dir)

        self.update_items_action.setEnabled(False)

        progress = QProgressDialog(
            "Loading Valheim bundles...",
            None,
            0,
            100,
            self
        )

        progress.setWindowTitle("Updating Item Database")
        progress.setWindowModality(
            Qt.WindowModality.ApplicationModal
        )
        progress.setMinimumDuration(0)
        progress.setCancelButton(
            QPushButton("Cancel")
        )
        progress.setAutoClose(False)
        progress.show()

        worker = ItemDatabaseWorker(valheim_dir)

        def update_progress(current, total, message):
            progress.setLabelText(message)

            if total > 0:
                progress.setValue(
                    int(current / total * 100)
                )

        def cancel_update():
            worker.cancel()
            progress.setLabelText(
                "Cancelling item database update..."
            )
            progress.setCancelButton(None)

        def update_finished(item_database):
            progress.close()

            if item_database is None:
                self.update_items_action.setEnabled(True)
                return

            reload_item_database()
            from PySide6.QtGui import QPixmapCache
            load_item_icons.cache_clear()
            QPixmapCache.clear()
            for slot in self.inventory_tab.slots.values():
                slot.update_visuals()

            QMessageBox.information(
                self,
                "Item Database Updated",
                "Valheim item database updated successfully.\n\n"
                f"Valheim installation:\n{valheim_dir}\n\n"
                f"Items found: {len(item_database)}\n"
                f"Items with icons: {sum(any(icons) for icons in load_item_icons().values())}\n"
                f"Icon cache: {ITEM_DATABASE_PATH.parent / 'item_icons'}"
            )

            self.update_items_action.setEnabled(True)

            worker.deleteLater()

        def update_error(message):
            progress.close()

            QMessageBox.critical(
                self,
                "Item Database Error",
                "Could not update the Valheim item database:\n\n"
                f"{message}"
            )

            self.update_items_action.setEnabled(True)

            worker.deleteLater()

        worker.progress.connect(update_progress)
        worker.finished.connect(update_finished)
        worker.error.connect(update_error)

        progress.canceled.connect(cancel_update)

        worker.start()

    def clear_document(self):
        self.btn_save_save.setEnabled(False)
        self.tabs.setEnabled(False)
        self.root_save = self.player_data = self.current_fch = None
        self.current_revision = None
        self.loaded_backup = False
        self.file_label.setText("No file loaded")

    def load_character(self, root, filename=None, backup=False, *, revision=None):
        payload = root.get("player_data_hex")
        if not payload:
            raise ValueError("This character contains no player data.")
        data = unpack_player_data_hex(payload)
        # A tab can reject malformed data. Keep a partially loaded form unsavable.
        self.clear_document()
        self.inventory_tab.load_data(data, root)
        self.skills_tab.load_data(data)
        self.stats_tab.load_data(data, root)
        self.appearance_tab.load_data(data)
        self.progress_tab.load_data(data)
        self.statistics_tab.load_data(data, root)
        self.character_tab.load_data(data, root)
        self.worlds_tab.load_data(root)
        self.root_save, self.player_data = root, data
        self.current_fch = None if backup else filename
        self.current_revision = None if backup else revision
        self.loaded_backup = backup
        self.tabs.setEnabled(True)
        self.btn_save_save.setEnabled(True)

    def load_file(self, filename, backup=False, *, expected_revision=None):
        try:
            snapshot = read_file_snapshot(filename)
            if expected_revision is not None:
                require_revision(filename, snapshot, expected_revision)
            if snapshot is None:
                raise FileNotFoundError(filename)
            self.load_character(parse_fch(snapshot.contents), filename, backup, revision=snapshot.revision)
            kind = "Backup" if backup else "Save"
            self.file_label.setText(
                f"Loaded {kind}: {Path(filename).name} (Char: {self.root_save.get('character_name')})"
            )
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Error Loading Character", str(exc))
            return False

    def new_character(self):
        character_name, ok = QInputDialog.getText(
            self,
            "New Character",
            "Character name:",
            QLineEdit.EchoMode.Normal,
            "New Viking"
        )

        if not ok:
            return

        character_name = character_name.strip()

        if not character_name:
            QMessageBox.warning(
                self,
                "Invalid Character Name",
                "Please enter a character name."
            )
            return

        try:
            self.load_character(create_new_character(character_name))
            self.file_label.setText(
                f"New Character: {character_name}"
            )

            QMessageBox.information(
                self,
                "New Character",
                f"New character created successfully!\n\n"
                f"Character: {character_name}\n"
                f"Player ID: {self.root_save['player_id']}\n\n"
                f"The character has not been saved to disk yet."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "New Character Error",
                f"Could not create the new character:\n\n{e}"
            )

    def last_save_dir(self) -> str:
        remembered = self.config.get("last_save_dir", "").strip()

        if remembered and Path(remembered).is_dir() and not is_steam_cloud_path(Path(remembered)):
            return remembered

        local = get_valheim_character_save_directory()
        return str(next((path for path in (local, *local.parents) if path.is_dir()), Path.home()))

    def remember_save_dir(self, filename):
        self.config["last_save_dir"] = str(Path(filename).parent)

        save_config(self.config)

    def open_save_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Valheim Character Save",
            self.last_save_dir(),
            "Valheim Character (*.fch)"
        )
        if not filename:
            return

        if self.load_file(filename):
            self.remember_save_dir(filename)

    def export_decompiled_json(self):
        if not self.root_save:
            QMessageBox.warning(
                self,
                "No Save Loaded",
                "Please load a Valheim character save first."
            )
            return

        char_name = self.root_save.get(
            "character_name",
            "Viking"
        ).strip()

        if not char_name:
            char_name = "Viking"

        default_filename = str(
            Path(self.last_save_dir()) / f"{char_name}_decompiled.json"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Decompiled JSON",
            default_filename,
            "JSON Files (*.json)"
        )

        if not filename:
            return

        self.remember_save_dir(filename)

        try:
            export_data = dict(self.root_save)

            if export_data.get("player_data_hex"):
                export_data["player_data"] = unpack_player_data_hex(
                    export_data["player_data_hex"]
                )
            else:
                export_data["player_data"] = None

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    export_data,
                    f,
                    indent=4,
                    ensure_ascii=False
                )

            QMessageBox.information(
                self,
                "JSON Exported",
                "The save was decompiled successfully.\n\n"
                f"JSON file:\n{filename}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                "Could not export the decompiled save:\n\n"
                f"{e}"
            )

    def inspect_save_destination(self, destination):
        if is_steam_cloud_path(destination):
            raise ValueError("Choose a save destination outside Steam Cloud storage.")
        if self.current_fch and destination.resolve() == Path(self.current_fch).resolve():
            return require_destination_revision(destination, self.current_revision)
        snapshot = read_file_snapshot(destination)
        if snapshot and self.current_revision:
            revision = snapshot.revision
            current = self.current_revision
            if revision.inode and (revision.device, revision.inode) == (current.device, current.inode):
                require_revision(destination, snapshot, current)
        return snapshot

    def save_save_file(self):
        """Packs the active inner data, updates the fch container, and re-compiles the file."""
        if not self.root_save or not self.player_data:
            QMessageBox.warning(self, "No Save Loaded", "Please load a valid .fch save file first.")
            return

        try:
            # 1. collect all changes from the active tabs
            if not self.character_tab.save_changes():
                return
            if not self.inventory_tab.save_changes():
                return
            self.skills_tab.save_changes()
            self.stats_tab.save_changes()
            self.appearance_tab.save_changes()

            # 2. update
            char_name = self.root_save.get("character_name", "Viking").strip()
            
            # filename: lowercase name + .fch
            if self.loaded_backup:
                suggested_filename = f"{char_name.lower()}_restored.fch"
            else:
                suggested_filename = f"{char_name.lower()}.fch"

            default_dir = (
                os.path.dirname(self.current_fch)
                if self.current_fch and not is_steam_cloud_path(Path(self.current_fch))
                else self.last_save_dir()
            )

            default_save_path = os.path.join(
                default_dir,
                suggested_filename
            )

            payload = pack_player_data_hex(self.player_data)
            while True:
                filename, _ = QFileDialog.getSaveFileName(
                    self, "Compile and Sign Valheim Save", default_save_path,
                    "Valheim Character (*.fch)", options=QFileDialog.Option.DontConfirmOverwrite,
                )
                if not filename:
                    return
                try:
                    result = self.save_to_destination(Path(filename), payload)
                except RevisionConflict as exc:
                    if QMessageBox.warning(
                        self, "Save Conflict", f"{exc}\n\nSave to another destination?",
                        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
                    ) != QMessageBox.Yes:
                        return
                    continue
                if result is None:
                    return
                break

            self.file_label.setText(f"Saved: {Path(filename).name} (Char: {char_name})")

            QMessageBox.information(
                self,
                "Success",
                f"Character save compiled, signed, and saved successfully!\n\n"
                f"Location:\n{filename}\n\n"
                f"{result}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Compilation Error", f"Failed to repack and sign the .fch file:\n{str(e)}")

    def save_to_destination(self, destination, payload):
        snapshot = self.inspect_save_destination(destination)
        if snapshot is not None:
            answer = QMessageBox.question(
                self, "Overwrite Character Save?",
                f"Replace this character save?\n\n{destination.absolute()}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return None

        source = Path(self.current_fch) if self.current_fch else None
        same_destination = source is not None and source.resolve() == destination.resolve()
        auto_backup = self.config.get("auto_backup", True)
        backups = []
        source_changed = False
        if source and auto_backup and not same_destination:
            try:
                source_snapshot = require_destination_revision(source, self.current_revision)
            except RevisionConflict:
                source_changed = True
            else:
                backups.append(self.create_backup(source, snapshot=source_snapshot))
        if snapshot is not None and (auto_backup or not same_destination):
            name = None if same_destination else destination.stem
            backups.append(self.create_backup(destination, name, snapshot=snapshot))

        revision = write_fch(dict(self.root_save, player_data_hex=payload), destination, destination=snapshot)
        self.root_save["player_data_hex"] = payload
        self.current_fch = str(destination)
        self.current_revision = revision
        self.loaded_backup = False
        summary = self.backup_summary(backups, destination, source=source)
        if source_changed:
            summary += "\nThe original file changed externally and was left as-is."
        return summary
