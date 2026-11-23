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
    QBoxLayout,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStyle,
)

from PySide6.QtCore import QEvent, Qt

from ui.inventorySlot import InventorySlot
from ui.tabStyle import DETAIL_STYLE
from ui.theme import set_themed_style
from ui.itemEditDialog import ItemEditDialog
from subscripts.equipmentSlots import eaq_equipment, eaq_inventory_rows, has_slot_mod_data
from subscripts.itemValidation import validate_item, validate_clipboard_item

class InventoryTab(QWidget):
    GRID_WIDTH = 8
    DEFAULT_GRID_HEIGHT = 4
    MIN_SLOT_SIZE = 82
    MAX_SLOT_SIZE = 110
    TOOLBAR_SPACING = 12

    def __init__(self):
        super().__init__()
        self.player_data = None
        self._eaq_rows = None
        self.slots = {}
        self.equipment_slots = []
        self._slot_size = self.MIN_SLOT_SIZE
        self.setObjectName("detailPage")
        self.setAttribute(Qt.WA_StyledBackground)
        set_themed_style(self, DETAIL_STYLE)

        page = QBoxLayout(QBoxLayout.LeftToRight, self)
        page.setContentsMargins(20, 18, 20, 18)
        page.setSpacing(0)
        column = QWidget()
        page.addStretch()
        page.addWidget(column, 1)
        page.addStretch()
        outer_layout = QVBoxLayout(column)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(12)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setObjectName("detailContent")
        self.main_layout = QVBoxLayout(content)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)
        self.main_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.scroll_area.setWidget(content)
        content.setAutoFillBackground(False)
        self.scroll_area.viewport().setAutoFillBackground(False)

        self.toolbar = QWidget()
        self.toolbar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.upgrade_layout = QBoxLayout(QBoxLayout.LeftToRight, self.toolbar)
        self.upgrade_layout.setContentsMargins(0, 0, 0, 0)
        self.upgrade_layout.setSpacing(self.TOOLBAR_SPACING)

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

        self.clear_cheated_button = QPushButton("Clear All Cheated Flags")
        self.clear_cheated_button.setToolTip(
            "Remove the 'spawned in with cheats' flag from every inventory item."
        )
        self.clear_cheated_button.setEnabled(False)
        self.clear_cheated_button.clicked.connect(self.clear_all_cheated_flags)
        self.upgrade_layout.addWidget(self.clear_cheated_button)
        self.upgrade_layout.insertStretch(2)
        for control in (self.wider_pockets_checkbox, self.deeper_pockets_checkbox, self.clear_cheated_button):
            self.upgrade_layout.setAlignment(control, Qt.AlignLeft)

        outer_layout.addWidget(self.toolbar)
        outer_layout.addWidget(self.scroll_area, 1)

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(6)
        self.main_layout.addLayout(self.grid_layout)
        grid_width = self.GRID_WIDTH * self.MAX_SLOT_SIZE + (self.GRID_WIDTH - 1) * self.grid_layout.spacing()
        column.setMaximumWidth(grid_width + self.scrollbar_gutter())
        
        self.equipment_group = QGroupBox("Mod equipment")
        # Eight equipped cells can span the same columns as the backpack.
        self.equipment_group.setStyleSheet("QGroupBox { padding-left: 0; padding-right: 0; border-left: none; border-right: none; }")
        self.equipment_layout = QGridLayout(self.equipment_group)
        self.equipment_layout.setContentsMargins(0, 6, 0, 6)
        self.equipment_layout.setHorizontalSpacing(self.grid_layout.horizontalSpacing())
        self.main_layout.addWidget(self.equipment_group)
        self.equipment_group.hide()

        self.wider_pockets_checkbox.stateChanged.connect(
            self.handle_wider_pockets
        )
        self.deeper_pockets_checkbox.stateChanged.connect(
            self.update_inventory_grid
        )

        self.init_empty_grid()
        self.scroll_area.viewport().installEventFilter(self)
        self.toolbar.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            if watched is self.scroll_area.viewport():
                self.resize_slots()
            elif watched is self.toolbar:
                self.fit_toolbar()
        return super().eventFilter(watched, event)

    def scrollbar_gutter(self):
        spacing = self.scroll_area.style().pixelMetric(QStyle.PM_ScrollView_ScrollBarSpacing, None, self.scroll_area)
        return self.scroll_area.verticalScrollBar().sizeHint().width() + max(0, spacing)

    def fit_toolbar(self):
        controls = (self.wider_pockets_checkbox, self.deeper_pockets_checkbox, self.clear_cheated_button)
        widths = [control.sizeHint().width() for control in controls]
        self.toolbar.setMinimumWidth(max(widths))
        row_width = sum(widths) + self.TOOLBAR_SPACING * (len(widths) - 1)
        if self.toolbar.width() < row_width:
            self.upgrade_layout.setDirection(QBoxLayout.TopToBottom)
            self.upgrade_layout.setSpacing(4)
        else:
            self.upgrade_layout.setDirection(QBoxLayout.LeftToRight)
            self.upgrade_layout.setSpacing(self.TOOLBAR_SPACING)

    def resize_slots(self):
        # Reserve the scrollbar gutter even for short inventories. Row count
        # can then change without affecting the sizing calculation.
        width = self.scroll_area.width() - self.scrollbar_gutter()
        width -= self.grid_layout.horizontalSpacing() * (self.GRID_WIDTH - 1)
        size = max(self.MIN_SLOT_SIZE, min(self.MAX_SLOT_SIZE, width // self.GRID_WIDTH))
        if size != self._slot_size:
            self._slot_size = size
            for slot in (*self.slots.values(), *self.equipment_slots):
                slot.set_slot_size(size)

    def get_inventory_rows(self):
        if self.deeper_pockets_checkbox.isChecked():
            rows = 6
        elif self.wider_pockets_checkbox.isChecked():
            rows = 5
        else:
            rows = 4
        return min(rows, self._eaq_rows) if self._eaq_rows is not None else rows

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

        self.init_empty_grid(self.get_inventory_rows())

    def init_empty_grid(self, rows=DEFAULT_GRID_HEIGHT, refresh=False):
        items = (self.player_data or {}).get("inventory", [])
        items_by_position = {(item.get("grid_x", 0), item.get("grid_y", 0)): item for item in items}

        # Keep the widgets and focus for rows that remain in the inventory.
        for position, slot in list(self.slots.items()):
            if position[1] >= rows:
                self.grid_layout.removeWidget(slot)
                slot.hide()
                slot.clicked.disconnect()
                slot.customContextMenuRequested.disconnect()
                slot.deleteLater()
                del self.slots[position]

        for y in range(rows):
            for x in range(self.GRID_WIDTH):
                if (x, y) in self.slots:
                    continue
                slot = InventorySlot(x, y, self)
                slot.set_slot_size(self._slot_size)

                slot.setContextMenuPolicy(
                    Qt.CustomContextMenu
                )

                slot.customContextMenuRequested.connect(
                    self.on_slot_context_menu
                )

                slot.clicked.connect(
                    self.on_slot_button_clicked
                )

                self.grid_layout.addWidget(
                    slot,
                    y,
                    x
                )

                self.slots[(x, y)] = slot

        for position, slot in self.slots.items():
            if refresh:
                slot.setEnabled(True)
            item = items_by_position.get(position)
            if slot.isEnabledTo(self) and (refresh or slot.item_data is not item):
                slot.set_item(item)

    def load_data(self, player_data, root_save=None):
        self.player_data = player_data
        self._eaq_rows = eaq_inventory_rows(player_data)
        self.clear_cheated_button.setEnabled(True)

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

        self.init_empty_grid(self.get_inventory_rows(), refresh=True)
        self._loaded_pockets = (self.wider_pockets_checkbox.isChecked(), self.deeper_pockets_checkbox.isChecked())
        self._mod_storage = has_slot_mod_data(player_data)
        for control in (self.wider_pockets_checkbox, self.deeper_pockets_checkbox, self.clear_cheated_button):
            control.setEnabled(not self._mod_storage)
        for control in (self.wider_pockets_checkbox, self.deeper_pockets_checkbox):
            control.setToolTip("Inventory dimensions are preserved while slot-mod data is present." if self._mod_storage else "")
        self.clear_cheated_button.setToolTip(
            "Bulk changes are disabled to preserve slot-mod items. Edit recognized items individually."
            if self._mod_storage else "Remove the 'spawned in with cheats' flag from every inventory item."
        )
        self.load_equipment(root_save)

    def load_equipment(self, root_save):
        self.equipment_slots = []
        while self.equipment_layout.count():
            widget = self.equipment_layout.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        equipment = eaq_equipment(self.player_data, root_save)
        self.equipment_group.setVisible(bool(equipment))
        if not equipment:
            return
        description = QLabel(
            "EquipmentAndQuickSlots — saved equipment. Item type, position and equipped state are kept."
        )
        description.setWordWrap(True)
        self.equipment_layout.addWidget(description, 0, 0, 1, 8)
        for column, (name, item) in enumerate(equipment):
            label = QLabel({"Helmet": "Head", "Shoulder": "Back", "Utility2": "Utility 2", "Utility3": "Utility 3"}.get(name, name))
            label.setAlignment(Qt.AlignCenter)
            self.equipment_layout.addWidget(label, 1, column)
            slot = InventorySlot(item["grid_x"], item["grid_y"], self)
            slot.set_slot_size(self._slot_size)
            slot.set_item(item)
            self.equipment_slots.append(slot)
            self.equipment_layout.addWidget(slot, 2, column)
            # Unsupported prefab IDs or properties remain visible and untouched.
            editable = not validate_item(item, inventory_rows=item["grid_y"] + 1)
            slot.setEnabled(editable)
            if not editable:
                slot.setToolTip(slot.toolTip() + "\nPreserved read-only: this item cannot be safely edited.")
            slot.clicked.connect(lambda checked=False, s=slot: self.edit_equipment_item(s))
            normal_slot = self.slots.get((item["grid_x"], item["grid_y"]))
            if normal_slot is not None:
                normal_slot.clear_item()
                normal_slot.setEnabled(False)

    def edit_equipment_item(self, slot):
        if slot not in self.equipment_slots or not slot.isEnabled():
            return
        player_data = self.player_data
        original = slot.item_data
        dialog = ItemEditDialog(original, self, original["grid_y"] + 1)
        try:
            # Slot-type checks depend on the mod's runtime definitions. Keep the
            # identity and residence flags; reuse property editing only.
            dialog.prefab_input.setEnabled(False)
            dialog.stack_input.setEnabled(False)
            dialog.equipped_input.setEnabled(False)
            baseline = dialog.get_updated_data()
            if (dialog.exec() == QDialog.Accepted and self.player_data is player_data
                    and slot in self.equipment_slots and slot.item_data is original
                    and any(item is original for item in player_data["inventory"])):
                updated = dialog.get_updated_data()
                for key in ("quality", "durability", "variant", "cheated", "crafter_id", "crafter_name"):
                    if updated[key] != baseline[key]:
                        original[key] = updated[key]
                slot.update_visuals()
        finally:
            dialog.deleteLater()

    def clear_all_cheated_flags(self):
        if not self.player_data or getattr(self, "_mod_storage", False):
            return

        flagged_items = [
            item for item in self.player_data.get("inventory", [])
            if item.get("cheated", False)
        ]
        if not flagged_items:
            QMessageBox.information(
                self, "Clear Cheated Flags",
                "No items have the cheated flag set."
            )
            return

        confirm = QMessageBox.question(
            self, "Confirm Clear Cheated Flags",
            f"Clear the cheated flag from {len(flagged_items)} item(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        for item in flagged_items:
            item["cheated"] = False
        for slot in self.slots.values():
            if slot.item_data:
                slot.update_visuals()

    def on_slot_button_clicked(self, checked=False):
        self.on_slot_clicked(self.sender())

    def on_slot_context_menu(self, position):
        self.show_slot_menu(position, self.sender())

    def is_current_slot(self, slot):
        return (self.player_data is not None and slot is not None
                and slot.isEnabled()
                and self.slots.get((slot.grid_x, slot.grid_y)) is slot)

    def on_slot_clicked(self, slot: InventorySlot):
        """Standard left-click action on a slot."""
        if not self.is_current_slot(slot):
            return
        if slot.item_data:
            self.edit_slot_item(slot)
        else:
            self.add_item_to_slot(slot)

    def show_slot_menu(self, position, slot: InventorySlot):
        """Right-click context menu options."""
        if not self.is_current_slot(slot):
            return
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
        if not self.is_current_slot(slot) or not slot.item_data:
            return
        player_data = self.player_data
        original_item = slot.item_data
        dialog = ItemEditDialog(
            slot.item_data,
            self,
            self.get_inventory_rows()
        )
        try:
            if (dialog.exec() == QDialog.Accepted
                    and self.player_data is player_data
                    and self.is_current_slot(slot) and slot.item_data is original_item):
                updated = dialog.get_updated_data()
                original_item.update(updated)
                slot.update_visuals()
        finally:
            dialog.deleteLater()

    def remove_slot_item(self, slot: InventorySlot):
        if not self.is_current_slot(slot) or not slot.item_data:
            return
        player_data, original = self.player_data, slot.item_data
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete the item in slot ({slot.grid_x}, {slot.grid_y})?",
            QMessageBox.Yes | QMessageBox.No
        )
        if (confirm == QMessageBox.Yes and self.player_data is player_data
                and self.is_current_slot(slot) and slot.item_data is original):
            for index, item in enumerate(player_data["inventory"]):
                if item is original:
                    del player_data["inventory"][index]
                    break
            slot.clear_item()

    def copy_slot_item(self, slot: InventorySlot):
        """Copy an inventory item to the system clipboard."""

        if not self.is_current_slot(slot) or not slot.item_data:
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

        if not self.is_current_slot(slot) or slot.item_data:
            return

        clipboard_text = QApplication.clipboard().text()

        try:
            clipboard_data = json.loads(clipboard_text)
        except (ValueError, RecursionError):
            QMessageBox.warning(
                self,
                "Invalid Item",
                "The clipboard does not contain a valid VikingEditor item."
            )
            return

        if not isinstance(clipboard_data, dict) or clipboard_data.get("valheim_editor") != "inventory_item":
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

        errors = validate_clipboard_item(pasted_item, self.get_inventory_rows())
        if errors:
            QMessageBox.warning(self, "Invalid Item", "\n".join(errors))
            return

        self.player_data["inventory"].append(pasted_item)
        slot.set_item(pasted_item)

    def add_item_to_slot(self, slot: InventorySlot):
        if not self.is_current_slot(slot) or slot.item_data:
            return
        player_data = self.player_data
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
            "picked_up": True,
            "cheated": False
        }

        dialog = ItemEditDialog(
            new_item,
            self,
            self.get_inventory_rows()
        )
        try:
            if (dialog.exec() == QDialog.Accepted
                    and self.player_data is player_data
                    and self.is_current_slot(slot) and not slot.item_data):
                final_item = dialog.get_updated_data()
                new_item.update(final_item)
                player_data["inventory"].append(new_item)
                slot.set_item(new_item)
        finally:
            dialog.deleteLater()

    def save_changes(self):
        if not self.player_data:
            return
        if (getattr(self, "_mod_storage", False)
                or (self.wider_pockets_checkbox.isChecked(), self.deeper_pockets_checkbox.isChecked())
                == getattr(self, "_loaded_pockets", None)):
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
        self._loaded_pockets = (self.wider_pockets_checkbox.isChecked(), self.deeper_pockets_checkbox.isChecked())
