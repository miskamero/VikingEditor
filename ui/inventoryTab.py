import json
import re

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QMenu,
    QMessageBox,
    QDialog,
    QApplication,
    QHBoxLayout,
    QCheckBox
)

from PySide6.QtCore import Qt

from ui.inventorySlot import InventorySlot
from ui.itemEditDialog import ItemEditDialog

class InventoryTab(QWidget):
    GRID_WIDTH = 8
    DEFAULT_GRID_HEIGHT = 4

    def __init__(self):
        super().__init__()
        self.player_data = None
        
        self.main_layout = QVBoxLayout(self)

        self.upgrade_layout = QHBoxLayout()

        self.wider_pockets_checkbox = QCheckBox(
            "Wider Pockets"
        )

        self.deeper_pockets_checkbox = QCheckBox(
            "Deeper Pockets"
        )

        self.upgrade_layout.addWidget(
            self.wider_pockets_checkbox
        )

        self.upgrade_layout.addWidget(
            self.deeper_pockets_checkbox
        )

        self.upgrade_layout.addStretch()

        self.main_layout.addLayout(
            self.upgrade_layout
        )

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(6)
        self.main_layout.addLayout(self.grid_layout)
        
        self.slots = {}

        self.wider_pockets_checkbox.stateChanged.connect(
            self.handle_wider_pockets
        )
        self.deeper_pockets_checkbox.stateChanged.connect(
            self.update_inventory_grid
        )

        self.init_empty_grid()

    def get_inventory_rows(self):
        if self.deeper_pockets_checkbox.isChecked():
            return 6
        elif self.wider_pockets_checkbox.isChecked():
            return 5
        else:
            return 4

    def handle_wider_pockets(self, state):
        if not state and self.deeper_pockets_checkbox.isChecked():
            self.deeper_pockets_checkbox.blockSignals(True)
            self.deeper_pockets_checkbox.setChecked(False)
            self.deeper_pockets_checkbox.blockSignals(False)

        self.update_inventory_grid()

    def update_inventory_grid(self):
        if self.deeper_pockets_checkbox.isChecked():
            if not self.wider_pockets_checkbox.isChecked():
                self.wider_pockets_checkbox.blockSignals(True)
                self.wider_pockets_checkbox.setChecked(True)
                self.wider_pockets_checkbox.blockSignals(False)

            rows = 6

        elif self.wider_pockets_checkbox.isChecked():
            rows = 5

        else:
            rows = 4

        self.init_empty_grid(rows)

    def init_empty_grid(self, rows=4):
        inventory_items = []

        if self.player_data:
            inventory_items = self.player_data.get(
                "inventory",
                []
            ).copy()

        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

        self.slots.clear()

        for y in range(rows):
            for x in range(self.GRID_WIDTH):
                slot = InventorySlot(x, y, self)

                slot.setContextMenuPolicy(
                    Qt.CustomContextMenu
                )

                slot.customContextMenuRequested.connect(
                    lambda pos, s=slot:
                    self.show_slot_menu(pos, s)
                )

                slot.clicked.connect(
                    lambda checked=False, s=slot:
                    self.on_slot_clicked(s)
                )

                self.grid_layout.addWidget(
                    slot,
                    y,
                    x
                )

                self.slots[(x, y)] = slot

        for item in inventory_items:
            x = item.get("grid_x", 0)
            y = item.get("grid_y", 0)

            if (x, y) in self.slots:
                self.slots[(x, y)].set_item(item)

    def load_data(self, player_data):
        self.player_data = player_data

        uniques = player_data.get(
            "uniques",
            []
        )

        self.wider_pockets_checkbox.blockSignals(True)
        self.deeper_pockets_checkbox.blockSignals(True)

        if "invrows 6" in uniques:
            self.wider_pockets_checkbox.setChecked(True)
            self.deeper_pockets_checkbox.setChecked(True)

        elif "invrows 5" in uniques:
            self.wider_pockets_checkbox.setChecked(True)
            self.deeper_pockets_checkbox.setChecked(False)

        else:
            self.wider_pockets_checkbox.setChecked(False)
            self.deeper_pockets_checkbox.setChecked(False)

        self.wider_pockets_checkbox.blockSignals(False)
        self.deeper_pockets_checkbox.blockSignals(False)

        self.update_inventory_grid()

    def on_slot_clicked(self, slot: InventorySlot):
        """Standard left-click action on a slot."""
        if slot.item_data:
            self.edit_slot_item(slot)
        else:
            self.add_item_to_slot(slot)

    def show_slot_menu(self, position, slot: InventorySlot):
        """Right-click context menu options."""
        menu = QMenu()

        if slot.item_data:
            edit_action = menu.addAction("Edit Item")
            copy_action = menu.addAction("Copy Item")
            remove_action = menu.addAction("Remove Item")

            action = menu.exec(slot.mapToGlobal(position))

            if action == edit_action:
                self.edit_slot_item(slot)
            elif action == copy_action:
                self.copy_slot_item(slot)
            elif action == remove_action:
                self.remove_slot_item(slot)

        else:
            add_action = menu.addAction("Add Item Here")
            paste_action = menu.addAction("Paste Item")

            action = menu.exec(slot.mapToGlobal(position))

            if action == add_action:
                self.add_item_to_slot(slot)
            elif action == paste_action:
                self.paste_slot_item(slot)

    def edit_slot_item(self, slot: InventorySlot):
        dialog = ItemEditDialog(
            slot.item_data,
            self,
            self.get_inventory_rows()
        )
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.get_updated_data()
            slot.item_data.update(updated)
            slot.update_visuals()

    def remove_slot_item(self, slot: InventorySlot):
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete the item in slot ({slot.grid_x}, {slot.grid_y})?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            if slot.item_data in self.player_data["inventory"]:
                self.player_data["inventory"].remove(slot.item_data)
            slot.clear_item()

    def copy_slot_item(self, slot: InventorySlot):
        """Copy an inventory item to the system clipboard."""

        if not slot.item_data:
            return

        clipboard_data = {
            "valheim_editor": "inventory_item",
            "item": slot.item_data.copy()
        }

        clipboard_text = json.dumps(
            clipboard_data,
            ensure_ascii=False
        )

        QApplication.clipboard().setText(clipboard_text)

    def paste_slot_item(self, slot: InventorySlot):
        """Paste an inventory item from the system clipboard."""

        clipboard_text = QApplication.clipboard().text()

        try:
            clipboard_data = json.loads(clipboard_text)
        except (json.JSONDecodeError, TypeError):
            QMessageBox.warning(
                self,
                "Invalid Item",
                "The clipboard does not contain a valid VikingEditor item."
            )
            return

        if clipboard_data.get("valheim_editor") != "inventory_item":
            QMessageBox.warning(
                self,
                "Invalid Item",
                "The clipboard does not contain a VikingEditor item."
            )
            return

        item_data = clipboard_data.get("item")

        if not isinstance(item_data, dict):
            QMessageBox.warning(
                self,
                "Invalid Item",
                "The clipboard item data is invalid."
            )
            return

        pasted_item = item_data.copy()

        pasted_item["grid_x"] = slot.grid_x
        pasted_item["grid_y"] = slot.grid_y

        self.player_data["inventory"].append(pasted_item)
        slot.set_item(pasted_item)

    def add_item_to_slot(self, slot: InventorySlot):
        new_item = {
            "prefab": "",
            "stack": 1,
            "durability": 100.0,
            "grid_x": slot.grid_x,
            "grid_y": slot.grid_y,
            "equipped": False,
            "quality": 1,
            "variant": 0,
            "crafter_id": 0,
            "crafter_name": "",
            "custom_data": {},
            "world_level": 0,
            "picked_up": True
        }

        dialog = ItemEditDialog(
            new_item,
            self,
            self.get_inventory_rows()
        )
        if dialog.exec() == QDialog.Accepted:
            final_item = dialog.get_updated_data()
            new_item.update(final_item)
            
            self.player_data["inventory"].append(new_item)
            slot.set_item(new_item)

    def save_changes(self):
        if not self.player_data:
            return

        uniques = self.player_data.get(
            "uniques",
            []
        )

        uniques = [
            unique
            for unique in uniques
            if not (
                isinstance(unique, str)
                and (
                    unique.startswith("invrows ")
                    or re.fullmatch(r"invslot\d+", unique)
                )
            )
        ]

        if self.deeper_pockets_checkbox.isChecked():
            rows = 6
        elif self.wider_pockets_checkbox.isChecked():
            rows = 5
        else:
            rows = 4

        if rows > self.DEFAULT_GRID_HEIGHT:
            uniques.append(
                f"invrows {rows}"
            )

            for slot_number in range(
                1,
                rows - self.DEFAULT_GRID_HEIGHT + 1
            ):
                uniques.append(
                    f"invslot{slot_number}"
                )

        self.player_data["uniques"] = uniques
