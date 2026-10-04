import json
import os
import shutil
import sys
from datetime import datetime

from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QThread, Signal
from pathlib import Path

from ui.settingsDialog import SettingsDialog
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
    save_valheim_path,
    load_config,
    save_config,
    get_valheim_character_save_directory
)

from subscripts.fchUtil import (
    decompile_fch,
    compile_fch
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

        # check editor conf
        self.config = load_config()
        save_config(self.config)


        # valheim check, nöfnöf
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
        self.loaded_backup = False

        self.setWindowTitle("Viking Editor")
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)

        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        help_menu = menu_bar.addMenu("Help")

        new_character_action = file_menu.addAction("New Character...")
        open_save_action = file_menu.addAction("Open Save File")
        open_json_action = file_menu.addAction("Open JSON")
        close_json_action = file_menu.addAction("Close JSON")
        backup_manager_action = file_menu.addAction("Manage Backups...")
        export_json_action = file_menu.addAction("Export Decompiled JSON...")

        file_menu.addSeparator()

        file_menu.addSeparator()

        self.update_items_action = file_menu.addAction("Update Item Database")
        settings_action = file_menu.addAction("Settings")

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        about_action = help_menu.addAction("About Viking Editor")

        new_character_action.triggered.connect(self.new_character)
        open_save_action.triggered.connect(self.open_save_file)
        open_json_action.triggered.connect(self.open_json_file)
        backup_manager_action.triggered.connect(self.show_backup_manager)
        export_json_action.triggered.connect(self.export_decompiled_json)

        self.update_items_action.triggered.connect(self.update_item_database)
        settings_action.triggered.connect(self.show_settings)

        exit_action.triggered.connect(self.close)

        about_action.triggered.connect(self.show_about)

        main_layout = QVBoxLayout(central)

        button_layout = QHBoxLayout()

        self.btn_open_save = QPushButton("Open Save")
        self.btn_save_save = QPushButton("Save Savefile")

        button_layout.addWidget(self.btn_open_save)
        button_layout.addWidget(self.btn_save_save)

        main_layout.addLayout(button_layout)

        self.file_label = QLabel("No file loaded")
        main_layout.addWidget(self.file_label)

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
        self.tabs.addTab(self.stats_tab, "Stats")
        self.tabs.addTab(self.appearance_tab, "Appearance")
        self.tabs.addTab(self.progress_tab, "Progress")
        self.tabs.addTab(self.statistics_tab, "Statistics")

        self.tabs.addTab(self.character_tab, "Character")
        self.tabs.addTab(self.worlds_tab, "Worlds")

        self.btn_open_save.clicked.connect(self.open_save_file)
        self.btn_save_save.clicked.connect(self.save_save_file)

        self.check_valheim_installation()
        self.check_item_database()

        if self.config.get("is_first_launch", True):
            self.show_about()
            self.config["is_first_launch"] = False
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

    def create_backup(self, filename):
        backup_root = self.get_backup_directory()

        character_name = self.root_save.get(
            "character_name",
            "Viking"
        ).strip()

        if not character_name:
            character_name = "Viking"

        character_backup_dir = backup_root / character_name
        character_backup_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H%M%S"
        )

        backup_filename = (
            f"{character_name}_{timestamp}.fch"
        )

        backup_path = character_backup_dir / backup_filename

        shutil.copy2(filename, backup_path)

        return backup_path

    def cleanup_old_backups(self, character_name):
        max_backups = self.config.get(
            "max_backups_per_character",
            15
        )

        if max_backups == 0:
            return

        backup_dir = self.get_backup_directory() / character_name

        if not backup_dir.is_dir():
            return

        backups = sorted(
            backup_dir.glob("*.fch"),
            key=lambda path: path.stat().st_mtime,
            reverse=True
        )

        for old_backup in backups[max_backups:]:
            old_backup.unlink()

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
            save_valheim_path(valheim_dir)
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

        save_valheim_path(valheim_dir)

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

    def load_backup_file(self, filename):
        try:
            self.root_save = decompile_fch(str(filename))
            self.loaded_backup = True

            player_hex = self.root_save.get("player_data_hex")

            if not player_hex:
                QMessageBox.warning(
                    self,
                    "Empty Backup",
                    "The backup contains no player data."
                )
                return False

            self.player_data = unpack_player_data_hex(player_hex)

            self.inventory_tab.load_data(self.player_data)
            self.skills_tab.load_data(self.player_data)
            self.stats_tab.load_data(
                self.player_data,
                self.root_save
            )
            self.appearance_tab.load_data(self.player_data)
            self.progress_tab.load_data(self.player_data)
            self.statistics_tab.load_data(self.player_data, self.root_save)

            self.character_tab.load_data(
                self.player_data,
                self.root_save
            )

            self.worlds_tab.load_data(
                self.root_save
            )

            self.file_label.setText(
                f"Loaded Backup: {os.path.basename(filename)} "
                f"(Char: {self.root_save.get('character_name')})"
            )

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading Backup",
                f"Failed to load backup:\n\n{str(e)}"
            )
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
            self.root_save = create_new_character(
                character_name
            )

            player_hex = self.root_save.get(
                "player_data_hex"
            )

            if not player_hex:
                raise ValueError(
                    "The generated character contains no player data."
                )

            self.player_data = unpack_player_data_hex(
                player_hex
            )

            self.current_fch = None
            self.loaded_backup = False

            self.inventory_tab.load_data(
                self.player_data
            )

            self.skills_tab.load_data(
                self.player_data
            )

            self.stats_tab.load_data(
                self.player_data,
                self.root_save
            )

            self.appearance_tab.load_data(
                self.player_data
            )

            self.progress_tab.load_data(
                self.player_data
            )

            self.statistics_tab.load_data(
                self.player_data,
                self.root_save
            )

            self.character_tab.load_data(
                self.player_data,
                self.root_save
            )

            self.worlds_tab.load_data(
                self.root_save
            )

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
            self.root_save = None
            self.player_data = None
            self.current_fch = None
            self.loaded_backup = False

            QMessageBox.critical(
                self,
                "New Character Error",
                f"Could not create the new character:\n\n{e}"
            )

    def last_save_dir(self) -> str:
        remembered = self.config.get("last_save_dir", "").strip()

        if remembered and Path(remembered).is_dir():
            return remembered

        return str(get_valheim_character_save_directory())

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

        self.remember_save_dir(filename)

        try:
            # 1. Unpack container
            self.root_save = decompile_fch(filename)
            self.current_fch = filename
            self.loaded_backup = False

            # 2. Extract nested player hex bytes
            player_hex = self.root_save.get("player_data_hex")
            if player_hex:
                # 3. Unpack inner structures
                self.player_data = unpack_player_data_hex(player_hex)
                self.inventory_tab.load_data(self.player_data)
                self.skills_tab.load_data(self.player_data)
                self.stats_tab.load_data(self.player_data, self.root_save)
                self.appearance_tab.load_data(self.player_data)
                self.progress_tab.load_data(self.player_data)
                self.statistics_tab.load_data(self.player_data, self.root_save)
                self.character_tab.load_data(self.player_data, self.root_save)
                self.worlds_tab.load_data(self.root_save)
                
                self.file_label.setText(f"Loaded Save: {os.path.basename(filename)} (Char: {self.root_save.get('character_name')})")
                QMessageBox.information(self, "Success", "Valheim Save decompiled and loaded successfully!")
            else:
                QMessageBox.warning(self, "Empty Save", "The save container was read, but it contains no player data.")

        except Exception as e:
            QMessageBox.critical(self, "Error loading save", f"Failed to parse file:\n{str(e)}")

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

    def open_json_file(self):
        # filename, _ = QFileDialog.getOpenFileName(
        #     self, "Open unpacked character data", "", "JSON Files (*.json)"
        # )
        # if not filename:
        #     return

        # try:
        #     with open(filename, "r", encoding="utf-8") as f:
        #         self.player_data = json.load(f)

        #     self.inventory_tab.load_data(self.player_data)
        #     self.file_label.setText(f"Loaded JSON: {os.path.basename(filename)}")
        #     QMessageBox.information(self, "Success", "Character JSON loaded successfully!")
        # except Exception as e:
        #     QMessageBox.critical(self, "Error", f"Failed to open JSON:\n{str(e)}")
        QMessageBox.information(self, "Feature WIP", "Opening JSON files is currently a work in progress and not yet implemented.")

    def save_json_file(self):
        # if not self.player_data:
        #     QMessageBox.warning(self, "Save Aborted", "No active character data loaded to write.")
        #     return

        # filename, _ = QFileDialog.getSaveFileName(
        #     self, "Save Unpacked Character Data", "playerdata_edited.json", "JSON Files (*.json)"
        # )
        # if not filename:
        #     return

        # try:
        #     # 1. Collect all changes from the active tabs
        #     self.inventory_tab.save_changes()
        #     self.skills_tab.save_changes()
        #     self.stats_tab.save_changes()
        #     self.appearance_tab.save_changes()
        #     self.misc_tab.save_changes()

        #     # 2. Write straight to JSON
        #     with open(filename, "w", encoding="utf-8") as f:
        #         json.dump(self.player_data, f, indent=4, ensure_ascii=False)
                
        #     QMessageBox.information(self, "Success", f"Data exported cleanly to:\n{filename}")
        # except Exception as e:
        #     QMessageBox.critical(self, "Error", f"Could not write JSON:\n{str(e)}")
        QMessageBox.information(self, "Feature WIP", "Saving to JSON files is currently a work in progress and not yet implemented.")

    def save_save_file(self):
        """Packs the active inner data, updates the fch container, and re-compiles the file."""
        if not self.root_save or not self.player_data:
            QMessageBox.warning(self, "No Save Loaded", "Please load a valid .fch save file first.")
            return

        try:
            # 1. collect all changes from the active tabs
            self.inventory_tab.save_changes() # ?
            self.skills_tab.save_changes()
            self.stats_tab.save_changes()
            self.appearance_tab.save_changes()
            self.character_tab.save_changes()

            # 2. update
            char_name = self.root_save.get("character_name", "Viking").strip()
            
            # filename: lowercase name + .fch
            if self.loaded_backup:
                suggested_filename = f"{char_name.lower()}_restored.fch"
            else:
                suggested_filename = f"{char_name.lower()}.fch"

            default_dir = (
                os.path.dirname(self.current_fch)
                if getattr(self, "current_fch", None)
                else ""
            )

            default_save_path = os.path.join(
                default_dir,
                suggested_filename
            )

            # 3. open save dialog
            filename, _ = QFileDialog.getSaveFileName(
                self, 
                "Compile and Sign Valheim Save", 
                default_save_path, 
                "Valheim Character (*.fch)"
            )
            if not filename:
                return

            if self.config.get("auto_backup", True):
                if self.current_fch and os.path.isfile(self.current_fch):
                    backup_path = self.create_backup(self.current_fch)

                    character_name = self.root_save.get(
                        "character_name",
                        "Viking"
                    ).strip()

                    if not character_name:
                        character_name = "Viking"

                    self.cleanup_old_backups(character_name)

            # 4. encode the player data back into hex and update the container
            updated_hex_payload = pack_player_data_hex(self.player_data)
            self.root_save["player_data_hex"] = updated_hex_payload

            # 5. temp file to hold the wrapper JSON for the compiler
            temp_wrapper_path = filename + ".tmp_wrapper.json"
            with open(temp_wrapper_path, "w", encoding="utf-8") as f:
                json.dump(self.root_save, f, indent=4, ensure_ascii=False)

            # compile and "sign" the .fch file (he said "sign" hahah, idiotic)
            compile_fch(temp_wrapper_path, filename)
            if os.path.exists(temp_wrapper_path):
                os.remove(temp_wrapper_path)

            backup_message = (
                f"Backup created:\n{backup_path}"
                if "backup_path" in locals()
                else "No backup was created."
            )

            QMessageBox.information(
                self,
                "Success",
                f"Character save compiled, signed, and saved successfully!\n\n"
                f"Location:\n{filename}\n\n"
                f"{backup_message}"
            )

            # QMessageBox.information(
            #     self, "Debug Info",
            #     f"Model Index: {self.player_data.get('model_index')}\n"
            #     f"Hair Style: {repr(self.player_data.get('hair'))}\n"
            #     f"Beard Style: {repr(self.player_data.get('beard'))}\n"
            #     f"Skin Color: {self.player_data.get('skin_color')}\n"
            #     f"Hair Color: {self.player_data.get('hair_color')}\n"
            #     f"Character Name: {self.root_save.get('character_name')}\n"
            # )
            
            self.current_fch = filename
            self.loaded_backup = False

        except Exception as e:
            if 'temp_wrapper_path' in locals() and os.path.exists(temp_wrapper_path):
                os.remove(temp_wrapper_path)
            QMessageBox.critical(self, "Compilation Error", f"Failed to repack and sign the .fch file:\n{str(e)}")
