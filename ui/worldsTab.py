import math

from PySide6.QtCore import QSignalBlocker, Qt
from ui.tabStyle import detail_layout, polish_forms
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QFormLayout,
    QApplication,
    QSplitter,
    QLineEdit,
    QComboBox,
    QGridLayout,
)


class WorldsTab(QWidget):
    def __init__(self):
        super().__init__()

        self.root_save = None
        self.worlds = {}
        self.named_times = {}

        main_layout = detail_layout(self, scroll=True)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        main_layout.addWidget(splitter, 1)

        worlds_group = QGroupBox("Worlds")
        worlds_layout = QVBoxLayout(worlds_group)
        self.collection = QComboBox()
        self.collection.addItem("Named play time", 0)
        self.collection.addItem("Saved world locations", "records")
        self.collection.setAccessibleName("World data collection")
        self.collection.currentIndexChanged.connect(self.show_collection)
        worlds_layout.addWidget(self.collection)
        self.world_search = QLineEdit()
        self.world_search.setPlaceholderText("Search worlds…")
        self.world_search.setClearButtonEnabled(True)
        self.world_search.textChanged.connect(self.filter_worlds)
        worlds_layout.addWidget(self.world_search)

        self.world_list = QListWidget()
        self.world_list.currentRowChanged.connect(
            self.on_world_selected
        )

        worlds_layout.addWidget(self.world_list)

        self.world_count_label = QLabel("No worlds recorded.")
        self.world_count_label.setObjectName("pageDescription")
        worlds_layout.addWidget(self.world_count_label)
        splitter.addWidget(worlds_group)

        # wrld info
        info_group = QGroupBox("World Information")
        info_layout = QVBoxLayout(info_group)


        self.world_name_label = QLabel("-")
        self.world_name_label.setTextFormat(Qt.PlainText)
        self.world_name_label.setWordWrap(True)
        self.world_name_label.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )

        info_layout.addWidget(
            self.world_name_label
        )

        # Time played
        self.time_played_label = QLabel("-")
        self.time_played_label.setObjectName("badge")

        info_layout.addWidget(
            self.time_played_label
        )

        # World ID
        world_id_group = QGroupBox("World ID")
        world_id_layout = QHBoxLayout(
            world_id_group
        )

        self.world_id_label = QLabel("-")
        self.world_id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        world_id_layout.addWidget(
            self.world_id_label,
            1
        )

        self.copy_world_id_button = QPushButton(
            "Copy"
        )
        self.copy_world_id_button.clicked.connect(
            self.copy_world_id
        )

        world_id_layout.addWidget(
            self.copy_world_id_button
        )

        info_layout.addWidget(
            world_id_group
        )

        # Locations
        locations_group = QGroupBox(
            "Character Locations"
        )

        locations_layout = QFormLayout(
            locations_group
        )

        locations_layout.setSpacing(10)

        self.spawn_label = QLabel("-")
        self.logout_label = QLabel("-")
        self.death_label = QLabel("-")
        self.home_label = QLabel("-")

        for label in (
            self.spawn_label,
            self.logout_label,
            self.death_label,
            self.home_label,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

        locations_layout.addRow(
            "Spawn:",
            self.spawn_label
        )

        locations_layout.addRow(
            "Logout:",
            self.logout_label
        )

        locations_layout.addRow(
            "Death:",
            self.death_label
        )

        locations_layout.addRow(
            "Home:",
            self.home_label
        )

        info_layout.addWidget(
            locations_group
        )

        # copy buttons
        actions_layout = QGridLayout()

        self.copy_spawn_button = QPushButton(
            "Copy Spawn"
        )
        self.copy_logout_button = QPushButton(
            "Copy Logout"
        )
        self.copy_death_button = QPushButton(
            "Copy Death"
        )
        self.copy_home_button = QPushButton(
            "Copy Home"
        )

        self.copy_spawn_button.clicked.connect(
            lambda: self.copy_location(
                self.spawn_label.text()
            )
        )

        self.copy_logout_button.clicked.connect(
            lambda: self.copy_location(
                self.logout_label.text()
            )
        )

        self.copy_death_button.clicked.connect(
            lambda: self.copy_location(
                self.death_label.text()
            )
        )

        self.copy_home_button.clicked.connect(
            lambda: self.copy_location(
                self.home_label.text()
            )
        )

        actions_layout.addWidget(
            self.copy_spawn_button, 0, 0
        )
        actions_layout.addWidget(
            self.copy_logout_button, 0, 1
        )
        actions_layout.addWidget(
            self.copy_death_button, 1, 0
        )
        actions_layout.addWidget(
            self.copy_home_button, 1, 1
        )

        info_layout.addLayout(
            actions_layout
        )

        info_layout.addStretch()

        splitter.addWidget(info_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 650])
        polish_forms(self)

        self.clear_display()

    def filter_worlds(self):
        query = self.world_search.text().strip().casefold()
        visible = 0
        for row in range(self.world_list.count()):
            item = self.world_list.item(row)
            matches = query in item.text().casefold()
            item.setHidden(not matches)
            visible += matches
        total = self.world_list.count()
        self.world_count_label.setText(f"{visible} of {total} entries" if visible else
                                       ("No matching entries." if total else "No entries in this collection."))
        current = self.world_list.currentItem()
        if current and current.isHidden():
            self.world_list.setCurrentRow(-1)

    def load_data(self, root_save):
        self.root_save = root_save
        data = root_save or {}
        self.worlds = {str(record["world_id"]): record for record in data.get("worlds", [])}

        # RawStats bucket 0 is the lifetime total. Other buckets can overlap it
        # and have their own entries. None provides a UID for these names.
        profiles = data.get("profiles", [])
        self.named_times = {}
        for index, profile in enumerate(profiles if isinstance(profiles, list) else []):
            times = profile.get("known_worlds") if isinstance(profile, dict) else None
            if isinstance(times, dict):
                self.named_times[index] = {name: seconds for name, seconds in times.items()
                                           if isinstance(name, str) and type(seconds) is not bool
                                           and isinstance(seconds, (int, float))}
        blocked = self.collection.blockSignals(True)
        while self.collection.count() > 2:
            self.collection.removeItem(2)
        self.collection.setItemText(0, f"Named play time, total ({len(self.named_times.get(0, {}))})")
        self.collection.setItemText(1, f"Saved world locations ({len(self.worlds)})")
        for index, times in self.named_times.items():
            if index and times:
                self.collection.addItem(f"Named play time, statistics profile {index} ({len(times)})", index)
        self.collection.setCurrentIndex(1 if self.worlds and not self.named_times.get(0) else 0)
        if not self.worlds and not self.named_times.get(0) and self.collection.count() > 2:
            self.collection.setCurrentIndex(2)
        self.collection.blockSignals(blocked)
        self.show_collection()

    def show_collection(self):
        self.clear_display()
        collection = self.collection.currentData()
        show_records = collection == "records"
        entries = self.worlds if show_records else self.named_times.get(collection, {})
        with QSignalBlocker(self.world_list):
            self.world_list.clear()
            self.world_search.clear()
            for key in entries:
                item = QListWidgetItem(f"World UID {key}" if show_records else key)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.world_list.addItem(item)
        if entries:
            self.world_list.setCurrentRow(0)
        self.filter_worlds()

    def on_world_selected(self, row):
        self.clear_display()
        item = self.world_list.item(row) if row >= 0 else None
        if item is None or item.isHidden():
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        collection = self.collection.currentData()
        if collection == "records":
            self.world_name_label.setText("Saved world record")
            self.time_played_label.setText("Time Played: Unknown")
            self.display_world(self.worlds[key])
        else:
            self.world_name_label.setText(key)
            seconds = self.named_times[collection][key]
            duration = self.format_duration(seconds) if math.isfinite(seconds) else "Unknown"
            self.time_played_label.setText(f"Time Played: {duration}")

    # Display
    def display_world(self, world):
        self.world_id_label.setText(
            str(
                world.get(
                    "world_id",
                    "-"
                )
            )
        )

        # Spawn
        if world.get(
            "have_custom_spawn",
            False
        ):
            self.spawn_label.setText(
                self.format_point(
                    world.get(
                        "spawn_point"
                    )
                )
            )
        else:
            self.spawn_label.setText(
                "Not set"
            )

        # Logout
        if world.get(
            "have_logout_point",
            False
        ):
            self.logout_label.setText(
                self.format_point(
                    world.get(
                        "logout_point"
                    )
                )
            )
        else:
            self.logout_label.setText(
                "Not set"
            )

        # Death
        if world.get(
            "have_death_point",
            False
        ):
            self.death_label.setText(
                self.format_point(
                    world.get(
                        "death_point"
                    )
                )
            )
        else:
            self.death_label.setText(
                "Not set"
            )

        # Home
        self.home_label.setText(
            self.format_point(
                world.get(
                    "home_point"
                )
            )
        )

        self.update_button_states()

    # Formatting
    def format_point(self, point):
        if not point or len(point) < 3:
            return "Not set"

        x, y, z = point[:3]

        return (
            f"X: {self.format_number(x)}    "
            f"Y: {self.format_number(y)}    "
            f"Z: {self.format_number(z)}"
        )

    def format_number(self, value):
        try:
            number = float(value)

            if number.is_integer():
                return str(int(number))

            return (
                f"{number:.2f}"
                .rstrip("0")
                .rstrip(".")
            )

        except (
            TypeError,
            ValueError
        ):
            return str(value)

    def format_duration(self, seconds):
        seconds = int(seconds)
        prefix = "-" if seconds < 0 else ""
        seconds = abs(seconds)

        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        parts = []

        if hours:
            parts.append(f"{hours}h")

        if minutes:
            parts.append(f"{minutes}m")

        if seconds or not parts:
            parts.append(f"{seconds}s")

        return prefix + " ".join(parts)

    # Button States
    def update_button_states(self):
        self.copy_spawn_button.setEnabled(
            self.spawn_label.text()
            not in ("Not set", "-")
        )

        self.copy_logout_button.setEnabled(
            self.logout_label.text()
            not in ("Not set", "-")
        )

        self.copy_death_button.setEnabled(
            self.death_label.text()
            not in ("Not set", "-")
        )

        self.copy_home_button.setEnabled(
            self.home_label.text()
            not in ("Not set", "-")
        )

        self.copy_world_id_button.setEnabled(
            self.world_id_label.text()
            != "-"
        )

    # Clipboard
    def copy_world_id(self):
        world_id = self.world_id_label.text()

        if not world_id or world_id == "-":
            return

        QApplication.clipboard().setText(
            world_id
        )

    def copy_location(self, text):
        if self.world_id_label.text() == "-" or not text or text in ("Not set", "-"):
            return

        QApplication.clipboard().setText(
            text
        )

    def clear_location_display(self):
        self.world_id_label.setText("-")
        self.spawn_label.setText("-")
        self.logout_label.setText("-")
        self.death_label.setText("-")
        self.home_label.setText("-")

        self.update_button_states()

    def clear_display(self):
        self.world_name_label.setText("-")
        self.time_played_label.setText(
            "Time Played: -"
        )

        self.clear_location_display()
