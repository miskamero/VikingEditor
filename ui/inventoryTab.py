import json
from collections import defaultdict

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

from PySide6.QtCore import QEvent, QSignalBlocker, Qt

from ui.inventorySlot import InventorySlot
from ui.tabStyle import DETAIL_STYLE
from ui.theme import set_themed_style
from ui.itemEditDialog import ItemEditDialog
from subscripts.equipmentSlots import eaq_equipment, eaq_inventory_rows, has_slot_mod_data, item_has_slot_mod_data
from subscripts.inventoryLayout import (
    DEFAULT_GRID_HEIGHT, GRID_WIDTH, effective_inventory_rows, is_playable_position,
    pockets_are_editable, resize_pocket_keys,
)
from subscripts.itemValidation import EQUIPMENT_PROPERTY_LIMITS, validate_item, validate_clipboard_item
from subscripts.playerDataUtil import item_is_cheated

class InventoryTab(QWidget):
    GRID_WIDTH = GRID_WIDTH
    DEFAULT_GRID_HEIGHT = DEFAULT_GRID_HEIGHT
    MIN_SLOT_SIZE = 82
    MAX_SLOT_SIZE = 110
    TOOLBAR_SPACING = 12
    inventory_version = 110

    def __init__(self):
        super().__init__()
        self.player_data = None
        self._eaq_rows = None
        self._rows = DEFAULT_GRID_HEIGHT
        self._loaded_rows = DEFAULT_GRID_HEIGHT
        self._can_resize = False
        self._mod_storage = False
        self._ambiguous_layout = False
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

        overview = QBoxLayout(QBoxLayout.LeftToRight)
        self.dimensions_label = QLabel()
        self.dimensions_label.setWordWrap(True)
        overview.addWidget(self.dimensions_label, 1)
        self.review_positions_button = QPushButton()
        self.review_positions_button.clicked.connect(self.review_stored_positions)
        overview.addWidget(self.review_positions_button)
        self.main_layout.addLayout(overview)

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
        return min(self._rows, self._eaq_rows) if self._eaq_rows is not None else self._rows

    def set_pocket_checks(self):
        with QSignalBlocker(self.wider_pockets_checkbox), QSignalBlocker(self.deeper_pockets_checkbox):
            self.wider_pockets_checkbox.setChecked(self._rows in (5, 6))
            self.deeper_pockets_checkbox.setChecked(self._rows == 6)

    def handle_wider_pockets(self, state):
        if not state and self.deeper_pockets_checkbox.isChecked():
            with QSignalBlocker(self.deeper_pockets_checkbox):
                self.deeper_pockets_checkbox.setChecked(False)
        self.update_inventory_grid()

    def update_inventory_grid(self):
        if not self._can_resize:
            self.set_pocket_checks()
            return
        target = 4
        if self.deeper_pockets_checkbox.isChecked():
            target = 6
        elif self.wider_pockets_checkbox.isChecked():
            target = 5
        # Adding an explicit invrows key can start the game's invalid-item
        # drop path even when the requested height is an increase.
        affected = self.items_outside_rows(target) if target != self._rows else []
        if affected:
            self.set_pocket_checks()
            self.show_resize_blockers(target, affected)
            return
        self._rows = target
        self.set_pocket_checks()
        self.init_empty_grid()

    def stored_items(self):
        return (self.player_data or {}).get("inventory", [])

    def items_outside_rows(self, rows):
        return [(index, item) for index, item in enumerate(self.stored_items(), 1)
                if not is_playable_position(item.get("grid_x"), item.get("grid_y"), rows)]

    @staticmethod
    def describe_item(index, item):
        name = item.get("prefab") or f"Unknown item (hash {item.get('prefab_hash', 0)})"
        return f"Record {index} at ({item.get('grid_x')}, {item.get('grid_y')}) · {name}"

    def show_resize_blockers(self, rows, affected):
        details = [self.describe_item(index, item) for index, item in affected]
        action = "Shrinking" if rows < self._rows else "Resizing"
        message = (
            f"{action} to {rows} rows would leave {len(details)} stored item(s) outside the playable grid. "
            "The current rows were kept. Remove affected items deliberately or choose a size that fits them.\n\n"
            + "\n".join(details[:5])
        )
        dialog = QMessageBox(QMessageBox.Warning, "Cannot Resize Inventory", message, QMessageBox.Ok, self)
        dialog.setTextFormat(Qt.PlainText)
        if len(details) > 5:
            dialog.setDetailedText("\n".join(details))
        dialog.exec()

    def group_by_position(self):
        positions = defaultdict(list)
        for index, item in enumerate(self.stored_items(), 1):
            positions[item.get("grid_x"), item.get("grid_y")].append((index, item))
        return positions

    def reportable_positions(self, positions):
        rows = self.get_inventory_rows()
        for (x, y), records in positions.items():
            reasons = []
            if not is_playable_position(x, y, rows):
                reasons.append("Outside the ordinary grid")
            if len(records) > 1:
                reasons.append("Multiple stored items")
            if any(item_has_slot_mod_data(item) for _, item in records):
                reasons.append("Slot-mod metadata")
            if reasons:
                yield " · ".join(reasons), records

    def review_stored_positions(self):
        groups = self.reportable_positions(self.group_by_position())
        lines = [f"{self.describe_item(index, item)} — {reason}"
                 for reason, records in groups for index, item in records]
        if lines:
            dialog = QMessageBox(
                QMessageBox.Information, "Stored Inventory Positions",
                "These records are kept at their saved coordinates. Coordinates start at zero.",
                QMessageBox.Ok, self,
            )
            dialog.setDetailedText("\n".join(lines))
            dialog.exec()

    def init_empty_grid(self, refresh=False):
        rows = self.get_inventory_rows()
        positions = self.group_by_position()

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
            records = positions.get(position, [])
            if len(records) > 1:
                slot.setEnabled(False)
                details = "\n".join(self.describe_item(index, item) for index, item in records[:5])
                slot.set_restricted(f"{len(records)} items", f"Multiple items share this cell.\n{details}")
            elif records and item_has_slot_mod_data(records[0][1]):
                slot.setEnabled(False)
                slot.set_restricted("Mod slot", self.describe_item(*records[0]) + "\nSlot ownership is protected.")
            elif not records and self._ambiguous_layout:
                slot.setEnabled(False)
                slot.set_restricted("Read only", "The saved slot-mod layout could not be established.")
            else:
                slot.setEnabled(True)
                item = records[0][1] if records else None
                if refresh or slot.item_data is not item or slot.restriction:
                    slot.set_item(item)
        status = f"Valheim grid · {self.GRID_WIDTH} columns × {self._rows} rows"
        if self._eaq_rows is not None:
            status += f" · Saved slot-mod boundary: {self._eaq_rows} rows"
        if rows != self._rows:
            status += f" · Editable rows: {rows}"
        if self._ambiguous_layout:
            status += " · Slot-mod layout unverified. Placement and removal are disabled."
        self.dimensions_label.setText(status)
        count = sum(len(records) for _, records in self.reportable_positions(positions))
        self.review_positions_button.setText(f"Review Stored Positions ({count})")
        self.review_positions_button.setVisible(bool(count))

    def load_data(self, player_data, root_save=None):
        self.player_data = player_data
        self.inventory_version = player_data.get("inventory_version", 109)
        self._eaq_rows = eaq_inventory_rows(player_data)
        self._mod_storage = has_slot_mod_data(player_data)
        self._ambiguous_layout = self._mod_storage and self._eaq_rows is None
        uniques = player_data.get("uniques", [])
        self._rows = self._loaded_rows = effective_inventory_rows(uniques)
        self._can_resize = not self._mod_storage and pockets_are_editable(uniques)
        self.set_pocket_checks()
        self.init_empty_grid(refresh=True)
        for control in (self.wider_pockets_checkbox, self.deeper_pockets_checkbox):
            control.setEnabled(self._can_resize)
            if self._mod_storage:
                control.setToolTip("Inventory dimensions are preserved while slot-mod data is present.")
            elif not self._can_resize:
                control.setToolTip("The unusual or ambiguous pocket metadata is preserved. Pocket changes are disabled.")
            else:
                control.setToolTip("")
        self.clear_cheated_button.setEnabled(self.inventory_version == 110 and not self._mod_storage)
        if self.inventory_version == 109:
            tooltip = "Valheim ignores the extra flag byte in Inventory 109. The byte is preserved."
        elif self._mod_storage:
            tooltip = "Bulk changes are disabled to preserve slot-mod items. Edit recognized items individually."
        else:
            tooltip = "Clear saved item cheat flags on unambiguous records. Valheim can reapply them based on item properties."
        self.clear_cheated_button.setToolTip(tooltip)
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
            editable = not validate_item(item, inventory_rows=item["grid_y"] + 1) and all(
                key not in item or lower <= item[key] <= upper
                for key, (lower, upper) in EQUIPMENT_PROPERTY_LIMITS.items()
            )
            slot.setEnabled(editable)
            if not editable:
                slot.setToolTip(slot.toolTip() + "\nPreserved read-only: this item cannot be safely edited.")
            slot.clicked.connect(lambda checked=False, s=slot: self.edit_equipment_item(s))

    def edit_equipment_item(self, slot):
        if slot not in self.equipment_slots or not slot.isEnabled():
            return
        player_data = self.player_data
        original = slot.item_data
        dialog = ItemEditDialog(
            original, self, original["grid_y"] + 1, inventory_version=self.inventory_version, equipment=True,
        )
        try:
            # Slot-type checks depend on the mod's runtime definitions. Keep the
            # identity and residence flags; reuse property editing only.
            dialog.prefab_input.setEnabled(False)
            dialog.stack_input.setEnabled(False)
            dialog.equipped_input.setEnabled(False)
            if (dialog.exec() == QDialog.Accepted and self.player_data is player_data
                    and slot in self.equipment_slots and slot.item_data is original
                    and self.record_matches_slot(slot)):
                allowed = {"quality", "durability", "variant", "cheated", "crafter_id", "crafter_name"}
                original.update((key, value) for key, value in dialog.get_changes().items() if key in allowed)
                slot.update_visuals()
        finally:
            dialog.deleteLater()

    def clear_all_cheated_flags(self):
        if not self.player_data or self.inventory_version != 110 or self._mod_storage:
            return

        player_data = self.player_data
        flagged_items = [records[0][1] for records in self.group_by_position().values()
                         if len(records) == 1 and item_is_cheated(records[0][1], self.inventory_version)]
        if not flagged_items:
            QMessageBox.information(
                self, "Clear Cheated Flags",
                "No editable item has the saved cheat flag set."
            )
            return

        confirm = QMessageBox.question(
            self, "Confirm Clear Cheated Flags",
            f"Clear the cheated flag from {len(flagged_items)} item(s)? Conflicting records will be preserved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes or self.player_data is not player_data:
            return

        selected = {id(item) for item in flagged_items}
        if not has_slot_mod_data(player_data):
            for records in self.group_by_position().values():
                if len(records) == 1 and id(records[0][1]) in selected:
                    records[0][1]["cheated"] = False
        self.init_empty_grid(refresh=True)

    def on_slot_button_clicked(self, checked=False):
        self.on_slot_clicked(self.sender())

    def on_slot_context_menu(self, position):
        self.show_slot_menu(position, self.sender())

    def record_matches_slot(self, slot):
        records = [item for item in self.stored_items()
                   if (item.get("grid_x"), item.get("grid_y")) == (slot.grid_x, slot.grid_y)]
        if not records:
            return slot.item_data is None
        return len(records) == 1 and records[0] is slot.item_data

    def is_current_slot(self, slot):
        if self.player_data is None or slot is None:
            return False
        position = slot.grid_x, slot.grid_y
        if (self.slots.get(position) is not slot or not slot.isEnabled() or slot.restriction
                or not is_playable_position(*position, self.get_inventory_rows())):
            return False
        if not self.record_matches_slot(slot) or (slot.item_data and item_has_slot_mod_data(slot.item_data)):
            self.init_empty_grid()
            return False
        return True

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
            remove_action = None if self._ambiguous_layout else menu.addAction("Remove Item")

            action = menu.exec(slot.mapToGlobal(position))

            if action == edit_action:
                self.edit_slot_item(slot)
            elif action == copy_action:
                self.copy_slot_item(slot)
            elif remove_action is not None and action == remove_action:
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
            self.get_inventory_rows(),
            inventory_version=self.inventory_version,
        )
        try:
            if self._ambiguous_layout:
                dialog.prefab_input.setEnabled(False)
                dialog.equipped_input.setEnabled(False)
            if (dialog.exec() == QDialog.Accepted
                    and self.player_data is player_data
                    and self.is_current_slot(slot) and slot.item_data is original_item):
                changes = dialog.get_changes()
                if self._ambiguous_layout:
                    for key in ("prefab", "prefab_hash", "equipped"):
                        changes.pop(key, None)
                original_item.update(changes)
                slot.update_visuals()
        finally:
            dialog.deleteLater()

    def remove_slot_item(self, slot: InventorySlot):
        if self._ambiguous_layout or not self.is_current_slot(slot) or not slot.item_data:
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
            self.init_empty_grid()

    def copy_slot_item(self, slot: InventorySlot):
        """Copy an inventory item to the system clipboard."""

        if not self.is_current_slot(slot) or not slot.item_data:
            return

        clipboard_data = {
            "valheim_editor": "inventory_item",
            "inventory_version": self.inventory_version,
            "item": slot.item_data.copy()
        }

        clipboard_text = json.dumps(
            clipboard_data,
            ensure_ascii=False
        )

        QApplication.clipboard().setText(clipboard_text)

    def paste_slot_item(self, slot: InventorySlot):
        """Paste an inventory item from the system clipboard."""

        if self._ambiguous_layout or not self.is_current_slot(slot) or slot.item_data:
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
        if item_has_slot_mod_data(pasted_item):
            QMessageBox.warning(self, "Protected Mod Item", "Items with slot-mod metadata cannot be placed in an ordinary cell.")
            return

        source_version = clipboard_data.get("inventory_version")
        if source_version is not None and (type(source_version) is not int or source_version not in (109, 110)):
            QMessageBox.warning(self, "Invalid Item", "The clipboard item has an unsupported inventory version.")
            return
        raw_low_bit = pasted_item.get("cheated_flags", 0) & 1
        active_flag = item_is_cheated(pasted_item, 110)
        if source_version is None:
            if self.inventory_version == 110 and "cheated_flags" in pasted_item and (raw_low_bit or active_flag):
                QMessageBox.warning(self, "Unknown Inventory Version",
                                    "Copy this item again so VikingEditor can identify the saved flag's meaning.")
                return
        elif source_version != self.inventory_version and (raw_low_bit or (source_version == 110 and active_flag)):
            QMessageBox.warning(self, "Incompatible Item Flag",
                                "This item has a flag that cannot be carried across these inventory versions.")
            return
        if self.inventory_version == 109:
            pasted_item["cheated"] = False

        self.player_data["inventory"].append(pasted_item)
        self.init_empty_grid()

    def add_item_to_slot(self, slot: InventorySlot):
        if self._ambiguous_layout or not self.is_current_slot(slot) or slot.item_data:
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
            self.get_inventory_rows(),
            inventory_version=self.inventory_version,
        )
        try:
            if (dialog.exec() == QDialog.Accepted
                    and self.player_data is player_data
                    and not self._ambiguous_layout and self.is_current_slot(slot) and not slot.item_data):
                new_item.update(dialog.get_changes())
                player_data["inventory"].append(new_item)
                self.init_empty_grid()
        finally:
            dialog.deleteLater()

    def save_changes(self):
        if not self.player_data or self._rows == self._loaded_rows:
            return True

        uniques = self.player_data.get("uniques", [])
        if (has_slot_mod_data(self.player_data) or not pockets_are_editable(uniques)
                or effective_inventory_rows(uniques) != self._loaded_rows):
            QMessageBox.warning(self, "Cannot Resize Inventory", "The saved inventory layout has changed.")
            return False
        if affected := self.items_outside_rows(self._rows):
            target = self._rows
            self._rows = self._loaded_rows
            self.set_pocket_checks()
            self.init_empty_grid()
            self.show_resize_blockers(target, affected)
            return False

        self.player_data["uniques"] = resize_pocket_keys(uniques, self._loaded_rows, self._rows)
        self._loaded_rows = self._rows
        return True
