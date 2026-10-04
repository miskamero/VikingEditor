import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QMessageBox, QHBoxLayout, QVBoxLayout,
    QGroupBox, QLabel, QScrollArea, QWidget, QFrame,
)

from ui.itemSearchWidget import ItemSearchWidget, display_name, item_icon
from ui.tabStyle import DETAIL_STYLE, polish_forms
from subscripts.itemValidation import validate_item


class ItemEditDialog(QDialog):
    """Browse items and preview changes without mutating the original item."""

    def __init__(self, item_data, parent=None, inventory_rows=4):
        super().__init__(parent)
        self.setWindowTitle("Edit Inventory Item")
        self.item_data = item_data
        self.inventory_rows = inventory_rows
        self.resize(900, 720)
        self.setObjectName("detailPage")
        integer_style = "\n".join(
            rule.replace("QDoubleSpinBox", "QSpinBox")
            for rule in re.findall(r"[^{}]+\{[^{}]*\}", DETAIL_STYLE)
            if "QDoubleSpinBox" in rule
        )
        self.setStyleSheet(DETAIL_STYLE + integer_style + """
            QDialog#detailPage { background: #f4f6f7; }
            QLabel#itemPreview { background: #252b27; border-radius: 10px; }
            QLabel#itemName { font-size: 18px; font-weight: 600; }
            QPushButton#applyItem { background: #45623a; color: white; border-color: #45623a; }
            QPushButton#applyItem:hover { background: #567849; }
            QPushButton#applyItem:disabled { background: #dce3d8; color: #899582; border-color: #dce3d8; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)
        title = QLabel("Edit item" if item_data.get("prefab") else "Add item")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        subtitle = QLabel("Find your item, fine-tune its properties, and preview the result.")
        subtitle.setObjectName("pageDescription")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(18)
        browse = QGroupBox("Item library")
        browse_layout = QVBoxLayout(browse)
        self.prefab_input = ItemSearchWidget(item_data.get("prefab", ""), self)
        browse_layout.addWidget(self.prefab_input)
        body.addWidget(browse, 3)

        details = QWidget()
        right = QVBoxLayout(details)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)
        preview = QGroupBox("Selected item")
        preview_layout = QVBoxLayout(preview)
        self.preview_icon = QLabel()
        self.preview_icon.setObjectName("itemPreview")
        self.preview_icon.setFixedSize(108, 108)
        self.preview_icon.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.preview_icon, 0, Qt.AlignCenter)
        self.preview_name = QLabel()
        self.preview_name.setObjectName("itemName")
        self.preview_name.setAlignment(Qt.AlignCenter)
        self.preview_name.setWordWrap(True)
        self.preview_name.setTextFormat(Qt.PlainText)
        preview_layout.addWidget(self.preview_name)
        self.preview_summary = QLabel()
        self.preview_summary.setAlignment(Qt.AlignCenter)
        self.preview_summary.setWordWrap(True)
        self.preview_summary.setObjectName("pageDescription")
        preview_layout.addWidget(self.preview_summary)
        right.addWidget(preview)

        properties = QGroupBox("Properties")
        form = QFormLayout(properties)
        for attr, key, label, low, high, default in (
            ("stack_input", "stack", "Quantity", 1, 9999, 1),
            ("quality_input", "quality", "Quality", 1, 99, 1),
            ("variant_input", "variant", "Style variant", 0, 99, 0),
        ):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(item_data.get(key, default))
            setattr(self, attr, spin)
            form.addRow(label, spin)
        self.durability_input = QDoubleSpinBox()
        self.durability_input.setRange(0.0, 99999.0)
        self.durability_input.setValue(item_data.get("durability", 100.0))
        form.addRow("Durability", self.durability_input)
        self.variant_input.setToolTip("Style indices start at 0. The preview uses the selected variant when available.")
        self.equipped_input = QCheckBox("Equipped")
        self.equipped_input.setChecked(item_data.get("equipped", False))
        self.cheated_input = QCheckBox("Spawned in with cheats")
        self.cheated_input.setChecked(item_data.get("cheated", False))
        self.cheated_input.setToolTip("Uncheck to remove this item's 'spawned in with cheats' label.")
        form.addRow(self.equipped_input)
        form.addRow(self.cheated_input)
        right.addWidget(properties)
        right.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(details)
        body.addWidget(scroll, 2)
        outer.addLayout(body, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.Ok)
        self.apply_button.setText("Apply item")
        self.apply_button.setObjectName("applyItem")
        # Enter in the search box selects a result; saving is always explicit.
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        polish_forms(self)
        form.setVerticalSpacing(8)
        self.prefab_input.prefabChanged.connect(self.update_preview)
        for spin in (self.stack_input, self.quality_input, self.variant_input):
            spin.valueChanged.connect(self.update_preview)
        self.update_preview()
        self.prefab_input.search.setFocus()

    def update_preview(self, *args):
        prefab = self.prefab_input.get_prefab()
        self.preview_name.setText(display_name(prefab) if prefab else "Choose an item")
        icon = item_icon(prefab, self.variant_input.value())
        self.preview_icon.clear()
        if not icon.isNull():
            self.preview_icon.setPixmap(icon.pixmap(80, 80))
        else:
            self.preview_icon.setText("—")
        self.preview_summary.setText(
            f"Quantity {self.stack_input.value()}  ·  Quality {self.quality_input.value()}\n"
            f"Style variant {self.variant_input.value()}"
        )
        self.apply_button.setEnabled(bool(prefab))

    def validate_and_accept(self):
        item = self.item_data.copy()
        item.update(self.get_updated_data())
        errors = validate_item(item, {"uniques": [f"invrows {self.inventory_rows}"]})
        if errors:
            QMessageBox.warning(self, "Invalid Item", "The item contains invalid data:\n\n" + "\n".join(errors))
            return
        self.accept()

    def get_updated_data(self):
        return {
            "prefab": self.prefab_input.get_prefab(),
            "stack": self.stack_input.value(),
            "durability": self.durability_input.value(),
            "quality": self.quality_input.value(),
            "variant": self.variant_input.value(),
            "equipped": self.equipped_input.isChecked(),
            "cheated": self.cheated_input.isChecked(),
        }
