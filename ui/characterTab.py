from datetime import datetime
from ui.tabStyle import detail_layout, polish_forms

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QMessageBox,
    QApplication
)


class CharacterTab(QWidget):
    def __init__(self):
        super().__init__()

        self.player_data = None
        self.root_save = None

        main_layout = detail_layout(
            self, "Character", "Edit your character's name and review identity and save details.", scroll=True
        )
        main_layout.setSpacing(12)

        # ==========================================================
        # Character Information
        # ==========================================================

        character_group = QGroupBox("Character Information")
        character_layout = QFormLayout(character_group)
        character_layout.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Character name")

        character_layout.addRow(
            "Character Name:",
            self.name_input
        )

        self.player_id_input = self.create_readonly_field()
        character_layout.addRow(
            "Player ID:",
            self.player_id_input
        )

        self.start_seed_input = self.create_readonly_field()
        character_layout.addRow(
            "Start Seed:",
            self.start_seed_input
        )

        self.creation_date_label = QLabel("-")
        character_layout.addRow(
            "Created:",
            self.creation_date_label
        )

        self.cheats_label = QLabel("-")
        character_layout.addRow(
            "Used Cheats:",
            self.cheats_label
        )

        main_layout.addWidget(character_group)

        # ==========================================================
        # Save Information
        # ==========================================================

        save_group = QGroupBox("Save Information")
        save_layout = QFormLayout(save_group)
        save_layout.setSpacing(8)

        self.fch_version_label = QLabel("-")
        save_layout.addRow(
            "Save Version:",
            self.fch_version_label
        )

        self.player_data_version_label = QLabel("-")
        save_layout.addRow(
            "Player Data Version:",
            self.player_data_version_label
        )

        self.profile_count_label = QLabel("-")
        save_layout.addRow(
            "Profile Count:",
            self.profile_count_label
        )

        self.stat_count_label = QLabel("-")
        save_layout.addRow(
            "Stat Count:",
            self.stat_count_label
        )

        main_layout.addWidget(save_group)

        # ==========================================================
        # Actions
        # ==========================================================

        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout(actions_group)

        self.copy_player_id_button = QPushButton("Copy Player ID")
        self.copy_seed_button = QPushButton("Copy Start Seed")

        self.copy_player_id_button.clicked.connect(
            self.copy_player_id
        )

        self.copy_seed_button.clicked.connect(
            self.copy_start_seed
        )

        actions_layout.addWidget(self.copy_player_id_button)
        actions_layout.addWidget(self.copy_seed_button)
        actions_layout.addStretch()

        main_layout.addWidget(actions_group)

        main_layout.addStretch()
        polish_forms(self)
        self.cheats_label.setToolTip("Change this character-wide flag in the Stats tab.")

    def create_readonly_field(self):
        field = QLineEdit()
        field.setReadOnly(True)
        field.setCursorPosition(0)
        return field

    def load_data(self, player_data, root_save=None):
        self.player_data = player_data
        self.root_save = root_save

        if not self.root_save:
            return

        # ----------------------------------------------------------
        # Character information
        # ----------------------------------------------------------

        character_name = self.root_save.get(
            "character_name",
            "Viking"
        )

        self.name_input.setText(
            str(character_name)
        )

        player_id = self.root_save.get(
            "player_id",
            ""
        )

        self.player_id_input.setText(
            str(player_id)
        )

        start_seed = self.root_save.get(
            "start_seed",
            ""
        )

        self.start_seed_input.setText(
            str(start_seed)
        )

        used_cheats = self.root_save.get(
            "used_cheats",
            False
        )

        self.cheats_label.setText(
            "Yes" if used_cheats else "No"
        )

        # ----------------------------------------------------------
        # Creation date
        # ----------------------------------------------------------

        date_created = self.root_save.get(
            "date_created_unix"
        )

        if date_created:
            try:
                created_datetime = datetime.fromtimestamp(
                    date_created
                )

                self.creation_date_label.setText(
                    created_datetime.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

            except (TypeError, ValueError, OSError):
                self.creation_date_label.setText(
                    "Unknown"
                )
        else:
            self.creation_date_label.setText(
                "Unknown"
            )

        # ----------------------------------------------------------
        # Save information
        # ----------------------------------------------------------

        self.fch_version_label.setText(
            str(
                self.root_save.get(
                    "version",
                    "-"
                )
            )
        )

        self.player_data_version_label.setText(
            str(
                self.player_data.get(
                    "version",
                    "-"
                )
            )
            if self.player_data
            else "-"
        )

        self.profile_count_label.setText(
            str(
                self.root_save.get(
                    "profile_count",
                    "-"
                )
            )
        )

        self.stat_count_label.setText(
            str(
                self.root_save.get(
                    "stat_count",
                    "-"
                )
            )
        )

    def save_changes(self):
        if not self.root_save:
            return

        new_name = self.name_input.text().strip()

        if not new_name:
            QMessageBox.warning(
                self,
                "Invalid Character Name",
                "Character name cannot be empty."
            )
            return

        self.root_save["character_name"] = new_name

        if self.player_data is not None:
            self.player_data["character_name"] = new_name

    def copy_player_id(self):
        player_id = self.player_id_input.text()

        if not player_id:
            return

        self.copy_to_clipboard(
            player_id,
            "Player ID"
        )

    def copy_start_seed(self):
        start_seed = self.start_seed_input.text()

        if not start_seed:
            return

        self.copy_to_clipboard(
            start_seed,
            "Start Seed"
        )

    def copy_to_clipboard(self, text, label):
        QApplication.clipboard().setText(text)

        QMessageBox.information(
            self,
            "Copied",
            f"{label} copied to clipboard."
        )
