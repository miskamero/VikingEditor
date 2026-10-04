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

        main_layout = detail_layout(
            self, "Stats", "Manage vitals, active food buffs, and your Forsaken power.", scroll=True
        )

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

        # 2. Active Foods (klinoff snore)
        food_group = QGroupBox("Active Food Buffs (Max 3)")
        food_layout = QVBoxLayout(food_group)
        
        food_buttons = QHBoxLayout()
        self.btn_add_food = QPushButton("Add Food")
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
        self.used_cheats_check.setToolTip("Character-wide flag; individual item flags are edited in Inventory.")
        meta_layout.addRow(self.used_cheats_check)
        bottom_layout.addWidget(meta_group, 1)
        main_layout.addLayout(bottom_layout)

        main_layout.addStretch()

        polish_forms(self)
        self.btn_add_food.clicked.connect(lambda: self.add_food_row())
        self.btn_remove_food.clicked.connect(self.remove_selected_food)
        self.food_table.itemSelectionChanged.connect(self.update_food_buttons)
        self.update_food_buttons()

    def update_food_buttons(self):
        self.btn_add_food.setEnabled(self.food_table.rowCount() < 3)
        self.btn_remove_food.setEnabled(bool(self.food_table.selectedItems()))

    def load_data(self, player_data, root_save):
        """Loads data from both the nested character payload and the outer container."""
        self.player_data = player_data
        self.root_save = root_save

        if not self.player_data:
            return

        # Vitals loading wheeeee
        self.max_health_spin.setValue(self.player_data.get("max_health", 25.0))
        self.health_spin.setValue(self.player_data.get("health", 25.0))
        self.max_stamina_spin.setValue(self.player_data.get("max_stamina", 50.0))
        self.stamina_spin.setValue(self.player_data.get("stamina", 50.0))
        self.max_eitr_spin.setValue(self.player_data.get("max_eitr", 0.0))
        self.eitr_spin.setValue(self.player_data.get("eitr", 0.0))

        # Active Foods loading
        self.food_table.setRowCount(0)
        foods = self.player_data.get("foods", [])
        for food in foods:
            self.add_food_row(food.get("name", ""), food.get("time", 1200.0))
        self.update_food_buttons()

        # Guardian Power loading
        gp_internal = self.player_data.get("guardian_power", "")
        index = self.gp_combo.findData(gp_internal)
        if index != -1:
            self.gp_combo.setCurrentIndex(index)
        else:
            self.gp_combo.setCurrentIndex(0)

        self.gp_cooldown_spin.setValue(self.player_data.get("guardian_power_cooldown", 0.0))

        # Outer Metadata loading
        if self.root_save:
            self.used_cheats_check.setChecked(self.root_save.get("used_cheats", False))

    def add_food_row(self, name="Bread", time=1200.0):
        if self.food_table.rowCount() >= 3:
            # dont try to add more than 3 foods, klinoff snore. klinoff is scared to eat more than 3 foods at once, so we should respect that.
            return
            
        row = self.food_table.rowCount()
        self.food_table.insertRow(row)

        name_item = QTableWidgetItem(name)
        self.food_table.setItem(row, 0, name_item)

        time_spin = QDoubleSpinBox()
        time_spin.setRange(0.0, 99999.0)
        time_spin.setValue(time)
        self.food_table.setCellWidget(row, 1, time_spin)
        self.update_food_buttons()

    def remove_selected_food(self):
        current_row = self.food_table.currentRow()
        if current_row >= 0:
            self.food_table.removeRow(current_row)
        self.update_food_buttons()

    def save_changes(self):
        """Applies UI edits back to the reference dictionaries."""
        if not self.player_data:
            return

        # Apply Vitals
        self.player_data["max_health"] = self.max_health_spin.value()
        self.player_data["health"] = self.health_spin.value()
        self.player_data["max_stamina"] = self.max_stamina_spin.value()
        self.player_data["stamina"] = self.stamina_spin.value()
        self.player_data["max_eitr"] = self.max_eitr_spin.value()
        self.player_data["eitr"] = self.eitr_spin.value()

        # Apply Foods
        updated_foods = []
        for row in range(self.food_table.rowCount()):
            name_item = self.food_table.item(row, 0)
            time_widget = self.food_table.cellWidget(row, 1)
            
            if name_item and isinstance(time_widget, QDoubleSpinBox):
                updated_foods.append({
                    "name": name_item.text().strip(),
                    "time": time_widget.value()
                })
        self.player_data["foods"] = updated_foods

        # Apply Guardian Power
        self.player_data["guardian_power"] = self.gp_combo.currentData()
        self.player_data["guardian_power_cooldown"] = self.gp_cooldown_spin.value()

        # Apply Outer Flags
        if self.root_save:
            self.root_save["used_cheats"] = self.used_cheats_check.isChecked()
