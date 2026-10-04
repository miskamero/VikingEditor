from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QListWidget, QGroupBox, QComboBox, QLineEdit,
)

from ui.tabStyle import detail_layout, polish_combo


class ProgressTab(QWidget):
    CATEGORIES = (
        ("Known recipes", "known_recipes"),
        ("Known stations", "known_stations"),
        ("Known materials", "known_material"),
        ("Trophies", "trophies"),
        ("Unique discoveries", "uniques"),
        ("Known biomes", "known_biomes"),
    )

    def __init__(self):
        super().__init__()
        self.player_data = {}
        layout = detail_layout(
            self, "Progress", "Discoveries and milestones from your Viking's journey.", scroll=True
        )
        summary = QGridLayout()
        summary.setSpacing(12)
        self.count_labels = {}
        for index, (title, key) in enumerate(self.CATEGORIES):
            card = QGroupBox(title)
            card_layout = QVBoxLayout(card)
            count = QLabel("0")
            count.setObjectName("metric")
            card_layout.addWidget(count)
            self.count_labels[key] = count
            summary.addWidget(card, index // 3, index % 3)
        layout.addLayout(summary)

        browser = QGroupBox("Browse discoveries")
        browser_layout = QVBoxLayout(browser)
        toolbar = QHBoxLayout()
        self.category_combo = QComboBox()
        polish_combo(self.category_combo)
        for title, key in self.CATEGORIES:
            self.category_combo.addItem(title, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search discoveries…")
        self.search.setClearButtonEnabled(True)
        toolbar.addWidget(self.category_combo)
        toolbar.addWidget(self.search, 1)
        browser_layout.addLayout(toolbar)
        self.discoveries_list = QListWidget()
        self.discoveries_list.setMinimumHeight(150)
        self.discoveries_list.setAlternatingRowColors(True)
        browser_layout.addWidget(self.discoveries_list, 1)
        self.results_label = QLabel()
        self.results_label.setObjectName("pageDescription")
        browser_layout.addWidget(self.results_label)
        layout.addWidget(browser, 1)
        self.category_combo.currentIndexChanged.connect(self.update_discoveries)
        self.search.textChanged.connect(self.filter_discoveries)
        self.update_discoveries()

    def load_data(self, player_data):
        self.player_data = player_data or {}
        for _, key in self.CATEGORIES:
            self.count_labels[key].setText(f"{len(self.player_data.get(key, [])):,}")
        self.update_discoveries()

    def update_discoveries(self):
        entries = self.player_data.get(self.category_combo.currentData(), [])
        if isinstance(entries, dict):
            names = [f"{name}  ·  Level {level}" for name, level in entries.items()]
        else:
            names = [str(entry) for entry in entries]
        self.discoveries_list.clear()
        self.discoveries_list.addItems(sorted(names, key=str.casefold))
        self.filter_discoveries()

    def filter_discoveries(self, text=None):
        query = self.search.text().strip().casefold()
        visible = 0
        for row in range(self.discoveries_list.count()):
            item = self.discoveries_list.item(row)
            matches = query in item.text().casefold()
            item.setHidden(not matches)
            visible += matches
        total = self.discoveries_list.count()
        self.results_label.setText(
            f"{visible} of {total} discoveries"
            if visible else ("No matching discoveries." if total else "No discoveries recorded in this category.")
        )
