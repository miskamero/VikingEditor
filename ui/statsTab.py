from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView
)

from data.powers import GUARDIAN_POWERS
from ui.tabStyle import detail_layout, polish_forms, polish_table

class StatsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.player_data = None
        self.root_save = None
        self.edits = {}
        self.food_records = []

        main_layout = detail_layout(self, scroll=True)

        top_layout = QHBoxLayout()

        # 1. Vital Attributes Group
        vitals_group = QGroupBox("Vitals")
        vitals_layout = QFormLayout(vitals_group)

        self.max_health_spin = QDoubleSpinBox()
        self.max_health_spin.setRange(25.0, 99999.0)
        self.max_health_spin.setValue(25.0)

        self.health_spin = QDoubleSpinBox()
        self.health_spin.setRange(0.0, 99999.0)
        self.health_spin.setValue(25.0)

        self.max_stamina_spin = QDoubleSpinBox()
        self.max_stamina_spin.setRange(50.0, 99999.0)
        self.max_stamina_spin.setValue(50.0)

        self.stamina_spin = QDoubleSpinBox()
        self.stamina_spin.setRange(0.0, 99999.0)
        self.stamina_spin.setValue(50.0)

        self.max_eitr_spin = QDoubleSpinBox()
        self.max_eitr_spin.setRange(0.0, 99999.0)
        self.max_eitr_spin.setValue(0.0)

        self.eitr_spin = QDoubleSpinBox()
        self.eitr_spin.setRange(0.0, 99999.0)
        self.eitr_spin.setValue(0.0)

        vitals_layout.addRow("Max Health:", self.max_health_spin)
        vitals_layout.addRow("Current Health:", self.health_spin)
        vitals_layout.addRow("Max Stamina:", self.max_stamina_spin)
        vitals_layout.addRow("Current Stamina:", self.stamina_spin)
        vitals_layout.addRow("Max Eitr:", self.max_eitr_spin)
        vitals_layout.addRow("Current Eitr:", self.eitr_spin)
        top_layout.addWidget(vitals_group)

        food_group = QGroupBox("Active Food Buffs")
        food_layout = QVBoxLayout(food_group)
        
        food_buttons = QHBoxLayout()
        self.btn_add_food = QPushButton("Add Food")
        self.btn_add_food.setToolTip("You can add food while fewer than three foods are active.")
        self.btn_remove_food = QPushButton("Remove Selected")
        food_buttons.addWidget(self.btn_add_food)
        food_buttons.addWidget(self.btn_remove_food)
        food_layout.addLayout(food_buttons)

        self.food_table = QTableWidget()
        self.food_table.setColumnCount(2)
        self.food_table.setHorizontalHeaderLabels(["Food Prefab", "Time Left (sec)"])
        self.food_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        polish_table(self.food_table)
        self.food_table.setMinimumHeight(185)
        food_layout.addWidget(self.food_table)
        top_layout.addWidget(food_group)

        main_layout.addLayout(top_layout)

        # 3. Guardian Power
        gp_group = QGroupBox("Forsaken Power")
        gp_layout = QFormLayout(gp_group)

        self.gp_combo = QComboBox()
        for internal_name, display_name in GUARDIAN_POWERS.items():
            self.gp_combo.addItem(display_name, internal_name)

        self.gp_cooldown_spin = QDoubleSpinBox()
        self.gp_cooldown_spin.setRange(0.0, 999999.0)
        self.gp_cooldown_spin.setSuffix(" seconds")

        gp_layout.addRow("Active Power:", self.gp_combo)
        gp_layout.addRow("Cooldown Remaining:", self.gp_cooldown_spin)
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(gp_group, 2)

        # 4. Meta Settings
        meta_group = QGroupBox("Character Flags")
        meta_layout = QFormLayout(meta_group)

        self.used_cheats_check = QCheckBox("This character has used cheats")
        self.used_cheats_check.setToolTip(
            "This is the character-wide flag. Valheim also checks item flags and other conditions for achievements."
        )
        meta_layout.addRow(self.used_cheats_check)
        bottom_layout.addWidget(meta_group, 1)
        main_layout.addLayout(bottom_layout)

        main_layout.addStretch()

        polish_forms(self)
        self.btn_add_food.clicked.connect(lambda: self.add_food_row())
        self.btn_remove_food.clicked.connect(self.remove_selected_food)
        self.food_table.itemSelectionChanged.connect(self.update_food_buttons)
        self.food_table.itemChanged.connect(self.edit_food_name)
        self.vital_fields = (
            ("max_health", self.max_health_spin, 25.0), ("health", self.health_spin, 25.0),
            ("max_stamina", self.max_stamina_spin, 50.0), ("stamina", self.stamina_spin, 50.0),
            ("max_eitr", self.max_eitr_spin, 0.0), ("eitr", self.eitr_spin, 0.0),
            ("guardian_power_cooldown", self.gp_cooldown_spin, 0.0),
        )
        for field, spin, _ in self.vital_fields:
            spin.valueChanged.connect(lambda value, key=field: self.edits.update({key: value}))
        self.gp_combo.currentIndexChanged.connect(
            lambda _: self.edits.update(guardian_power=self.gp_combo.currentData())
        )
        self.update_food_buttons()

    def update_food_buttons(self):
        self.btn_add_food.setEnabled(self.food_table.rowCount() < 3)
        self.btn_remove_food.setEnabled(bool(self.food_table.selectedItems()))

    def load_data(self, player_data, root_save):
        """Loads data from both the nested character payload and the outer container."""
        self.player_data = player_data
        self.root_save = root_save
        self.edits.clear()

        data = player_data or {}
        for field, spin, default in self.vital_fields:
            with QSignalBlocker(spin):
                spin.setValue(data.get(field, default))

        self.food_table.setRowCount(0)
        self.food_records.clear()
        for food in data.get("foods", []):
            self.insert_food_record(dict(food))
        self.update_food_buttons()

        power = data.get("guardian_power", "")
        with QSignalBlocker(self.gp_combo):
            if self.gp_combo.count() > len(GUARDIAN_POWERS):
                self.gp_combo.removeItem(len(GUARDIAN_POWERS))
            if self.gp_combo.findData(power) == -1:
                self.gp_combo.addItem(f"Unlisted power ({power})", power)
            self.gp_combo.setCurrentIndex(self.gp_combo.findData(power))
        self.used_cheats_check.setChecked((root_save or {}).get("used_cheats", False))

    def add_food_row(self, name="Bread", time=1200.0):
        if self.food_table.rowCount() < 3:
            self.insert_food_record({"name": name, "time": time})
            self.update_food_buttons()

    def insert_food_record(self, food):
        row = self.food_table.rowCount()
        self.food_records.append(food)
        with QSignalBlocker(self.food_table):
            self.food_table.insertRow(row)
            self.food_table.setItem(row, 0, QTableWidgetItem(food.get("name", "")))

        time_spin = QDoubleSpinBox()
        time_spin.setRange(0.0, 99999.0)
        time_spin.setValue(food.get("time", 1200.0))
        time_spin.valueChanged.connect(lambda value: food.update(time=value))
        self.food_table.setCellWidget(row, 1, time_spin)

    def edit_food_name(self, item):
        self.food_records[item.row()]["name"] = item.text().strip()

    def remove_selected_food(self):
        current_row = self.food_table.currentRow()
        if current_row >= 0:
            del self.food_records[current_row]
            self.food_table.removeRow(current_row)
        self.update_food_buttons()

    def save_changes(self):
        """Applies UI edits back to the reference dictionaries."""
        if not self.player_data:
            return

        self.player_data.update(self.edits)
        self.player_data["foods"] = [dict(food) for food in self.food_records]
        if self.root_save:
            self.root_save["used_cheats"] = self.used_cheats_check.isChecked()
