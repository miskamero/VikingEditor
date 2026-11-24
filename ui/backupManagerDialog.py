from datetime import datetime
from pathlib import Path
from subscripts.backupOwnership import (
    LEGACY_BACKUP, VALHEIM_SAVE_FOLDERS, managed_backups, owned_backup, plain_directory, remove_owned_backup,
)
from subscripts.fchUtil import atomic_write, read_file_snapshot, RevisionConflict, verified_payload

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from ui.theme import set_themed_style
from ui.valheim_detection import get_valheim_character_save_directory, is_steam_cloud_path


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

        self.character_filter.currentIndexChanged.connect(
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
        self.restore_to_valheim_button = QPushButton("Restore to Local Valheim")
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
        if is_steam_cloud_path(self.backup_directory):
            QMessageBox.warning(self, "Backup Location", "Choose a backup directory outside Steam Cloud storage.")
            return
        self.backup_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        # os.startfile is Windows-only; Qt picks the right file
        # manager on every platform.
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.backup_directory))
        )

    def filter_backups(self):
        group = self.character_filter.currentData()
        self.backup_list.setCurrentRow(-1)
        self.delete_all_button.setEnabled(isinstance(group, str))
        for index in range(self.backup_list.count()):
            item = self.backup_list.item(index)
            item.setHidden(group is not None and item.data(Qt.UserRole + 1) != group)

    def load_backups(self):
        self.delete_all_button.setEnabled(False)
        self.backup_list.clear()
        self.character_filter.blockSignals(True)
        self.character_filter.clear()
        self.character_filter.addItem("All Backups", None)
        try:
            if not self.backup_directory.is_dir() or is_steam_cloud_path(self.backup_directory):
                return
            groups = set()
            has_historical = False
            for directory in sorted(self.backup_directory.iterdir()):
                if directory.name.lower() in VALHEIM_SAVE_FOLDERS or not plain_directory(directory):
                    continue
                for path in sorted(directory.glob("*.fch"), reverse=True):
                    owned = owned_backup(self.backup_directory, path)
                    if owned:
                        group = directory.name
                        groups.add(group)
                    elif ((match := LEGACY_BACKUP.fullmatch(path.stem))
                          and match[1] == directory.name and path.is_file() and not path.is_symlink()):
                        group = False
                        has_historical = True
                    else:
                        continue
                    item = QListWidgetItem(f"{directory.name}\n{path.name}")
                    item.setData(Qt.UserRole, str(path))
                    item.setData(Qt.UserRole + 1, group)
                    self.backup_list.addItem(item)
            for group in sorted(groups):
                self.character_filter.addItem(group, group)
            if has_historical:
                self.character_filter.addItem("Historical or Unverified", False)
        except OSError as exc:
            QMessageBox.warning(self, "Backup Listing Failed", str(exc))
        finally:
            self.character_filter.blockSignals(False)

    def get_selected_backup(self):
        item = self.backup_list.currentItem()
        if item is None:
            QMessageBox.information(self, "No Backup Selected", "Please select a backup first.")
            return None
        return Path(item.data(Qt.UserRole))

    def update_backup_info(self, current, previous):
        path = Path(current.data(Qt.UserRole)) if current else None
        available = path is not None and path.is_file()
        owned = available and owned_backup(self.backup_directory, path) is not None
        self.open_button.setEnabled(available)
        self.restore_to_valheim_button.setEnabled(available)
        self.restore_button.setEnabled(bool(available and self.main_window and self.main_window.current_fch))
        self.delete_button.setEnabled(owned)
        if not available:
            self.backup_info.setText("Select an available backup to view its details.")
            return
        try:
            info = path.stat()
        except OSError as exc:
            self.backup_info.setText(str(exc))
            self.delete_button.setEnabled(False)
            return
        created = datetime.fromtimestamp(info.st_mtime).strftime("%B %d, %Y %H:%M:%S")
        status = "Managed backup" if owned else "Unverified ownership. Available for opening or restoring."
        self.backup_info.setTextFormat(Qt.PlainText)
        self.backup_info.setText(f"{status}\n{created}\n{info.st_size:,} bytes\n{path}")

    def open_backup(self):
        path = self.get_selected_backup()
        if path is None or self.main_window is None:
            return
        answer = QMessageBox.question(
            self, "Open Backup",
            f"Open this backup for editing?\n\n{path}\n\nSave As will suggest a separate file.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes and self.main_window.load_file(path, backup=True):
            self.accept()

    def restore_to_valheim(self):
        path = self.get_selected_backup()
        if path is None:
            return
        owned = owned_backup(self.backup_directory, path)
        if owned:
            filename = owned[1]
        else:
            historical = LEGACY_BACKUP.fullmatch(path.stem)
            filename = f"{historical[1]}.fch" if historical else path.name
        self.restore_file(path, get_valheim_character_save_directory() / filename)

    def restore_backup(self):
        path = self.get_selected_backup()
        if path is None or self.main_window is None:
            return
        if not self.main_window.current_fch:
            QMessageBox.warning(self, "No Save Loaded", "Load a character save before restoring a backup.")
            return
        self.restore_file(path, Path(self.main_window.current_fch))

    def restore_file(self, backup_path, destination):
        if self.main_window is None:
            return
        try:
            backup = read_file_snapshot(backup_path)
            if backup is None:
                raise FileNotFoundError(backup_path)
            verified_payload(backup.contents)
            while True:
                try:
                    result = self.restore_to_destination(backup_path, backup, destination)
                except RevisionConflict as exc:
                    if QMessageBox.warning(
                        self, "Restore Conflict", f"{exc}\n\nRestore to another destination?",
                        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
                    ) != QMessageBox.Yes:
                        return
                    filename, _ = QFileDialog.getSaveFileName(
                        self, "Restore Backup to Another File", str(destination),
                        "Valheim Character (*.fch)", options=QFileDialog.Option.DontConfirmOverwrite,
                    )
                    if not filename:
                        return
                    destination = Path(filename)
                    continue
                if result is None:
                    return
                revision, backups = result
                break
        except (OSError, ValueError, EOFError) as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))
            return

        loaded = self.main_window.current_fch
        if loaded and Path(loaded).resolve() == destination.resolve():
            if not self.main_window.load_file(str(destination), expected_revision=revision):
                self.main_window.clear_document()
        summary = self.main_window.backup_summary(backups, destination, source=backup_path)
        QMessageBox.information(self, "Backup Restored", f"Restored:\n{destination.absolute()}\n\n{summary}")
        self.load_backups()

    def restore_to_destination(self, backup_path, backup, destination):
        snapshot = self.main_window.inspect_save_destination(destination)
        if snapshot is not None and backup_path.samefile(destination):
            raise ValueError("The selected backup is already the destination file.")
        title = "Restore Backup"
        message = f"Restore this backup?\n\nBackup:\n{backup_path}\n\nDestination:\n{destination.absolute()}"
        if snapshot is not None:
            message += "\n\nThe existing file will be kept as a recovery copy before replacement."
            try:
                verified_payload(snapshot.contents)
            except (ValueError, EOFError) as exc:
                title = "Damaged Destination"
                message += f"\n\nThe destination appears damaged. {exc}"
        if QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return None
        backups = []
        if snapshot is not None:
            backups.append(self.main_window.create_backup(
                destination, destination.stem, allow_damaged=True, snapshot=snapshot,
            ))
        destination.parent.mkdir(parents=True, exist_ok=True)
        revision = atomic_write(destination, backup.contents, snapshot)
        return revision, backups

    def delete_backup(self):
        path = self.get_selected_backup()
        if path is None or is_steam_cloud_path(self.backup_directory):
            return
        owned = owned_backup(self.backup_directory, path)
        if owned is None:
            QMessageBox.warning(self, "Backup Kept", "VikingEditor could not verify ownership of this backup.")
            return
        if QMessageBox.question(
            self, "Delete Backup", f"Permanently delete this managed backup?\n\n{path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.delete_owned_backups([(path, owned[0].revision)])

    def delete_all_backups(self):
        group = self.character_filter.currentData()
        if not isinstance(group, str) or is_steam_cloud_path(self.backup_directory):
            return
        backups = list(managed_backups(self.backup_directory, self.backup_directory / group))
        if backups and QMessageBox.question(
            self, "Delete Character Backups",
            f"Permanently delete {len(backups)} managed backups for {group}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.delete_owned_backups(backups)

    def delete_owned_backups(self, backups):
        try:
            for path, revision in backups:
                remove_owned_backup(self.backup_directory, path, revision)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))
        finally:
            self.load_backups()
