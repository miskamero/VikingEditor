from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
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

    # misc
    return "❓"

def wrap_long_word(word, max_length=18):
    if len(word) <= max_length:
        return word

    split_at = round(len(word) * 0.50)

    return (
        word[:split_at] + "-\n" +
        word[split_at:]
    )

class InventorySlot(QPushButton):
    def __init__(self, x, y, parent=None):
        super().__init__(parent)

        self.grid_x = x
        self.grid_y = y
        self.item_data = None

        self.setFixedSize(120, 120)
        self.setCursor(Qt.PointingHandCursor)

        # Item icon.
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        # Main item name.
        self.name_label = QLabel()
        self.name_label.setAlignment(
            Qt.AlignCenter
        )
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.name_label.setMinimumHeight(36)
        self.name_label.setMaximumHeight(48)
        self.name_label.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        # Stack badge.
        self.stack_label = QLabel()
        self.stack_label.setAlignment(
            Qt.AlignCenter
        )
        self.stack_label.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        # Quality badge.
        self.quality_label = QLabel()
        self.quality_label.setAlignment(
            Qt.AlignCenter
        )
        self.quality_label.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        # Equipped badge.
        self.equipped_label = QLabel()
        self.equipped_label.setAlignment(
            Qt.AlignCenter
        )
        self.equipped_label.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        # Main layout.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        layout.addWidget(self.equipped_label, 0, Qt.AlignCenter)
        
        layout.addWidget(
            self.icon_label,
            0,
            Qt.AlignCenter
        )

        # Fixed-height area for the item name.
        name_layout = QVBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)

        name_layout.addStretch()
        name_layout.addWidget(
            self.name_label,
            0,
            Qt.AlignCenter
        )
        name_layout.addStretch()

        layout.addLayout(name_layout, 1)

        # Bottom badges.
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        bottom_layout.addWidget(self.stack_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.quality_label)

        layout.addLayout(bottom_layout)

        self.update_visuals()

    def set_item(self, item_data):
        self.item_data = item_data
        self.update_visuals()

    def clear_item(self):
        self.item_data = None
        self.update_visuals()

    def update_visuals(self):
        if not self.item_data:
            self.name_label.clear()
            self.stack_label.clear()
            self.quality_label.clear()
            self.equipped_label.clear()
            self.icon_label.clear()

            self.setToolTip("Empty Slot")

            self.setStyleSheet("""
                QPushButton {
                    background-color: #151515;
                    border: 1px dashed #303030;
                    border-radius: 7px;
                }

                QPushButton:hover {
                    background-color: #1d1d1d;
                    border: 1px solid #444444;
                }

                QPushButton:pressed {
                    background-color: #111111;
                }
            """)

            return

        prefab = self.item_data.get(
            "prefab",
            "Unknown"
        )

        icon = get_item_icon(prefab)

        if icon == "❓":
            self.icon_label.setText(icon)
            self.icon_label.setStyleSheet("""
                QLabel {
                    color: #888888;
                    font-size: 24px;
                    background: transparent;
                }
            """)
        else:
            icon_path = (
                Path(__file__).resolve().parent.parent
                / "assets"
                / icon
            )

            pixmap = QPixmap(str(icon_path))

            self.icon_label.setPixmap(
                pixmap.scaled(
                    44,
                    44,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

        self.icon_label.show()

        stack = self.item_data.get(
            "stack",
            1
        )

        quality = self.item_data.get(
            "quality",
            1
        )

        equipped = self.item_data.get(
            "equipped",
            False
        )

        display_name = format_item_name(prefab)

        display_name = " ".join(
            wrap_long_word(word)
            for word in display_name.split(" ")
        )

        self.name_label.setText(
            display_name
        )

        self.name_label.setStyleSheet("""
            QLabel {
                color: #e6e6e6;
                font-size: 11px;
                font-weight: bold;
                background: transparent;
            }
        """)

        # Stack badge.
        if stack > 1:
            self.stack_label.setText(
                f"×{stack}"
            )

            self.stack_label.setStyleSheet("""
                QLabel {
                    background-color: #111111;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 1px 5px;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)

            self.stack_label.show()

        else:
            self.stack_label.clear()
            self.stack_label.hide()

        # Quality badge.
        if quality > 1:
            self.quality_label.setText(
                # "★" * quality
                f"{quality}★"
            )

            self.quality_label.setStyleSheet("""
                QLabel {
                    color: #d8c46a;
                    background: transparent;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)

            self.quality_label.show()

        else:
            self.quality_label.clear()
            self.quality_label.hide()

        # Equipped badge.
        if equipped:
            self.equipped_label.setText(
                "EQUIPPED"
            )

            self.equipped_label.setStyleSheet("""
                QLabel {
                    background-color: #3a4728;
                    color: #d9e8b5;
                    border: 1px solid #657a3f;
                    border-radius: 4px;
                    padding: 2px 5px;
                    font-size: 9px;
                    font-weight: bold;
                }
            """)

            self.equipped_label.show()

        else:
            self.equipped_label.clear()
            self.equipped_label.hide()

        self.setToolTip(
            f"{display_name}\n"
            f"Stack: {stack}\n"
            f"Quality: {quality}\n"
            f"Equipped: {'Yes' if equipped else 'No'}"
        )

        # Slot background.
        if equipped:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #3a4728;
                    border: 1px solid #657a3f;
                    border-radius: 7px;
                }

                QPushButton:hover {
                    background-color: #465633;
                    border: 1px solid #829b52;
                }

                QPushButton:pressed {
                    background-color: #303b22;
                }
            """)

        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #252525;
                    border: 1px solid #444444;
                    border-radius: 7px;
                }

                QPushButton:hover {
                    background-color: #303030;
                    border: 1px solid #777777;
                }

                QPushButton:pressed {
                    background-color: #1c1c1c;
                }
            """)
