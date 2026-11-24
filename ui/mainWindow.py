import hashlib
import os
import sys
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmapCache
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
    atomic_write,
    character_json,
    encode_fch,
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
    completed = Signal(object)
    error = Signal(str)

    def __init__(self, valheim_dir, parent):
        super().__init__(parent)
        self.valheim_dir = valheim_dir
        self.cancel_requested = False

    def run(self):
        try:
            item_database = scan_item_database(
                self.valheim_dir,
                progress_callback=self.update_progress,
                cancel_callback=self.is_cancelled
            )

            self.completed.emit(item_database)

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
        self.saved_digest = None
        self.item_database_worker = None
        self.item_database_progress = None

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

        new_character_action = file_menu.addAction("New Blank Character...")
        open_save_action = file_menu.addAction("Open Save File")
        backup_manager_action = file_menu.addAction("Manage Backups...")
        export_json_action = file_menu.addAction("Export Character JSON...")

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

        self.tabs, tab_widgets = self.create_character_tabs()
        self.__dict__.update(tab_widgets)
        main_layout.addWidget(self.tabs)

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
                "Select an installation with Unity asset bundles in "
                "valheim_Data/StreamingAssets/SoftRef/Bundles."
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
        if self.item_database_worker is not None:
            return
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

        worker = self.item_database_worker = ItemDatabaseWorker(valheim_dir, self)
        self.item_database_progress = progress
        worker.progress.connect(self.catalog_progress)
        worker.completed.connect(self.catalog_updated)
        worker.error.connect(self.catalog_update_error)
        worker.finished.connect(self.catalog_worker_finished)
        progress.canceled.connect(self.cancel_catalog_update)
        worker.start()

    @Slot(int, int, str)
    def catalog_progress(self, current, total, message):
        if not self.item_database_worker.cancel_requested:
            self.item_database_progress.setLabelText(message)
            if total > 0:
                self.item_database_progress.setValue(int(current / total * 100))

    @Slot()
    def cancel_catalog_update(self):
        if self.item_database_worker is None:
            return
        self.item_database_worker.cancel()
        self.item_database_progress.setLabelText("Cancelling item database update...")
        self.item_database_progress.setCancelButton(None)

    def refresh_item_catalog(self, item_database):
        reload_item_database(item_database)
        load_item_icons.cache_clear()
        QPixmapCache.clear()
        self.inventory_tab.refresh_item_catalog()

    @Slot(object)
    def catalog_updated(self, item_database):
        self.item_database_progress.hide()
        if item_database is not None:
            self.refresh_item_catalog(item_database)
            QMessageBox.information(self, "Item Database Updated",
                                    f"Updated the item catalog with {len(item_database)} Valheim items.")

    @Slot(str)
    def catalog_update_error(self, message):
        self.item_database_progress.hide()
        QMessageBox.critical(self, "Item Database Error", f"Could not update the Valheim item database.\n\n{message}")

    @Slot()
    def catalog_worker_finished(self):
        self.item_database_progress.deleteLater()
        self.item_database_worker.deleteLater()
        self.item_database_progress = self.item_database_worker = None
        self.update_items_action.setEnabled(True)

    def clear_document(self):
        if self.root_save is not None:
            self.replace_character_tabs(*self.create_character_tabs())
        self.btn_save_save.setEnabled(False)
        self.tabs.setEnabled(False)
        self.root_save = self.player_data = self.current_fch = None
        self.current_revision = None
        self.saved_digest = None
        self.loaded_backup = False
        self.file_label.setText("No file loaded")

    @staticmethod
    def create_character_tabs():
        tabs = QTabWidget()
        widgets = {}
        for attribute, title, widget_type in (
            ("inventory_tab", "Inventory", InventoryTab), ("skills_tab", "Skills", SkillsTab),
            ("stats_tab", "Vitals", StatsTab), ("appearance_tab", "Appearance", AppearanceTab),
            ("progress_tab", "Progress", ProgressTab), ("statistics_tab", "Statistics", StatisticsTab),
            ("character_tab", "Character", CharacterTab), ("worlds_tab", "Worlds", WorldsTab),
        ):
            widget = widget_type()
            widgets[attribute] = widget
            tabs.addTab(widget, title)
        return tabs, widgets

    def prepare_character(self, root):
        payload = root.get("player_data_hex")
        data = None if payload is None else unpack_player_data_hex(payload)
        tabs, widgets = self.create_character_tabs()
        try:
            if data is None:
                for attribute in ("inventory_tab", "skills_tab", "stats_tab", "appearance_tab", "progress_tab"):
                    tabs.setTabEnabled(tabs.indexOf(widgets[attribute]), False)
                widgets["character_tab"].name_input.setReadOnly(True)
            else:
                widgets["inventory_tab"].load_data(data, root)
                widgets["skills_tab"].load_data(data)
                widgets["stats_tab"].load_data(data, root)
                widgets["appearance_tab"].load_data(data)
                widgets["progress_tab"].load_data(data)
            widgets["statistics_tab"].load_data(data, root)
            widgets["character_tab"].load_data(data, root)
            widgets["worlds_tab"].load_data(root)
        except Exception:
            tabs.deleteLater()
            raise
        return tabs, widgets, root, data

    def replace_character_tabs(self, tabs, widgets):
        previous = self.tabs
        index = previous.currentIndex()
        if tabs.isTabEnabled(index):
            tabs.setCurrentIndex(index)
        else:
            tabs.setCurrentWidget(widgets["character_tab"])
        self.centralWidget().layout().replaceWidget(previous, tabs)
        previous.hide()
        previous.deleteLater()
        self.tabs = tabs
        self.__dict__.update(widgets)

    def install_character(self, prepared, filename=None, backup=False, *, revision=None):
        tabs, widgets, root, data = prepared
        self.replace_character_tabs(tabs, widgets)
        self.root_save, self.player_data = root, data
        self.current_fch = None if backup else filename
        self.current_revision = None if backup else revision
        self.saved_digest = revision.digest if revision is not None else None
        self.loaded_backup = backup
        self.btn_save_save.setEnabled(data is not None)
        if filename is None:
            label = f"New Blank Character: {root['character_name']}"
        else:
            kind = "Backup" if backup else "Save"
            label = f"Loaded {kind}: {Path(filename).name} (Char: {root['character_name']})"
        if data is None:
            label += " — Profile only (no player payload). Metadata and JSON export are available."
        self.file_label.setText(label)

    def load_file(self, filename, backup=False, *, expected_revision=None):
        prepared = None
        try:
            snapshot = read_file_snapshot(filename)
            if expected_revision is not None:
                require_revision(filename, snapshot, expected_revision)
            if snapshot is None:
                raise FileNotFoundError(filename)
            root = parse_fch(snapshot.contents, validate_player=False)
            prepared = self.prepare_character(root)
            previous_revision = self.current_revision
            if not self.confirm_document_transition("opening the selected character"):
                return False
            if (self.current_revision != previous_revision and self.current_fch
                    and Path(self.current_fch).resolve() == Path(filename).resolve()):
                # Save As can target the file we are about to open.
                snapshot = require_destination_revision(filename, self.current_revision)
                prepared[0].deleteLater()
                prepared = None
                prepared = self.prepare_character(parse_fch(snapshot.contents, validate_player=False))
            else:
                require_destination_revision(filename, snapshot.revision)
            self.install_character(prepared, filename, backup, revision=snapshot.revision)
            prepared = None
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Error Loading Character", str(exc))
            return False
        finally:
            if prepared is not None:
                prepared[0].deleteLater()

    def new_character(self):
        character_name, ok = QInputDialog.getText(
            self,
            "New Blank Character",
            "Character name\n\nThis template starts with an empty inventory, a generated seed, "
            "and the first-spawn intro flag off.",
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
            prepared = self.prepare_character(create_new_character(character_name))
            if not self.confirm_document_transition("creating a blank character"):
                prepared[0].deleteLater()
                return
            self.install_character(prepared)

            QMessageBox.information(
                self,
                "New Blank Character",
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

    def character_snapshot(self, *, report_errors=True, reset_blocked_resize=False):
        root_save = dict(self.root_save)
        root_save.pop("player_data_hex", None)
        if self.player_data is None:
            return dict(root_save, player_data=None)
        # Collectors replace fields on these copies. Inventory records keep
        # their identity in the live grid when a successful save commits them.
        player_data = dict(self.player_data)
        if not self.character_tab.save_changes(player_data, root_save, report_errors=report_errors):
            return None
        if not self.inventory_tab.save_changes(player_data, report_errors=report_errors,
                                               reset_blocked_resize=reset_blocked_resize):
            return None
        self.skills_tab.save_changes(player_data)
        self.stats_tab.save_changes(player_data, root_save)
        self.appearance_tab.save_changes(player_data)
        player_data.pop("character_name", None)  # The outer profile stores the name.
        return dict(root_save, player_data=player_data)

    def has_unsaved_changes(self):
        if self.player_data is None:
            return False
        if self.saved_digest is None:
            return True
        try:
            snapshot = self.character_snapshot(report_errors=False)
            return snapshot is None or hashlib.sha256(encode_fch(snapshot)).hexdigest() != self.saved_digest
        except (ValueError, EOFError, OSError, TypeError):
            return True

    def confirm_document_transition(self, action, *, protected_path=None):
        if not self.has_unsaved_changes():
            return True
        save_hint = "\n\nSave will ask for a separate file." if protected_path is not None else ""
        choice = QMessageBox.question(
            self, "Unsaved Character Changes", f"Save your changes before {action}?{save_hint}",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if choice == QMessageBox.Save:
            return self.save_save_file(protected_path=protected_path)
        return choice == QMessageBox.Discard

    def closeEvent(self, event):
        if self.item_database_worker is not None:
            self.cancel_catalog_update()
            event.ignore()
            return
        if self.confirm_document_transition("closing VikingEditor"):
            super().closeEvent(event)
        else:
            event.ignore()

    def export_decompiled_json(self):
        if not self.root_save:
            QMessageBox.warning(self, "No Save Loaded", "Please load a Valheim character save first.")
            return

        char_name = self.character_tab.name_input.text().strip() or "Viking"
        default_filename = str(Path(self.last_save_dir()) / f"{char_name}_decompiled.json")
        filename, _ = QFileDialog.getSaveFileName(self, "Export Character JSON", default_filename,
                                                  "JSON Files (*.json)")
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() != ".json" or is_steam_cloud_path(path):
                raise ValueError("Choose a .json file outside Steam Cloud storage.")
            if self.current_fch:
                original = Path(self.current_fch)
                if path.resolve() == original.resolve() or (path.exists() and original.exists()
                                                             and path.samefile(original)):
                    raise ValueError("Choose a JSON file separate from the character save.")
            destination = read_file_snapshot(path)
            export_data = self.character_snapshot()
            if export_data is None:
                return
            encode_fch(export_data)
            atomic_write(path, character_json(export_data), destination)
            QMessageBox.information(self, "JSON Exported", f"Exported current character edits to {path}.")
        except (OSError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export the character JSON.\n\n{exc}")

    def is_current_document(self, path):
        return self.current_fch is not None and path.resolve() == Path(self.current_fch).resolve()

    def inspect_save_destination(self, destination):
        if is_steam_cloud_path(destination):
            raise ValueError("Choose a save destination outside Steam Cloud storage.")
        if self.is_current_document(destination):
            return require_destination_revision(destination, self.current_revision)
        snapshot = read_file_snapshot(destination)
        if snapshot and self.current_revision:
            revision = snapshot.revision
            current = self.current_revision
            if revision.inode and (revision.device, revision.inode) == (current.device, current.inode):
                require_revision(destination, snapshot, current)
        return snapshot

    def save_save_file(self, *, protected_path=None):
        if self.player_data is None:
            QMessageBox.warning(self, "Character Editing Unavailable", "Open a character with player data to use Save As.")
            return False

        try:
            root = self.character_snapshot(reset_blocked_resize=True)
            if root is None:
                return False
            player = root.pop("player_data")
            root["player_data_hex"] = pack_player_data_hex(player)
            char_name = root["character_name"].strip()
            suffix = "_edited" if protected_path is not None else "_restored" if self.loaded_backup else ""
            suggested_filename = f"{char_name.lower()}{suffix}.fch"

            default_dir = (
                os.path.dirname(self.current_fch)
                if self.current_fch and not is_steam_cloud_path(Path(self.current_fch))
                else self.last_save_dir()
            )

            default_save_path = os.path.join(
                default_dir,
                suggested_filename
            )

            while True:
                filename, _ = QFileDialog.getSaveFileName(
                    self, "Compile and Sign Valheim Save", default_save_path,
                    "Valheim Character (*.fch)", options=QFileDialog.Option.DontConfirmOverwrite,
                )
                if not filename:
                    return False
                destination = Path(filename)
                if protected_path is not None and destination.resolve() == protected_path.resolve():
                    QMessageBox.warning(self, "Choose a Separate File", "The restore will replace this file.")
                    continue
                try:
                    result = self.save_to_destination(destination, root)
                except RevisionConflict as exc:
                    if QMessageBox.warning(
                        self, "Save Conflict", f"{exc}\n\nSave to another destination?",
                        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
                    ) != QMessageBox.Yes:
                        return False
                    continue
                if result is None:
                    return False
                break

            self.root_save.update(root)
            self.player_data.update(player)
            self.character_tab.loaded_name_text = self.character_tab.name_input.text()
            self.inventory_tab.mark_saved()
            self.stats_tab.edits.clear()
            self.appearance_tab.edits.clear()
            self.saved_digest = self.current_revision.digest
            self.file_label.setText(f"Saved: {Path(filename).name} (Char: {char_name})")

            QMessageBox.information(
                self,
                "Success",
                f"Character save compiled, signed, and saved successfully!\n\n"
                f"Location:\n{filename}\n\n"
                f"{result}"
            )
            return True

        except Exception as e:
            QMessageBox.critical(self, "Compilation Error", f"Failed to repack and sign the .fch file:\n{str(e)}")
            return False

    def save_to_destination(self, destination, root):
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

        revision = write_fch(root, destination, destination=snapshot)
        self.current_fch = str(destination)
        self.current_revision = revision
        self.loaded_backup = False
        summary = self.backup_summary(backups, destination, source=source)
        if source_changed:
            summary += "\nThe original file changed externally and was left as-is."
        return summary
