import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ui import valheim_detection as detection


class CharacterSaveLocationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def test_windows_prefers_current_local_even_when_only_legacy_exists(self):
        base = self.home / "AppData" / "LocalLow" / "IronGate" / "Valheim"
        (base / "characters").mkdir(parents=True)
        with patch.object(detection.sys, "platform", "win32"), \
             patch.dict(os.environ, {"USERPROFILE": str(self.home)}):
            self.assertEqual(detection.get_valheim_character_save_directory(), base / "characters_local")
            self.assertEqual(detection.get_valheim_character_save_directory(legacy=True), base / "characters")

    def test_linux_native_defaults_without_creating_folders_or_using_cloud(self):
        config = self.home / "xdg"
        native = config / "unity3d" / "IronGate" / "Valheim"
        steam = self.home / "Steam"
        cloud = steam / "userdata" / "123" / "892970" / "remote" / "characters"
        cloud.mkdir(parents=True)
        with patch.object(detection.sys, "platform", "linux"), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}), \
             patch.object(detection, "get_steam_installations", return_value=[steam]):
            self.assertEqual(detection.get_valheim_character_save_directory(), native / "characters_local")
            self.assertEqual(detection.get_valheim_character_save_directory(legacy=True), native / "characters")
        self.assertFalse(config.exists())
        self.assertTrue(detection.is_steam_cloud_path(cloud / "test.fch"))

    def test_linux_finds_local_proton_storage_in_a_steam_library(self):
        steam = self.home / "Steam"
        library = self.home / "Other Library"
        data = (library / "steamapps" / "compatdata" / "892970" / "pfx" / "drive_c" / "users"
                / "steamuser" / "AppData" / "LocalLow" / "IronGate" / "Valheim")
        (data / "characters_local").mkdir(parents=True)
        config = self.home / ".config"
        with patch.object(detection.sys, "platform", "linux"), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}), \
             patch.object(Path, "home", return_value=self.home), \
             patch.object(detection, "get_steam_installations", return_value=[steam]), \
             patch.object(detection, "parse_steam_library_paths", return_value=[library]):
            self.assertEqual(detection.get_valheim_character_save_directory(), data / "characters_local")
            self.assertEqual(detection.get_valheim_character_save_directory(legacy=True), data / "characters")
            native = config / "unity3d" / "IronGate" / "Valheim" / "characters_local"
            native.mkdir(parents=True)
            self.assertEqual(detection.get_valheim_character_save_directory(), native)
