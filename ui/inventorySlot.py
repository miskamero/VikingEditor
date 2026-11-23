from pathlib import Path
import re
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from subscripts.itemDatabase import get_item_icon_path
from PySide6.QtWidgets import (
    QToolButton,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSizePolicy,
)

def format_item_name(prefab):
    special_names = {
        "SwordIron": "Iron Sword",
        "SwordBronze": "Bronze Sword",
        "SwordSilver": "Silver Sword",
        "SwordBlackmetal": "Blackmetal Sword",
        "BowFineWood": "Finewood Bow",
        "BowHuntsman": "Huntsman Bow",
        "BowDraugrFang": "Draugr Fang",
        "PickaxeAntler": "Antler Pickaxe",
        "PickaxeBronze": "Bronze Pickaxe",
        "PickaxeIron": "Iron Pickaxe",
        "PickaxeStone": "Stone Pickaxe",
    }

    if prefab in special_names:
        return special_names[prefab]

    name = prefab

    if name.startswith("$item_"):
        name = name[6:]

    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", name)
    name = name.replace("_", " ")

    return name.title()

def get_item_icon(prefab):
    prefab_lower = prefab.lower()

    if "sword" in prefab_lower:
        return "sword.png"

    if "bow" in prefab_lower:
        return "bow.png"

    if "axe" in prefab_lower and "pickaxe" not in prefab_lower:
        return "axe.png"

    if "pickaxe" in prefab_lower:
        return "pickaxe.png"

    if "shield" in prefab_lower:
        return "shield.png"

    if "arrow" in prefab_lower:
        return "arrow.png"

    if any(word in prefab_lower for word in (
        "armor",
        "helmet",
        "cape",
        "chest",
        "legs",
        "shoulder",
        "tunic",
        "shirt",
        "hood",
        "hat",
        "cloak",
    )):
        return "armor.png"

    if any(word in prefab_lower for word in (
        "food",
        "meat",
        "fish",
        "berry",
        "mushroom",
        "honey",
        "bread",
        "cake",
        "stew",
    )):
        return "food.png"

    if any(word in prefab_lower for word in (
        "potion",
        "mead",
    )):
        return "potion.png"

    if any(word in prefab_lower for word in (
        "seed",
        "plant",
        "sapling",
        "carrot",
        "turnip",
        "onion",
    )):
        return "plant.png"

    if any(word in prefab_lower for word in (
        "hammer",
        "hoe",
        "cultivator",
        "torch",
        "fishingrod",
        "shovel",
        "knife",
        "rod",
    )):
        return "tool.png"

    if any(word in prefab_lower for word in (
        "ore",
        "ingot",
        "metal",
    )):
        return "metal.png"

    if any(word in prefab_lower for word in (
        "wood",
        "stone",
        "leather",
        "bone",
        "resin",
        "feather",
        "hide",
    )):
        return "material.png"

    return "❔"


class InventorySlot(QToolButton):
    # Match the dialog buttons without inheriting their minimum form-control height.
    STYLE = """
        QToolButton { padding: 0; background: white; color: #303438; border: 1px solid #d7dade; border-radius: 6px; }
        QToolButton[slotState="empty"] {
            background: #f8fafb; border: 1px solid #dfe4e5; color: transparent;
        }
        QToolButton[slotState="equipped"] { background: #eaf1e5; border-color: #a3b598; }
        QToolButton:enabled:hover { background: #f0f5ec; border: 1px solid #a3b598; color: #45623a; }
        QToolButton:enabled:focus { border: 2px solid #6d895b; color: #45623a; }
        QToolButton:enabled:pressed { background: #e3eddc; }
        QLabel#itemName { color: #303438; font-weight: 600; }
        QLabel#quality, QLabel#stack { color: #536348; font-weight: 600; }
        QLabel#missingIcon { color: #737c80; font-size: 20px; }
        QLabel#equippedMark, QLabel#cheatedMark { border-radius: 3px; font-weight: 600; }
        QLabel#equippedMark { color: white; background: #45623a; }
        QLabel#cheatedMark { color: #793b31; background: #f3e4de; }
    """

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.grid_x = x
        self.grid_y = y
        self.item_data = None
        self._display_name = ""
        self._icon = QPixmap()
        self._icon_size = 0

        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self.STYLE)

        self.icon_label = self.make_label("missingIcon")
        self.name_label = self.make_label("itemName")
        self.stack_label = self.make_label("stack", Qt.AlignLeft | Qt.AlignVCenter)
        self.quality_label = self.make_label("quality", Qt.AlignRight | Qt.AlignVCenter)
        self.equipped_label = self.make_label("equippedMark")
        self.cheated_label = self.make_label("cheatedMark")
        self.equipped_label.setText("✓")
        self.cheated_label.setText("×")
        for marker in (self.equipped_label, self.cheated_label):
            marker.setFixedSize(14, 14)
        self.icon_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(1)

        image_layout = QGridLayout()
        layout.addLayout(image_layout, 1)
        image_layout.addWidget(self.icon_label, 0, 0, 1, 2)
        image_layout.addWidget(self.equipped_label, 0, 0, Qt.AlignTop | Qt.AlignLeft)
        image_layout.addWidget(self.cheated_label, 0, 1, Qt.AlignTop | Qt.AlignRight)
        image_layout.setColumnStretch(0, 1)
        image_layout.setColumnStretch(1, 1)

        layout.addWidget(self.name_label)

        metadata_row = QWidget()
        metadata_row.setFixedHeight(16)
        metadata_row.setAttribute(Qt.WA_TransparentForMouseEvents)
        metadata = QHBoxLayout(metadata_row)
        metadata.setContentsMargins(0, 0, 0, 0)
        metadata.setSpacing(4)
        for label in (self.stack_label, self.quality_label):
            metadata.addWidget(label, 1)
        layout.addWidget(metadata_row)

        self.set_slot_size(82)
        self.update_visuals()

    def make_label(self, name, alignment=Qt.AlignCenter):
        label = QLabel()
        label.setObjectName(name)
        label.setAlignment(alignment)
        label.setTextFormat(Qt.PlainText)
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        return label

    def set_slot_size(self, size):
        if self.width() == size and self.height() == size:
            return
        self.setFixedSize(size, size)
        self.fit_contents()

    def fit_contents(self):
        if not self.item_data:
            return

        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        metrics = self.name_label.fontMetrics()
        name = self._display_name
        if metrics.horizontalAdvance(name) > width:
            # Break at a word boundary, or within a single long prefab token.
            end = 1
            while end < len(name) and metrics.horizontalAdvance(name[:end + 1]) <= width:
                end += 1
            split = name.rfind(" ", 1, end + 1)
            if split < 0:
                split = end
            name = name[:split] + "\n" + metrics.elidedText(name[split:].lstrip(), Qt.ElideRight, width)
        self.name_label.setFixedHeight(metrics.lineSpacing() * (1 + name.count("\n")) + 1)
        self.name_label.setText(name)

        stack = self.item_data.get("stack", 1)
        quality = self.item_data.get("quality", 1)
        # Give each value the space it needs up to half the row when both
        # are long. Short values leave more room for the other label.
        stack_text = f"×{stack:,}" if stack > 1 else ""
        quality_text = f"{quality}★" if quality > 1 else ""
        self.stack_label.setVisible(bool(stack_text))
        self.quality_label.setVisible(bool(quality_text))
        if stack_text and quality_text:
            available = width - 4
            stack_width = self.stack_label.fontMetrics().horizontalAdvance(stack_text)
            quality_width = self.quality_label.fontMetrics().horizontalAdvance(quality_text)
            stack_width = min(stack_width, available - min(quality_width, available // 2))
            self.stack_label.setFixedWidth(stack_width)
            self.quality_label.setFixedWidth(available - stack_width)
        else:
            self.stack_label.setFixedWidth(width)
            self.quality_label.setFixedWidth(width)
        for label, value in ((self.stack_label, stack_text), (self.quality_label, quality_text)):
            label.setText(label.fontMetrics().elidedText(value, Qt.ElideRight, label.width()))

        icon_size = max(16, self.height() - margins.top() - margins.bottom() - self.name_label.height() - 18)
        if not self._icon.isNull() and self._icon_size != icon_size:
            self._icon_size = icon_size
            ratio = self.devicePixelRatioF()
            pixmap = self._icon.scaled(round(icon_size * ratio), round(icon_size * ratio),
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
            self.icon_label.setPixmap(pixmap)

    def set_item(self, item_data):
        self.item_data = item_data
        self.update_visuals()

    def clear_item(self):
        self.set_item(None)

    def update_visuals(self):
        item = self.item_data or {}
        equipped = item.get("equipped", False)
        cheated = item.get("cheated", False)
        state = "equipped" if equipped else "occupied" if item else "empty"
        if self.property("slotState") != state:
            self.setProperty("slotState", state)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

        self.setText("" if item else "+")
        self.icon_label.setVisible(bool(item))
        self.name_label.setVisible(bool(item))
        self.equipped_label.setVisible(bool(equipped))
        self.cheated_label.setVisible(bool(cheated))
        if not item:
            self._icon = QPixmap()
            for label in (self.icon_label, self.name_label, self.stack_label, self.quality_label):
                label.clear()
                label.hide()
            self.setToolTip("Empty slot — click to add an item.")
            self.setAccessibleName(f"Empty slot, column {self.grid_x + 1}, row {self.grid_y + 1}")
            self.setAccessibleDescription("")
            return

        prefab = item.get("prefab") or ""
        self._display_name = format_item_name(prefab) if prefab else "Unknown item"
        details = self._display_name if prefab else f"Unknown item (ID: {item.get('prefab_hash', '?')})"
        cached_icon = get_item_icon_path(prefab, item.get("variant", 0))
        self._icon = QPixmap(str(cached_icon)) if cached_icon else QPixmap()
        if self._icon.isNull():
            filename = get_item_icon(prefab)
            if filename != "❔":
                self._icon = QPixmap(str(Path(__file__).resolve().parent.parent / "assets" / filename))
        self._icon_size = 0
        if self._icon.isNull():
            self.icon_label.setText("?")
        self.fit_contents()
        self.setToolTip(
            f"{details}\n"
            f"Stack: {item.get('stack', 1)}\n"
            f"Quality: {item.get('quality', 1)}\n"
            f"Equipped: {'Yes' if equipped else 'No'}\n"
            f"Spawned in with cheats: {'Yes' if cheated else 'No'}"
        )
        self.setAccessibleName(details)
        self.setAccessibleDescription(self.toolTip())
