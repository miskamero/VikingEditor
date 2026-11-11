"""Independent wire fixtures based on the installed game's Save/Load methods.

These are synthetic, not copies of private character files. See
docs/nested-save-compatibility.md for assembly evidence and real-save checks.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tests.support import create_empty_player_data, create_new_character, playerDataUtil as player
from subscripts.fchUtil import BinaryReader, compile_fch, decompile_fch


def string(value):
    encoded = value.encode("utf-8")
    assert len(encoded) < 128
    return bytes([len(encoded)]) + encoded


def strings(*values):
    return struct.pack("<i", len(values)) + b"".join(map(string, values))


def wire_payload(version=34, inventory_version=110):
    """Build bytes without calling the production player serializer."""
    result = struct.pack("<i4f", version, 100, 90, 70, 1.5)
    result += string("GP_Eikthyr") + struct.pack("<f", 12.5)
    inventory_offset = len(result)
    result += struct.pack("<iH", inventory_version, 2)
    # All optional item flags: quality, stack, variant, crafter, prefab, custom.
    result += struct.pack("<i4B HHiq", 2350, 2, 1, 7, 255, 4, 12, 2, 1234567890123)
    result += string("Åsa") + struct.pack("<i", -1234567)
    result += b"\x02" + string("note") + string("crafted") + string("mod") + string("opaque")
    cheated_offset = len(result)
    result += b"\xa5"  # Bit 0 plus uninterpreted bits that must survive.
    # No optional fields; quality/stack default to 1, variant/crafter/hash to 0.
    result += struct.pack("<i5B", 0, 3, 1, 0, 0, 0)
    result += strings("SwordIron")
    result += struct.pack("<i", 1) + string("forge") + struct.pack("<i", 4)
    for values in (("Wood",), ("tutorial",), ("unique",), ("TrophyDeer",), ("Meadows",)):
        result += strings(*values)
    result += struct.pack("<i", 1) + string("rune") + string("text")
    result += string("Beard1") + string("Hair1") + struct.pack("<6fi", 1, 0.5, 0.25, 0, 1, 0.5, 1)
    result += struct.pack("<i", 1) + string("Bread") + struct.pack("<f", 300.5)
    result += struct.pack("<iiiff", 2, 1, 1, 12.5, 7.25)  # Skills v2.
    result += struct.pack("<i", 1) + string("mod.player") + string("retain me")
    result += struct.pack("<3fi", 50, 25, 12.5, 3) + b"\x00\xff\x80"
    build_end = len(result)
    if version == 34:
        # Player.Save: pseudo counters first, then item-upgrade seeds.
        result += struct.pack("<5i", 2, -123, 7, 456, 0)
        result += struct.pack("<5i", 2, -789, -2147483648, 123, 2147483647)
    return result, inventory_offset, cheated_offset, build_end


class NestedVersionTests(unittest.TestCase):
    def test_unknown_skill_ids_and_unsupported_skill_layouts(self):
        for version in (33, 34):
            with self.subTest(version=version):
                payload = wire_payload(version)[0]
                skill_record = struct.pack("<iiiff", 2, 1, 1, 12.5, 7.25)
                self.assertEqual(payload.count(skill_record), 1)
                custom_record = struct.pack("<iiiff", 2, 1, -12345, 250.125, 987654.5)
                custom_payload = payload.replace(skill_record, custom_record)
                data = player.unpack_player_data_hex(custom_payload.hex())
                self.assertEqual(data["skills"], [{"id": -12345, "level": 250.125, "xp": 987654.5}])
                self.assertEqual(bytes.fromhex(player.pack_player_data_hex(data)), custom_payload)
                unsupported = payload.replace(skill_record, struct.pack("<i", 3) + skill_record[4:])
                with self.assertRaisesRegex(ValueError, "Unsupported skill data version"):
                    player.unpack_player_data_hex(unsupported.hex())
                data["skill_version"] = 3
                with self.assertRaisesRegex(ValueError, "Unsupported skill data version"):
                    player.pack_player_data_hex(data)

    def test_independent_wire_fixtures_round_trip_all_versions(self):
        for version in (33, 34):
            for inventory_version in (109, 110):
                with self.subTest(player=version, inventory=inventory_version):
                    payload, _, _, _ = wire_payload(version, inventory_version)
                    data = player.unpack_player_data_hex(payload.hex())
                    self.assertEqual(data["version"], version)
                    self.assertEqual(data["inventory_version"], inventory_version)
                    first, second = data["inventory"]
                    self.assertEqual(first["prefab_hash"], -1234567)
                    self.assertEqual(first["custom_data"], {"note": "crafted", "mod": "opaque"})
                    self.assertEqual(first["crafter_name"], "Åsa")
                    self.assertEqual((first["durability"], first["quality"], first["stack"]), (23.5, 4, 12))
                    self.assertEqual((second["quality"], second["stack"], second["variant"]), (1, 1, 0))
                    self.assertEqual(data["build_ui_data_hex"], "00ff80")
                    if version == 34:
                        self.assertEqual(data["pseudo_drop_counters"], {-123: 7, 456: 0})
                        self.assertEqual(data["item_upgrade_seeds"], {-789: -2147483648, 123: 2147483647})
                    else:
                        self.assertNotIn("pseudo_drop_counters", data)
                        self.assertNotIn("item_upgrade_seeds", data)
                    before = deepcopy(data)
                    self.assertEqual(bytes.fromhex(player.pack_player_data_hex(data)), payload)
                    self.assertEqual(data, before)
                    # Export/import converts integer dictionary keys to strings.
                    self.assertEqual(bytes.fromhex(player.pack_player_data_hex(json.loads(json.dumps(data)))), payload)

    def test_editing_cheat_bit_retains_inventory_version_and_other_flag_bits(self):
        for inventory_version in (109, 110):
            with self.subTest(inventory=inventory_version):
                payload, _, offset, _ = wire_payload(inventory_version=inventory_version)
                data = player.unpack_player_data_hex(payload.hex())
                data["inventory"][0]["cheated"] = False
                expected = bytearray(payload)
                expected[offset] &= ~1
                self.assertEqual(bytes.fromhex(player.pack_player_data_hex(data)), expected)

    def test_new_and_legacy_defaults(self):
        data = create_empty_player_data()
        loaded = player.unpack_player_data_hex(player.pack_player_data_hex(data))
        self.assertEqual((loaded["version"], loaded["inventory_version"]), (34, 110))
        self.assertEqual(loaded["pseudo_drop_counters"], {})
        self.assertEqual(loaded["item_upgrade_seeds"], {})
        for key in ("version", "inventory_version", "pseudo_drop_counters", "item_upgrade_seeds"):
            data.pop(key)
        legacy = player.unpack_player_data_hex(player.pack_player_data_hex(data))
        self.assertEqual((legacy["version"], legacy["inventory_version"]), (33, 109))
        data["version"] = 34
        loaded = player.unpack_player_data_hex(player.pack_player_data_hex(data))
        self.assertEqual(loaded["pseudo_drop_counters"], {})
        self.assertEqual(loaded["item_upgrade_seeds"], {})

    def test_version_33_cannot_silently_drop_new_state(self):
        for field in ("pseudo_drop_counters", "item_upgrade_seeds"):
            with self.subTest(field=field):
                data = create_empty_player_data()
                data.update(version=33, **{field: {123: 7}})
                with self.assertRaisesRegex(ValueError, "cannot store"):
                    player.pack_player_data_hex(data)

    def test_unknown_versions_are_rejected_before_rewriting(self):
        payload, inventory_offset, _, _ = wire_payload()
        for field, offset, versions in (("version", 0, (32, 35)),
                                         ("inventory_version", inventory_offset, (108, 111))):
            for version in versions:
                with self.subTest(field=field, version=version):
                    invalid = bytearray(payload)
                    struct.pack_into("<i", invalid, offset, version)
                    with self.assertRaisesRegex(ValueError, "Unsupported"):
                        player.unpack_player_data_hex(invalid.hex())
                    data = create_empty_player_data()
                    data[field] = version
                    with self.assertRaisesRegex(ValueError, "Unsupported"):
                        player.pack_player_data_hex(data)

    def test_version_34_requires_both_complete_dictionaries(self):
        payload, _, _, build_end = wire_payload()
        for suffix in (b"", struct.pack("<i", 0), struct.pack("<ii", 1, 123),
                       struct.pack("<ii", 0, 1), struct.pack("<i", -1), struct.pack("<ii", 0, -1)):
            with self.subTest(suffix=suffix):
                with self.assertRaises((EOFError, ValueError)):
                    player.unpack_player_data_hex((payload[:build_end] + suffix).hex())

    def test_opaque_suffix_is_preserved_for_supported_versions(self):
        for version in (33, 34):
            with self.subTest(version=version):
                payload = wire_payload(version)[0] + b"\xfe\x00\x80extension"
                data = player.unpack_player_data_hex(payload.hex())
                self.assertEqual(data["trailing_data_hex"], b"\xfe\x00\x80extension".hex())
                self.assertEqual(bytes.fromhex(player.pack_player_data_hex(data)), payload)

    def test_nested_edits_survive_outer_46_and_47_round_trips(self):
        for outer_version in (46, 47):
            for version, inventory in ((33, 109), (34, 110)):
                with self.subTest(outer=outer_version, player=version), tempfile.TemporaryDirectory() as directory:
                    data = player.unpack_player_data_hex(wire_payload(version, inventory)[0].hex())
                    data["health"] = 23.5
                    data["inventory"][0]["stack"] = 11
                    root = create_new_character("Test Viking")
                    root.update(version=outer_version, player_data_hex=player.pack_player_data_hex(data))
                    wrapper = Path(directory) / "wrapper.json"
                    output = Path(directory) / "edited.fch"
                    wrapper.write_text(json.dumps(root), encoding="utf-8")
                    with redirect_stdout(io.StringIO()):
                        compile_fch(str(wrapper), str(output))
                        loaded = decompile_fch(str(output))
                    self.assertEqual(loaded, root)
                    self.assertEqual(player.unpack_player_data_hex(loaded["player_data_hex"]), data)
                    reader = BinaryReader(output.read_bytes())
                    self.assertEqual(hashlib.sha512(reader.read_byte_array()).digest(), reader.read_byte_array())
