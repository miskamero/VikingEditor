import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from tests.support import item
from tests.test_editor import QtTestCase
from subscripts import itemDatabase as database
from ui.inventorySlot import InventorySlot


class ItemIconTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "items.json"
        patcher = patch.object(database, "ITEM_DATABASE_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        database.load_item_icons.cache_clear()
        self.addCleanup(database.load_item_icons.cache_clear)

    def component(self, *references):
        shared = SimpleNamespace(m_icons=list(references))
        return Mock(read=Mock(return_value=SimpleNamespace(m_itemData=SimpleNamespace(m_shared=shared))))

    def sprite(self, color):
        sprite = Mock(path_id=42, assets_file=object())
        sprite.read.return_value = SimpleNamespace(image=Image.new("RGBA", (8, 8), color))
        return Mock(deref=Mock(return_value=sprite))

    def manifest(self, icons):
        self.path.write_text(json.dumps({"items": {"1": {"prefab": "Wood", "icons": icons}}}), encoding="utf-8")
        database.load_item_icons.cache_clear()

    def test_extract_preserves_alpha_and_deduplicates(self):
        reference = self.sprite((255, 0, 0, 128))
        cache = {}
        icons = database.extract_item_icons(self.component(reference, reference), cache)
        self.assertEqual(icons[0], icons[1])
        reference.deref.return_value.read.assert_called_once()
        with Image.open(self.path.parent / "item_icons" / icons[0]) as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 128))

    def test_variants_and_missing_variant_fallback(self):
        icons = database.extract_item_icons(self.component(self.sprite("red"), self.sprite("blue")), {})
        self.manifest(icons)
        self.assertEqual(database.get_item_icon_path("Wood", 1).name, icons[1])
        self.assertEqual(database.get_item_icon_path("Wood", 99).name, icons[0])
        (self.path.parent / "item_icons" / icons[1]).unlink()
        self.assertEqual(database.get_item_icon_path("Wood", 1).name, icons[0])

    def test_null_sprite_keeps_variant_index(self):
        icons = database.extract_item_icons(self.component(Mock(deref=Mock(return_value=None)), self.sprite("blue")), {})
        self.assertIsNone(icons[0])
        self.assertIsNotNone(icons[1])

    def test_unreadable_sprite_does_not_abort_other_variants(self):
        broken = Mock(deref=Mock(side_effect=ValueError("broken sprite")))
        with patch("builtins.print"):
            icons = database.extract_item_icons(self.component(broken, self.sprite("blue")), {})
        self.assertIsNone(icons[0])
        self.assertIsNotNone(icons[1])

    def test_old_missing_or_invalid_database_uses_fallback(self):
        self.assertIsNone(database.get_item_icon_path("Wood"))
        for content in ('{"items":{"1":{"prefab":"Wood"}}}', 'invalid json'):
            self.path.write_text(content, encoding="utf-8")
            database.load_item_icons.cache_clear()
            self.assertIsNone(database.get_item_icon_path("Wood"))

    def test_manifest_cannot_escape_cache(self):
        self.manifest(["../../outside.png"])
        self.assertIsNone(database.get_item_icon_path("Wood"))

    def test_cancellation_preserves_existing_database(self):
        self.manifest([])
        before = self.path.read_bytes()
        with patch.object(database, "find_valheim_bundles", return_value=[]), \
             patch.object(database, "get_bundles_dir", return_value=self.path.parent), \
             patch.object(database.UnityPy, "Environment"), patch("builtins.print"):
            self.assertIsNone(database.update_item_database("unused", cancel_callback=lambda: True))
        self.assertEqual(self.path.read_bytes(), before)


class InventoryIconTests(QtTestCase):
    def test_slot_displays_cached_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "icon.png"
            Image.new("RGBA", (8, 8), "red").save(path)
            with patch("ui.inventorySlot.get_item_icon_path", return_value=path) as lookup:
                slot = self.widget(InventorySlot, 0, 0)
                slot.set_item(item(variant=2))
                lookup.assert_called_with("Wood", 2)
                self.assertEqual(slot.icon_label.pixmap().toImage().pixelColor(10, 10).red(), 255)

    def test_corrupt_cache_uses_category_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "icon.png"
            path.write_bytes(b"broken")
            with patch("ui.inventorySlot.get_item_icon_path", return_value=path):
                slot = self.widget(InventorySlot, 0, 0)
                slot.set_item(item())
                self.assertFalse(slot.icon_label.pixmap().isNull())
