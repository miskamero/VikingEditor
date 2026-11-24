import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from tests.support import item
from tests.test_editor import QtTestCase
from subscripts import itemDatabase as database
from ui.inventorySlot import InventorySlot
from ui.valheim_detection import is_valid_valheim_installation


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
        shared = SimpleNamespace(m_icons=list(references), m_name="$item_fixture")
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
        (self.path.parent / "item_icons").mkdir()
        (self.path.parent / "outside.png").write_bytes(b"existing file")
        self.manifest(["../outside.png"])
        self.assertIsNone(database.get_item_icon_path("Wood"))

    def test_invalid_entry_does_not_disable_unrelated_icons(self):
        icons = database.extract_item_icons(self.component(self.sprite("red")), {})
        self.path.write_text(json.dumps({"items": {
            "1": {"prefab": "Wood", "icons": icons}, "2": None,
            "3": {"prefab": "Broken", "icons": None}}}), encoding="utf-8")
        self.assertIsNotNone(database.get_item_icon_path("Wood"))
        self.assertIsNone(database.get_item_icon_path("Broken"))

    def test_cancellation_preserves_existing_database(self):
        self.manifest([])
        before = self.path.read_bytes()
        with patch.object(database, "find_valheim_bundles", return_value=[]), \
             patch.object(database, "get_bundles_dir", return_value=self.path.parent), \
             patch.object(database.UnityPy, "Environment"), patch("builtins.print"):
            self.assertIsNone(database.update_item_database("unused", cancel_callback=lambda: True))
        self.assertEqual(self.path.read_bytes(), before)

    def asset_object(self, prefab, component):
        component.type = database.ClassIDType.MonoBehaviour
        component.path_id = 1
        obj = Mock(type=database.ClassIDType.GameObject)
        obj.peek_name.return_value = prefab
        obj.read.return_value = SimpleNamespace(m_Component=[
            SimpleNamespace(component=Mock(deref=Mock(return_value=component)))])
        return obj

    def run_update(self, component, *, source="unused", objects=None):
        if objects is None:
            objects = [self.asset_object("Wood", component)]
        with patch.object(database, "find_valheim_bundles", return_value=[]), \
             patch.object(database.UnityPy, "Environment", return_value=SimpleNamespace(objects=objects)), \
             patch.object(database, "get_script_class_name", return_value="ItemDrop"), \
             patch("builtins.print"):
            return database.update_item_database(source)

    def test_update_repairs_deleted_icon_without_losing_other_variants(self):
        component = self.component(self.sprite("red"), self.sprite("blue"))
        self.run_update(component)
        deleted = database.get_item_icon_path("Wood", 0)
        unaffected = database.get_item_icon_path("Wood", 1)
        deleted.unlink()
        self.assertEqual(database.get_item_icon_path("Wood", 1), unaffected)
        self.run_update(component)
        self.assertTrue(deleted.is_file())
        self.assertEqual(database.get_item_icon_path("Wood", 0), deleted)
        self.assertEqual(database.get_item_icon_path("Wood", 1), unaffected)

    def test_total_extraction_failure_preserves_manifest_and_reports_cause(self):
        self.run_update(self.component(self.sprite("red")))
        before = self.path.read_bytes()
        broken = Mock(deref=Mock(side_effect=ValueError("texture unavailable")))
        with self.assertRaisesRegex(RuntimeError, "texture unavailable"):
            self.run_update(self.component(broken))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNotNone(database.get_item_icon_path("Wood"))

    def test_installation_rejects_empty_and_invalid_bundle_directories(self):
        location = self.path.parent / "Valheim"
        bundles = database.get_bundles_dir(location)
        bundles.mkdir(parents=True)
        self.manifest([])
        before = self.path.read_bytes()
        self.assertFalse(is_valid_valheim_installation(location))
        (bundles / "cafe").write_bytes(b"not a bundle" * 10)
        self.assertFalse(is_valid_valheim_installation(location))
        with self.assertRaisesRegex(ValueError, "No Unity asset bundles"):
            database.update_item_database(location)
        self.assertEqual(self.path.read_bytes(), before)

    def test_bundle_manifest_checks_missing_dependencies_and_load_failures(self):
        location = self.path.parent / "Valheim"
        bundles = database.get_bundles_dir(location)
        bundles.mkdir(parents=True)
        self.manifest([])
        before = self.path.read_bytes()
        manifest = bundles.parent / "manifest"
        manifest.write_text("SoftRef manifest - Text\n- bundle: cafe\n  dependencies:\n  - dead\n", encoding="utf-8")
        (bundles / "cafe").write_bytes(b"UnityFS\0" + struct.pack(">I", 8) + bytes(24))
        with self.assertRaisesRegex(ValueError, "Missing 1 Valheim bundle.*dead"):
            database.update_item_database(location)
        manifest.write_text("SoftRef manifest - Text\n- bundle: cafe\n", encoding="utf-8")
        for result, explanation in ((OSError("bad block"), "bad block"), (None, "no readable assets")):
            env = Mock()
            if isinstance(result, Exception):
                env.load_file.side_effect = result
            else:
                env.load_file.return_value = result
            with patch.object(database.UnityPy, "Environment", return_value=env), \
                    self.assertRaisesRegex(ValueError, f"bundle cafe.*{explanation}"):
                database.update_item_database(location)
            self.assertEqual(self.path.read_bytes(), before)

    def test_empty_or_incomplete_result_keeps_old_manifest_and_icon_files(self):
        red = self.component(self.sprite("red"))
        self.run_update(red)
        before = self.path.read_bytes()
        icon = database.get_item_icon_path("Wood")
        before_png = icon.read_bytes()
        with self.assertRaisesRegex(ValueError, "No Valheim items"):
            self.run_update(None, objects=[])
        blue = self.component(self.sprite("blue"))
        unreadable = Mock(read=Mock(side_effect=ValueError("invalid item type tree")))
        assets = [self.asset_object("Wood", blue), self.asset_object("SwordIron", unreadable)]
        with self.assertRaisesRegex(ValueError, "Incomplete item catalog.*SwordIron"):
            self.run_update(None, objects=assets)
        broken = Mock(deref=Mock(side_effect=ValueError("bad variant")))
        with self.assertRaisesRegex(RuntimeError, "bad variant"):
            self.run_update(self.component(self.sprite("blue"), broken))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(icon.parent.iterdir()), [icon])
        self.assertEqual(icon.read_bytes(), before_png)

    def test_catalog_smaller_by_source_is_valid_but_missing_advertised_item_is_not(self):
        location = self.path.parent / "Valheim"
        bundles = database.get_bundles_dir(location)
        bundles.mkdir(parents=True)
        extended = bundles.parent / "manifest_extended"
        wood = self.asset_object("Wood", self.component(self.sprite("red")))
        hammer = self.asset_object("Hammer", self.component(self.sprite("blue")))
        self.assertEqual(len(self.run_update(None, objects=[wood, hammer])), 2)
        before = self.path.read_bytes()
        manifest = "SoftRef manifest - Text\n  path in bundle: Assets/items/Wood.prefab\n"
        extended.write_text(manifest + "  path in bundle: Assets/items/Hammer.prefab\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Incomplete item catalog.*Hammer"):
            self.run_update(None, source=location, objects=[wood])
        self.assertEqual(self.path.read_bytes(), before)
        extended.write_text(manifest, encoding="utf-8")
        self.assertEqual(self.run_update(None, source=location, objects=[wood]),
                         {database.get_stable_hash_code("Wood"): "Wood"})
        self.assertEqual(database.load_item_database(), {database.get_stable_hash_code("Wood"): "Wood"})

    def test_manifest_persistence_failure_leaves_prior_working_cache(self):
        self.run_update(self.component(self.sprite("red")))
        before = self.path.read_bytes()
        icon = database.get_item_icon_path("Wood")
        before_png = icon.read_bytes()
        atomic_write = database.atomic_write

        def fail_manifest(path, contents, revision):
            if path == self.path:
                raise OSError("manifest could not be replaced")
            return atomic_write(path, contents, revision)

        with patch.object(database, "atomic_write", side_effect=fail_manifest), \
                self.assertRaisesRegex(OSError, "manifest could not be replaced"):
            self.run_update(self.component(self.sprite("blue")))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(database.get_item_icon_path("Wood"), icon)
        self.assertEqual(icon.read_bytes(), before_png)
        self.assertFalse(list(self.path.parent.glob("item-catalog-*")))

    def test_conflicting_prefab_hashes_do_not_replace_working_catalog(self):
        wood = self.asset_object("Wood", self.component(self.sprite("red")))
        hammer = self.asset_object("Hammer", self.component(self.sprite("blue")))
        self.run_update(None, objects=[wood, hammer])
        before = self.path.read_bytes()
        with patch.object(database, "get_stable_hash_code", return_value=7), \
                self.assertRaisesRegex(ValueError, "Item hash 7 is shared by Hammer and Wood"):
            self.run_update(None, objects=[wood, hammer])
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
