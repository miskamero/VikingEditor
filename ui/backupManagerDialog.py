from pathlib import Path
from subscripts.fchUtil import atomic_write, verified_payload

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
)
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from ui.theme import set_themed_style
from ui.valheim_detection import get_valheim_character_save_directory


class BackupManagerDialog(QDialog):
    def __init__(self, backup_directory, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Backup Manager")
        self.resize(800, 600)

        self.backup_directory = Path(backup_directory)
        self.main_window = parent

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Character"))

        self.character_filter = QComboBox()
        layout.addWidget(self.character_filter)

        layout.addWidget(QLabel("Character Backups"))

        self.backup_list = QListWidget()
        self.backup_list.setSpacing(4)

        self.character_filter.currentTextChanged.connect(
            self.filter_backups
        )

        layout.addWidget(self.backup_list)

        self.backup_info = QLabel(
            "Select a backup to view its details."
        )

        self.backup_info.setWordWrap(True)
        self.backup_info.setMinimumHeight(100)
        self.backup_info.setStyleSheet(
            "QLabel {"
            "  padding: 10px;"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(self.backup_info)

        button_layout = QHBoxLayout()

        self.open_button = QPushButton("Open Backup")
        self.restore_button = QPushButton("Restore to Loaded Save")
        self.restore_to_valheim_button = QPushButton("Restore to Valheim Saves")
        self.delete_button = QPushButton("Delete")
        self.delete_all_button = QPushButton("Delete Character Backups")
        self.open_folder_button = QPushButton("Open Backups Folder")
        self.refresh_button = QPushButton("Refresh")

        for button in (
            self.open_button,
            self.restore_button,
            self.restore_to_valheim_button,
            self.delete_button,
            self.delete_all_button,
            self.open_folder_button,
            self.refresh_button,
        ):
            button.setMinimumHeight(32)

        for button in (self.delete_button, self.delete_all_button):
            set_themed_style(button, "QPushButton:enabled { color: @danger@; }")

        button_layout.addWidget(self.open_button)

        button_layout.addWidget(self.restore_button)
        button_layout.addWidget(self.restore_to_valheim_button)

        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.delete_all_button)

        button_layout.addWidget(self.open_folder_button)
        button_layout.addWidget(self.refresh_button)

        layout.addLayout(button_layout)

        self.open_button.clicked.connect(self.open_backup)

        self.restore_button.clicked.connect(self.restore_backup)
        self.restore_to_valheim_button.clicked.connect(self.restore_to_valheim)

        self.delete_button.clicked.connect(self.delete_backup)
        self.delete_all_button.clicked.connect(
            self.delete_all_backups
        )

        self.open_folder_button.clicked.connect(self.open_backups_folder)
        self.refresh_button.clicked.connect(self.load_backups)

        self.backup_list.itemDoubleClicked.connect(
            lambda _: self.open_backup()
        )

        self.backup_list.currentItemChanged.connect(
            self.update_backup_info
        )

        self.update_backup_info(None, None)
        self.load_backups()

    def open_backups_folder(self):
        self.backup_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        # os.startfile is Windows-only; Qt picks the right file
        # manager on every platform.
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.backup_directory))
        )

    def filter_backups(self, character_name):
        self.backup_list.setCurrentRow(-1)
        self.delete_all_button.setEnabled(bool(character_name) and character_name != "All Characters")
        for index in range(self.backup_list.count()):
            item = self.backup_list.item(index)

            backup_path = Path(
                item.data(256)
            )

            if character_name == "All Characters":
                item.setHidden(False)
                continue

            item.setHidden(
                backup_path.parent.name != character_name
            )

    def load_backups(self):
        self.delete_all_button.setEnabled(False)
        self.backup_list.clear()
        self.character_filter.blockSignals(True)
        self.character_filter.clear()
        self.character_filter.addItem("All Characters")

        if not self.backup_directory.is_dir():
            self.character_filter.blockSignals(False)
            return

        character_names = []

        for character_dir in sorted(self.backup_directory.iterdir()):
            if not character_dir.is_dir():
                continue

            backups = sorted(
                character_dir.glob("*.fch"),
                key=lambda path: path.stat().st_mtime,
                reverse=True
            )

            if not backups:
                continue

            character_names.append(character_dir.name)

            for backup_file in backups:
                modified_time = backup_file.stat().st_mtime

                from datetime import datetime

                created_time = datetime.fromtimestamp(
                    modified_time
                ).strftime("%B %d, %Y %H:%M:%S")

                size = backup_file.stat().st_size

                if size < 1024:
                    size_text = f"{size} B"
                elif size < 1024 * 1024:
                    size_text = f"{size / 1024:.1f} KB"
                else:
                    size_text = f"{size / (1024 * 1024):.1f} MB"

                item = QListWidgetItem(
                    f"{character_dir.name}\n"
                    f"{created_time} · {size_text}"
                )

                item.setData(
                    256,
                    str(backup_file)
                )

                self.backup_list.addItem(item)

        self.character_filter.addItems(
            character_names
        )

        self.character_filter.blockSignals(False)

    def get_selected_backup(self):
        item = self.backup_list.currentItem()

        if item is None:
            QMessageBox.information(
                self,
                "No Backup Selected",
                "Please select a backup first."
            )
            return None

        return Path(item.data(256))

    def update_backup_info(self, current, previous):
        selected = current is not None
        for button in (self.open_button, self.restore_to_valheim_button, self.delete_button):
            button.setEnabled(selected)
        self.restore_button.setEnabled(bool(selected and self.main_window and self.main_window.current_fch))
        if current is None:
            self.backup_info.setText(
                "Select a backup to view its details."
            )
            return

        backup_path = Path(
            current.data(256)
        )

        if not backup_path.is_file():
            self.backup_info.setText(
                "The selected backup file no longer exists."
            )
            return

        from datetime import datetime

        character_name = backup_path.parent.name

        created_time = datetime.fromtimestamp(
            backup_path.stat().st_mtime
        ).strftime("%B %d, %Y %H:%M:%S")

        size = backup_path.stat().st_size

        if size < 1024:
            size_text = f"{size} B"
        elif size < 1024 * 1024:
            size_text = f"{size / 1024:.1f} KB"
        else:
            size_text = f"{size / (1024 * 1024):.1f} MB"

        self.backup_info.setText(
            f"<b>Selected Backup</b><br><br>"
            f"<b>Character:</b> {character_name}<br>"
            f"<b>Created:</b> {created_time}<br>"
            f"<b>Size:</b> {size_text}<br>"
            f"<b>Location:</b> {backup_path}"
        )

    def open_backup(self):
        backup_path = self.get_selected_backup()

        if backup_path is None:
            return

        if not backup_path.is_file():
            QMessageBox.warning(
                self,
                "Backup Not Found",
                "The selected backup file no longer exists."
            )
            self.load_backups()
            return

        answer = QMessageBox.question(
            self,
            "Open Backup",
            "Open this backup in Viking Editor?\n\n"
            f"{backup_path.name}\n\n"
            "The backup will be loaded for editing. "
            "Saving will create a new save file rather than "
            "modifying this backup directly.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        if self.main_window is None:
            return

        if not self.main_window.load_file(backup_path, backup=True):
            return

        self.accept()

    def restore_to_valheim(self):
        backup_path = self.get_selected_backup()

        if backup_path is None:
            return

        if not backup_path.is_file():
            QMessageBox.warning(
                self,
                "Backup Not Found",
                "The selected backup file no longer exists."
            )
            self.load_backups()
            return

        valheim_save_dir = get_valheim_character_save_directory()
        name = backup_path.stem

        timestamp_parts = name.rsplit("_", 2)

        if len(timestamp_parts) == 3:
            character_name = timestamp_parts[0]
        else:
            character_name = name

        target_path = valheim_save_dir / f"{character_name}.fch"

        if target_path.exists():
            answer = QMessageBox.question(
                self,
                "Overwrite Character Save?",
                "A character save with this name already exists.\n\n"
                f"{target_path.name}\n\n"
                "Do you want to overwrite it?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

        self.restore_file(backup_path, target_path)

    def restore_backup(self):
        backup_path = self.get_selected_backup()

        if backup_path is None:
            return

        if not backup_path.is_file():
            QMessageBox.warning(
                self,
                "Backup Not Found",
                "The selected backup file no longer exists."
            )
            self.load_backups()
            return

        if self.main_window is None:
            return

        current_fch = self.main_window.current_fch

        if not current_fch:
            QMessageBox.warning(
                self,
                "No Save Loaded",
                "Load a character save before restoring a backup."
            )
            return

        current_fch = Path(current_fch)

        answer = QMessageBox.question(
            self,
            "Restore Backup",
            "Are you sure you want to restore this backup?\n\n"
            f"Backup:\n{backup_path}\n\n"
            f"Target:\n{current_fch}\n\n"
            "The current save will be replaced.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.restore_file(backup_path, current_fch)

    def restore_file(self, backup_path, destination):
        backups = []
        try:
            contents = backup_path.read_bytes()
            verified_payload(contents)
            if destination.exists():
                if backup_path.samefile(destination):
                    raise ValueError("The selected backup is already the destination file.")
                try:
                    verified_payload(destination.read_bytes())
                except (ValueError, EOFError) as exc:
                    answer = QMessageBox.question(
                        self, "Damaged Destination",
                        f"{destination}\n\n{exc}\n\nKeep a recovery copy of this damaged file "
                        "and replace it with the selected backup?",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                    )
                    if answer != QMessageBox.Yes:
                        return
                backups.append(self.main_window.create_backup(destination, destination.stem, allow_damaged=True))
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(destination, contents)
        except (OSError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))
            return

        summary = self.main_window.backup_summary(backups, destination)
        QMessageBox.information(self, "Backup Restored", f"Restored:\n{destination}\n\n{summary}")
        loaded = self.main_window.current_fch
        if loaded and Path(loaded).resolve() == destination.resolve():
            if not self.main_window.load_file(str(destination)):
                self.main_window.clear_document()
        self.load_backups()

    def delete_backup(self):
        backup_path = self.get_selected_backup()

        if backup_path is None:
            return

        if not backup_path.is_file():
            QMessageBox.warning(
                self,
                "Backup Not Found",
                "The selected backup file no longer exists."
            )
            self.load_backups()
            return

        answer = QMessageBox.question(
            self,
            "Delete Backup",
            "Are you sure you want to permanently delete this backup?\n\n"
            f"{backup_path}",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            backup_path.unlink()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Delete Failed",
                "Could not delete the backup:\n\n"
                f"{e}"
            )
            return

        self.load_backups()

    def delete_all_backups(self):
        character_name = self.character_filter.currentText()

        if character_name == "All Characters":
            QMessageBox.information(
                self,
                "Select Character",
                "Please select a specific character first."
            )
            return

        character_dir = (
            self.backup_directory
            / character_name
        )

        if not character_dir.is_dir():
            QMessageBox.information(
                self,
                "No Backups",
                f"No backups were found for {character_name}."
            )
            return

        backups = list(
            character_dir.glob("*.fch")
        )

        if not backups:
            QMessageBox.information(
                self,
                "No Backups",
                f"No backups were found for {character_name}."
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete All Backups",
            f"Are you sure you want to permanently delete "
            f"all {len(backups)} backups for {character_name}?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            for backup in backups:
                backup.unlink()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Delete Failed",
                "Could not delete all backups:\n\n"
                f"{e}"
            )
            return

        QMessageBox.information(
            self,
            "Backups Deleted",
            f"All backups for {character_name} "
            "were deleted successfully."
        )

        self.load_backups()
