import math

from PySide6.QtCore import Qt
from ui.tabStyle import detail_layout, polish_table

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QLabel
)


class StatisticsTab(QWidget):
    def __init__(self):
        super().__init__()

        self.player_data = None
        self.root_save = None

        layout = detail_layout(
            self, "Statistics", "Explore your character's lifetime activity."
        )
        self.table_controls = {}

        self.tabs = QTabWidget()

        self.enemies_widget, self.enemies_table, self.enemies_search, self.enemies_total = self.create_table()
        self.pickups_widget, self.pickups_table, self.pickups_search, self.pickups_total = self.create_table()
        self.crafted_widget, self.crafted_table, self.crafted_search, self.crafted_total = self.create_table()
        self.pickables_widget, self.pickables_table, self.pickables_search, self.pickables_total = self.create_table()
        self.pieces_widget, self.pieces_table, self.pieces_search, self.pieces_total = self.create_table()

        self.tabs.addTab(self.enemies_widget, "Enemies")
        self.tabs.addTab(self.pickups_widget, "Items Picked Up")
        self.tabs.addTab(self.crafted_widget, "Items Crafted")
        self.tabs.addTab(self.pickables_widget, "Pickables")
        self.tabs.addTab(self.pieces_widget, "Pieces Placed")

        layout.addWidget(self.tabs)

    def create_table(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        top_layout = QHBoxLayout()

        search = QLineEdit()
        search.setPlaceholderText("Search...")
        search.setClearButtonEnabled(True)
        search.setMinimumHeight(32)
        
        total_label = QLabel("Total: 0")
        total_label.setObjectName("badge")
        total_label.setMinimumWidth(100)
        total_label.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignVCenter
        )

        top_layout.addWidget(search)
        top_layout.addWidget(total_label)

        layout.addLayout(top_layout)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Name", "Count"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        table.verticalHeader().setDefaultSectionSize(30)
        polish_table(table)
        table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents
        )

        table.horizontalHeaderItem(1).setTextAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout.addWidget(table)

        search.textChanged.connect(
            lambda text: self.filter_table(table, text)
        )
        status = QLabel("No activity recorded.")
        status.setObjectName("pageDescription")
        layout.addWidget(status)
        self.table_controls[table] = (search, total_label, status)

        return container, table, search, total_label

    def load_data(self, player_data, root_save):
        self.player_data = player_data
        self.root_save = root_save

        self.clear_tables()

        if not isinstance(self.root_save, dict):
            return

        profiles = self.root_save.get("profiles", [])

        if not isinstance(profiles, list) or not profiles:
            return

        # fchUtil preserves serialized order in v46/v47: RawStats = 0, Any = 1.
        # Raw contains lifetime totals; other profiles overlap with it.
        raw = profiles[0]
        if not isinstance(raw, dict):
            return

        # enemy_stats is a list of method dictionaries, not enemy records.
        # KillModifiers.MixedAndTotal = 0 already includes the other methods.
        enemy_slots = raw.get("enemy_stats", [])
        enemy_stats = (
            enemy_slots[0]
            if isinstance(enemy_slots, list) and enemy_slots
            else {}
        )

        for table, data in (
            (self.enemies_table, enemy_stats),
            (self.pickups_table, raw.get("item_pickup_stats", {})),
            (self.crafted_table, raw.get("item_craft_stats", {})),
            (self.pickables_table, raw.get("pickable_stats", {})),
            (self.pieces_table, raw.get("pieces_placed_stats", {})),
        ):
            # Missing or malformed statistics display as empty, without using Any.
            valid_data = {
                name: count for name, count in data.items()
                if isinstance(name, str)
                and isinstance(count, (int, float))
                and not isinstance(count, bool)
                and math.isfinite(count)
            } if isinstance(data, dict) else {}
            self.populate_table(table, valid_data)

    def get_first_populated(self, dictionaries):
        for data in dictionaries:
            if data:
                return data

        return {}

    def populate_table(self, table, data):
        table.setRowCount(0)

        total = sum(data.values())

        total_label = None

        if table is self.enemies_table:
            total_label = self.enemies_total
        elif table is self.pickups_table:
            total_label = self.pickups_total
        elif table is self.crafted_table:
            total_label = self.crafted_total
        elif table is self.pickables_table:
            total_label = self.pickables_total
        elif table is self.pieces_table:
            total_label = self.pieces_total

        if total_label:
            total_label.setText(
                f"Total: {self.format_count(total)}"
            )

        sorted_items = sorted(
            data.items(),
            key=lambda item: item[1],
            reverse=True
        )

        for name, count in sorted_items:
            row = table.rowCount()
            table.insertRow(row)

            display_name = self.format_name(name)

            table.setItem(
                row,
                0,
                QTableWidgetItem(display_name)
            )

            table.setItem(
                row,
                1,
                QTableWidgetItem(self.format_count(count))
            )
            table.item(row, 1).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.filter_table(table, self.table_controls[table][0].text())

    def filter_table(self, table, text):
        text = text.lower().strip()

        for row in range(table.rowCount()):
            item = table.item(row, 0)

            if item is None:
                continue

            matches = text in item.text().lower()

            table.setRowHidden(row, not matches)
        visible = sum(not table.isRowHidden(row) for row in range(table.rowCount()))
        status = self.table_controls[table][2]
        status.setText(
            f"{visible} of {table.rowCount()} entries"
            if visible else ("No matching entries." if table.rowCount() else "No activity recorded.")
        )

    def format_name(self, name):
        if name.startswith("$"):
            name = name[1:]

        return name.replace("_", " ").strip().title()

    def format_count(self, count):
        if float(count).is_integer():
            return f"{int(count):,}".replace(",", " ")

        return str(count)

    def clear_tables(self):
        for table, (search, total, status) in self.table_controls.items():
            search.clear()
            total.setText("Total: 0")
            status.setText("No activity recorded.")
        self.enemies_table.setRowCount(0)
        self.pickups_table.setRowCount(0)
        self.crafted_table.setRowCount(0)
        self.pickables_table.setRowCount(0)
        self.pieces_table.setRowCount(0)
