"""Render repository media from the real UI using a synthetic character.

Run from the project root: python tools/createShowcase.py
Uses the local item/icon cache if available; never writes user configuration/saves.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import QApplication
from subscripts.newCharacter import create_empty_player_data, create_new_character
from ui.mainWindow import MainWindow
from ui.itemEditDialog import ItemEditDialog


def main():
    destination = ROOT / "docs" / "media"
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    font_file = Path("C:/Windows/Fonts/segoeui.ttf")
    if font_file.exists():
        for extra in ("segoeuib.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont(str(font_file.parent / extra))
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    palette = QPalette()
    for role, color in ((QPalette.Window, "#f4f6f7"), (QPalette.WindowText, "#303438"),
                        (QPalette.Base, "#ffffff"), (QPalette.Text, "#303438"),
                        (QPalette.Button, "#f4f6f7"), (QPalette.ButtonText, "#303438"),
                        (QPalette.Highlight, "#dce9d4"), (QPalette.HighlightedText, "#263422")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    with patch("ui.mainWindow.load_config", return_value={"is_first_launch": False}), \
         patch("ui.mainWindow.save_config"), patch("ui.mainWindow.is_valheim_running", return_value=False), \
         patch.object(MainWindow, "check_valheim_installation"), \
         patch.object(MainWindow, "check_item_database"):
        window = MainWindow()
    data = create_empty_player_data()
    prefabs = ["SwordIron", "ShieldWood", "BowDraugrFang", "ArrowObsidian", "PickaxeIron", "Hammer",
               "Hoe", "Cultivator", "ArmorWolfChest", "ArmorWolfLegs", "HelmetDrake", "CapeWolf",
               "Wood", "Stone", "FineWood", "Iron", "Bread", "CookedMeat", "Honey", "Carrot",
               "AmberPearl", "Coins", "Resin", "Feathers"]
    data["inventory"] = [dict(prefab=p, stack=(50 if i in range(12,16) else 20 if i in range(16,24) else 1),
        grid_x=i % 8, grid_y=i // 8, quality=3 if i < 3 else 1, durability=100.0,
        equipped=i in (0,1,8,9,10,11), variant=2 if p == "ShieldWood" else 0, cheated=False)
        for i,p in enumerate(prefabs)]
    data.update(health=125, max_health=150, stamina=100, max_stamina=150,
                hair="Hair1", beard="Beard1", skin_color=[0.8,0.65,0.5], hair_color=[0.22,0.14,0.08],
                foods=[dict(name="Bread",time=900),dict(name="CookedMeat",time=600)],
                skills=[dict(id=i,level=level,xp=12) for i,level in ((1,65),(2,48),(3,56),(4,42),(5,60),(6,32))],
                known_recipes=prefabs, known_stations={"forge":5,"workbench":4,"cauldron":3},
                known_material=prefabs[12:], trophies=["TrophyDeer","TrophyEikthyr","TrophyTroll"],
                known_biomes=["Meadows","BlackForest","Swamp","Mountain"],
                uniques=["defeated_eikthyr","defeated_gdking"])
    root = create_new_character("Astrid")
    root.update(player_id=123456789, start_seed="DEMO-WORLD", date_created_unix=1735689600)
    root["profiles"][0]["enemy_stats"] = [{"Greydwarf":328,"Skeleton":145,"Draugr":96,"Troll":24,"Wolf":52}]
    window.player_data, window.root_save = data, root
    window.inventory_tab.load_data(data)
    window.skills_tab.load_data(data)
    window.stats_tab.load_data(data, root)
    window.appearance_tab.load_data(data)
    window.progress_tab.load_data(data)
    window.statistics_tab.load_data(data, root)
    window.character_tab.load_data(data, root)
    window.file_label.setText("Demo character: Astrid  ·  Illustrative data")
    window.resize(1100, 780)
    window.show()
    frames = []
    for title in ("Inventory", "Skills", "Stats", "Progress", "Statistics"):
        index = next(i for i in range(window.tabs.count()) if window.tabs.tabText(i) == title)
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        path = destination / f"{title.lower()}.png"
        window.grab().save(str(path))
        with Image.open(path) as image:
            frames.append(image.copy().convert("RGB"))
    frames[0].save(destination / "showcase.gif", save_all=True, append_images=frames[1:],
                   duration=[4000,3000,3000,3000,3000], loop=0, optimize=True)
    dialog = ItemEditDialog(data["inventory"][1])
    dialog.prefab_input.search.setText("shield")
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(destination / "item-editor.png"))
    dialog.close()
    window.close()
    print(f"Created showcase media in {destination}")


if __name__ == "__main__":
    main()
