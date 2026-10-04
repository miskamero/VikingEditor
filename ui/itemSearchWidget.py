"""Searchable item browser with explicit selection and custom prefab support."""
from pathlib import Path
import re

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel

from subscripts.itemDatabase import load_item_database, get_item_icon_path
from ui.inventorySlot import format_item_name, get_item_icon


def display_name(prefab):
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", prefab)
    words = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", words)
    special = format_item_name(prefab)
    return special if special != prefab.replace("_", " ").title() else words.replace("_", " ").title()


def search_key(text):
    return "".join(re.findall(r"\w+", text.casefold()))


def rank_items(prefabs, query):
    """Match every search term in any order, prioritizing exact prefab/name matches."""
    terms = re.findall(r"\w+", query.casefold())
    compact = search_key(query)
    matches = []
    for prefab in prefabs:
        name = display_name(prefab)
        keys = (search_key(prefab), search_key(name))
        if not all(any(term in key for key in keys) for term in terms):
            continue
        rank = 0 if compact in keys else 1 if any(key.startswith(compact) for key in keys) else 2
        matches.append((rank, name.casefold(), prefab))
    return [prefab for _, _, prefab in sorted(matches)]


def item_icon(prefab, variant=0):
    path = get_item_icon_path(prefab, variant)
    icon = QIcon(str(path)) if path else QIcon()
    if icon.isNull():
        path = Path(__file__).resolve().parent.parent / "assets" / get_item_icon(prefab)
        icon = QIcon(str(path)) if path.is_file() else QIcon()
    return icon


class ItemResultsList(QListWidget):
    navigated = Signal(object)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End,
                           Qt.Key_PageUp, Qt.Key_PageDown):
            self.navigated.emit(self.currentItem())


class ItemSearchWidget(QWidget):
    prefabChanged = Signal(str)

    def __init__(self, current_prefab="", parent=None):
        super().__init__(parent)
        self.items = sorted(set(load_item_database().values()))
        self._icons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search items… e.g. iron sword, wolf armor")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search items")
        layout.addWidget(self.search)
        self.results = ItemResultsList()
        self.results.setIconSize(QSize(40, 40))
        self.results.setMinimumHeight(240)
        self.results.setAccessibleName("Matching items")
        layout.addWidget(self.results, 1)
        self.result_count = QLabel()
        self.result_count.setObjectName("pageDescription")
        layout.addWidget(self.result_count)
        label = QLabel("Selected prefab · editable for custom items")
        label.setObjectName("pageDescription")
        layout.addWidget(label)
        self.prefab_edit = QLineEdit()
        self.prefab_edit.setPlaceholderText("Select an item above or enter its prefab ID")
        self.prefab_edit.setAccessibleName("Selected prefab")
        layout.addWidget(self.prefab_edit)
        self.search.textChanged.connect(self.update_search_results)
        self.search.returnPressed.connect(self.select_first_result)
        # Only user interaction selects a prefab. currentItemChanged also fires
        # during show/hide/teardown, including after Apply has closed the dialog.
        self.results.itemClicked.connect(self.select_result)
        self.results.itemActivated.connect(self.select_result)
        self.results.navigated.connect(self.select_result)
        self.prefab_edit.textChanged.connect(self.prefabChanged)
        self.set_prefab(current_prefab)
        self.update_search_results("")

    def update_search_results(self, text):
        matches = rank_items(self.items, text)
        self.results.blockSignals(True)
        self.results.clear()
        for prefab in matches:
            if prefab not in self._icons:
                self._icons[prefab] = item_icon(prefab)
            row = QListWidgetItem(self._icons[prefab], f"{display_name(prefab)}\n{prefab}")
            row.setData(Qt.UserRole, prefab)
            row.setSizeHint(QSize(0, 64))
            self.results.addItem(row)
            if prefab == self.get_prefab():
                self.results.setCurrentItem(row)
        self.results.blockSignals(False)
        self.result_count.setText(
            f"{len(matches)} of {len(self.items)} items"
            if matches else "No matches. Try fewer words or enter a custom prefab below."
        )
        if not self.items:
            self.result_count.setText("No item database. Use File → Update Item Database, or enter a prefab below.")
        self.result_count.setWordWrap(True)

    def select_first_result(self):
        if self.results.count():
            self.results.setCurrentRow(0)
            self.set_prefab(self.results.item(0).data(Qt.UserRole))
            self.results.setFocus()

    def select_result(self, current, previous=None):
        if current:
            self.set_prefab(current.data(Qt.UserRole))

    def set_prefab(self, prefab):
        self.prefab_edit.setText(prefab)

    def get_prefab(self):
        return self.prefab_edit.text().strip()
