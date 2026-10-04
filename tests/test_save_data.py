from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tests.support import ITEMS, item, playerDataUtil as player, create_empty_player_data, create_new_character
from subscripts.fchUtil import BinaryReader, BinaryWriter, compile_fch, decompile_fch


class BinaryTests(unittest.TestCase):
    def test_integer_encoding_known_bytes(self):
        for value, expected in ((0, b"\x00"), (127, b"\x7f"),
                                (128, b"\x80\x01"), (16384, b"\x80\x80\x01")):
            for writer_type, reader_type in ((BinaryWriter, BinaryReader),
                                             (player.PlayerDataWriter, player.PlayerDataReader)):
                with self.subTest(value=value, writer=writer_type):
                    writer = writer_type()
                    writer.write_7bit_encoded_int(value)
                    self.assertEqual(writer.get_bytes(), expected)
                    self.assertEqual(reader_type(expected).read_7bit_encoded_int(), value)

    def test_item_count_encoding_boundaries(self):
        for value, expected in ((127, b"\x7f"), (128, b"\x80\x80"),
                                (256, b"\x81\x00"), (32767, b"\xff\xff")):
            with self.subTest(value=value):
                writer = player.PlayerDataWriter()
                writer.write_num_items(value)
                self.assertEqual(writer.get_bytes(), expected)
                self.assertEqual(player.PlayerDataReader(expected).read_num_items(), value)

    def test_utf8_strings(self):
        for text in ("", "Viking", "Åsa ⚔", "x" * 300):
            with self.subTest(text=text):
                writer = BinaryWriter()
                writer.write_string(text)
                self.assertEqual(BinaryReader(writer.get_bytes()).read_string(), text)

    def test_truncated_read(self):
        with self.assertRaises(EOFError):
            BinaryReader(b"\x01").read_int32()

    def test_negative_array_length(self):
        with self.assertRaises(ValueError):
            BinaryReader(struct.pack("<i", -1)).read_byte_array()

    def test_signed_int_overflow(self):
        self.assertEqual(player.int32(0xFFFFFFFF), -1)
        self.assertEqual(player.int32(0x80000000), -2147483648)
        self.assertEqual(player.int32(0x100000000), 0)


class PlayerDataTests(unittest.TestCase):
    def setUp(self):
        database = patch.dict(player.ITEM_HASH_TO_PREFAB, ITEMS, clear=True)
        database.start()
        self.addCleanup(database.stop)

    def round_trip(self, data):
        return player.unpack_player_data_hex(player.pack_player_data_hex(data))

    def test_new_character_defaults(self):
        data = self.round_trip(create_empty_player_data())
        self.assertEqual(data["inventory"], [])
        self.assertEqual(data["health"], 25)
        self.assertEqual(data["skills"], [])
        self.assertEqual(data["inventory_version"], 109)

    def test_item_metadata_and_both_cheated_states(self):
        data = create_empty_player_data()
        data["inventory"] = [item(prefab="SwordIron", stack=12, quality=4,
            durability=23.5, variant=2, equipped=True, cheated=True,
            crafter_id=1234567890123, crafter_name="Åsa", custom_data={"note": "crafted"}), item(grid_x=1)]
        loaded = self.round_trip(data)
        for expected, actual in zip(data["inventory"], loaded["inventory"]):
            for key, value in expected.items():
                with self.subTest(key=key, cheated=expected["cheated"]):
                    self.assertEqual(actual[key], value)

    def test_skills_foods_and_discoveries(self):
        data = create_empty_player_data()
        fields = dict(skills=[dict(id=1, level=12.5, xp=7.25)],
                      foods=[dict(name="Bread", time=300.5)],
                      known_recipes=["SwordIron"], known_stations={"forge": 4},
                      known_material=["Wood"], trophies=["TrophyDeer"],
                      uniques=["invrows 6"], known_biomes=["Meadows"])
        data.update(fields)
        loaded = self.round_trip(data)
        for key, expected in fields.items():
            with self.subTest(key=key):
                self.assertEqual(loaded[key], expected)

    def test_packing_does_not_mutate_input(self):
        data = create_empty_player_data()
        data["inventory"] = [item(cheated=True)]
        original = deepcopy(data)
        player.pack_player_data_hex(data)
        self.assertEqual(data, original)

    def test_invalid_hex_rejected(self):
        with self.assertRaises(ValueError):
            player.unpack_player_data_hex("not hex")


class CharacterFileTests(unittest.TestCase):
    def test_new_characters_do_not_share_mutable_data(self):
        first, second = create_new_character("A"), create_new_character("B")
        first["profiles"][0]["known_worlds"]["Midgard"] = 10
        self.assertEqual(first["profiles"][1]["known_worlds"], {})
        self.assertEqual(second["profiles"][0]["known_worlds"], {})

    def test_character_file_round_trip_and_checksum(self):
        original = create_new_character("Åsa")
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            source = Path(directory) / "source.json"
            target = Path(directory) / "character.fch"
            source.write_text(json.dumps(original), encoding="utf-8")
            compile_fch(str(source), str(target))
            loaded = decompile_fch(str(target))
            reader = BinaryReader(target.read_bytes())
            payload = reader.read_byte_array()
            self.assertEqual(reader.read_byte_array(), hashlib.sha512(payload).digest())
        for key in ("character_name", "player_id", "start_seed", "version",
                    "profile_count", "stat_count", "used_cheats", "player_data_hex"):
            with self.subTest(key=key):
                self.assertEqual(loaded[key], original[key])

    def test_truncated_character_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / "broken.fch"
            path.write_bytes(b"\x08\x00\x00\x00\x01")
            with self.assertRaises(EOFError):
                decompile_fch(str(path))
