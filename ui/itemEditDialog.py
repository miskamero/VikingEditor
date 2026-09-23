from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QMessageBox
)

from ui.itemSearchWidget import ItemSearchWidget
from subscripts.itemValidation import validate_item


class ItemEditDialog(QDialog):
    """A dialog to edit details of a specific item slot."""

    def __init__(self, item_data, parent=None, inventory_rows=4):
        super().__init__(parent)

        self.setWindowTitle("Edit Inventory Item")
        self.item_data = item_data
        self.inventory_rows = inventory_rows

        layout = QFormLayout(self)

        self.prefab_input = ItemSearchWidget(
            item_data.get("prefab", ""),
            self
        )

        self.stack_input = QSpinBox()
        self.stack_input.setRange(1, 9999)
        self.stack_input.setValue(
            item_data.get("stack", 1)
        )

        self.durability_input = QDoubleSpinBox()
        self.durability_input.setRange(0.0, 99999.0)
        self.durability_input.setValue(
            item_data.get("durability", 100.0)
        )

        self.quality_input = QSpinBox()
        self.quality_input.setRange(1, 99)
        self.quality_input.setValue(
            item_data.get("quality", 1)
        )

        self.variant_input = QSpinBox()
        self.variant_input.setRange(0, 99)
        self.variant_input.setValue(
            item_data.get("variant", 0)
        )

        self.equipped_input = QCheckBox()
        self.equipped_input.setChecked(
            item_data.get("equipped", False)
        )

        layout.addRow(
            "Item:",
            self.prefab_input
        )
        layout.addRow(
            "Stack Size:",
            self.stack_input
        )
        layout.addRow(
            "Durability:",
            self.durability_input
        )
        layout.addRow(
            "Quality Level:",
            self.quality_input
        )
        layout.addRow(
            "Variant (Style):",
            self.variant_input
        )
        layout.addRow(
            "Equipped:",
            self.equipped_input
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addRow(buttons)

    def validate_and_accept(self):
        item = self.item_data.copy()
        item.update(self.get_updated_data())

        errors = validate_item(
            item,
            {
                "uniques": [
                    f"invrows {self.inventory_rows}"
                ]
            }
        )

        if errors:
            QMessageBox.warning(
                self,
                "Invalid Item",
                "The item contains invalid data:\n\n"
                + "\n".join(
                    f"• {error}"
                    for error in errors
                )
            )
            return

        self.accept()

    def get_updated_data(self):
        return {
            "prefab": self.prefab_input.get_prefab(),
            "stack": self.stack_input.value(),
            "durability": self.durability_input.value(),
            "quality": self.quality_input.value(),
            "variant": self.variant_input.value(),
            "equipped": self.equipped_input.isChecked()
        }
