import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QMessageBox, QHBoxLayout, QVBoxLayout,
    QGroupBox, QLabel, QLineEdit, QScrollArea, QWidget, QFrame,
)

from ui.itemSearchWidget import ItemSearchWidget, display_name, item_icon
from ui.tabStyle import DETAIL_STYLE, polish_forms
from ui.theme import set_themed_style
from subscripts.itemDatabase import get_stable_hash_code
from subscripts.itemValidation import (
    MIN_STACK, MAX_STACK, MIN_QUALITY, MAX_QUALITY, MIN_VARIANT, MAX_VARIANT,
    MIN_DURABILITY, MAX_DURABILITY, EQUIPMENT_PROPERTY_LIMITS, validate_item,
)
from subscripts.playerDataUtil import display_item_prefab, item_is_cheated


class ItemEditDialog(QDialog):
    """Browse items and preview changes without mutating the original item."""

    def __init__(self, item_data, parent=None, inventory_rows=4, *, inventory_version=110, equipment=False):
        super().__init__(parent)
        self.setWindowTitle("Edit Inventory Item")
        self.item_data = item_data
        self.inventory_rows = inventory_rows
        self.inventory_version = inventory_version
        self.hash_only = not item_data.get("prefab") and bool(item_data.get("prefab_hash"))
        self.existing_item = bool(item_data.get("prefab")) or self.hash_only
        self.resize(900, 720)
        self.setObjectName("detailPage")
        integer_style = "\n".join(
            rule.replace("QDoubleSpinBox", "QSpinBox")
            for rule in re.findall(r"[^{}]+\{[^{}]*\}", DETAIL_STYLE)
            if "QDoubleSpinBox" in rule
        )
        set_themed_style(self, DETAIL_STYLE + integer_style + """
            QDialog#detailPage { background: @page@; }
            QLabel#itemPreview { background: @preview@; border-radius: 10px; }
            QLabel#itemName { font-size: 18px; font-weight: 600; }
            QPushButton#applyItem { background: @primary@; color: @onPrimary@; border-color: @primary@; }
            QPushButton#applyItem:hover { background: @primaryHover@; }
            QPushButton#applyItem:disabled { background: @disabledSurface@; color: @disabledText@; border-color: @disabledSurface@; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)
        title = QLabel("Edit item" if self.existing_item else "Add item")
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
        self.prefab_input = ItemSearchWidget(display_item_prefab(item_data), self)
        self.initial_prefab = self.prefab_input.get_prefab()
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
        self.preview_summary.setTextFormat(Qt.PlainText)
        self.preview_summary.setObjectName("pageDescription")
        preview_layout.addWidget(self.preview_summary)
        right.addWidget(preview)

        properties = QGroupBox("Properties")
        form = QFormLayout(properties)
        equipment_limits = EQUIPMENT_PROPERTY_LIMITS if equipment else {}
        for attr, key, label, low, high, default in (
            ("stack_input", "stack", "Quantity", MIN_STACK, MAX_STACK, 1),
            ("quality_input", "quality", "Quality", MIN_QUALITY, MAX_QUALITY, 1),
            ("variant_input", "variant", "Style variant", MIN_VARIANT, MAX_VARIANT, 0),
        ):
            spin = QSpinBox()
            spin.setRange(*equipment_limits.get(key, (low, high)))
            spin.setValue(item_data.get(key, default))
            setattr(self, attr, spin)
            form.addRow(label, spin)
        self.durability_input = QDoubleSpinBox()
        self.durability_input.setRange(*equipment_limits.get("durability", (MIN_DURABILITY, MAX_DURABILITY)))
        self.durability_input.setValue(item_data.get("durability", 100.0))
        form.addRow("Durability", self.durability_input)
        self.stack_input.setToolTip("Valheim caps the loaded quantity at the prefab's stack limit.")
        self.variant_input.setToolTip("Valheim may reset a style variant that the prefab does not support.")
        self.equipped_input = QCheckBox("Equipped")
        self.equipped_input.setChecked(item_data.get("equipped", False))
        self.cheated_input = QCheckBox("Saved item cheat flag")
        self.cheated_input.setChecked(item_is_cheated(item_data, inventory_version))
        self.cheated_input.setEnabled(inventory_version == 110)
        self.cheated_input.setToolTip(
            "Valheim can reapply this flag based on item properties."
            if inventory_version == 110 else "Valheim ignores the extra flag byte in Inventory 109. The byte is preserved."
        )
        form.addRow(self.equipped_input)
        form.addRow(self.cheated_input)
        right.addWidget(properties)

        self.crafter_group = QGroupBox("Crafted by")
        self.crafter_group.setCheckable(True)
        self.crafter_group.setChecked(item_data.get("crafter_id", 0) != 0)
        self.crafter_group.setToolTip("Uncheck to remove crafting attribution from this item.")
        crafter_form = QFormLayout(self.crafter_group)
        self.crafter_name_input = QLineEdit(item_data.get("crafter_name", ""))
        self.crafter_name_input.setPlaceholderText("Crafter name")
        # QSpinBox is limited to 32 bits; keep character IDs as exact integers.
        self.crafter_id_input = QLineEdit(str(item_data.get("crafter_id", 0)))
        self.crafter_id_input.setToolTip(
            "The crafter's character ID. Keep the existing ID when only renaming. "
            "A nonzero ID is required to save crafting attribution."
        )
        crafter_form.addRow("Name", self.crafter_name_input)
        crafter_form.addRow("Character ID", self.crafter_id_input)
        right.addWidget(self.crafter_group)
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
        self.crafter_name_input.textChanged.connect(self.update_preview)
        self.crafter_group.toggled.connect(self.update_preview)
        self.initial_properties = self.property_values()
        self.initial_crafter = self.crafter_inputs()
        self.update_preview()
        self.prefab_input.search.setFocus()

    def update_preview(self, *args):
        prefab = self.prefab_input.get_prefab()
        if prefab:
            name = display_name(prefab)
        elif self.hash_only:
            name = f"Unknown item (ID: {self.item_data['prefab_hash']})"
        else:
            name = "Choose an item"
        self.preview_name.setText(name)
        icon = item_icon(prefab, self.variant_input.value())
        self.preview_icon.clear()
        if not icon.isNull():
            self.preview_icon.setPixmap(icon.pixmap(80, 80))
        else:
            self.preview_icon.setText("—")
        summary = (
            f"Quantity {self.stack_input.value()}  ·  Quality {self.quality_input.value()}\n"
            f"Style variant {self.variant_input.value()}"
        )
        if self.crafter_group.isChecked():
            summary += f"\nCrafted by {self.crafter_name_input.text()}"
        self.preview_summary.setText(summary)
        self.apply_button.setEnabled(bool(prefab) or self.hash_only)

    def validate_and_accept(self):
        try:
            changes = self.get_changes()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Item", str(error))
            return
        errors = []
        if changes or not self.existing_item:
            errors = validate_item(
                dict(self.item_data, **changes), inventory_rows=self.inventory_rows, allow_hash_only=True,
            )
        if errors:
            QMessageBox.warning(self, "Invalid Item", "The item contains invalid data:\n\n" + "\n".join(errors))
            return
        self.accept()

    def get_updated_data(self):
        return dict(self.item_data, **self.get_changes())

    def crafter_inputs(self):
        return (self.crafter_group.isChecked(), self.crafter_id_input.text(), self.crafter_name_input.text())

    def property_values(self):
        values = {
            "stack": self.stack_input.value(),
            "durability": self.durability_input.value(),
            "quality": self.quality_input.value(),
            "variant": self.variant_input.value(),
            "equipped": self.equipped_input.isChecked(),
        }
        if self.inventory_version == 110:
            values["cheated"] = self.cheated_input.isChecked()
        return values

    def get_changes(self):
        changes = {key: value for key, value in self.property_values().items()
                   if value != self.initial_properties[key]}
        prefab = self.prefab_input.get_prefab()
        if prefab != self.initial_prefab:
            if not prefab or "\x00" in prefab:
                raise ValueError("Enter a nonempty prefab ID without null characters.")
            prefab.encode("utf-8")
            changes.update(prefab=prefab, prefab_hash=get_stable_hash_code(prefab))

        inputs = self.crafter_inputs()
        if inputs == self.initial_crafter:
            return changes
        attributed, text, name = inputs
        crafter_id = 0
        crafter_name = ""
        if attributed:
            text = text.strip()
            if not re.fullmatch(r"[+-]?[0-9]+", text):
                raise ValueError("Crafter ID must be a whole number.")
            crafter_id = int(text)
            if crafter_id == 0:
                raise ValueError(
                    "Enter a nonzero crafter character ID, or uncheck Crafted by "
                    "to remove crafting attribution."
                )
            name.encode("utf-8")
            crafter_name = name
        for key, value in (("crafter_id", crafter_id), ("crafter_name", crafter_name)):
            if value != self.item_data.get(key):
                changes[key] = value
        return changes
