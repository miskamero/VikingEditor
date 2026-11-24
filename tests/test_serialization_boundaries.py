"""Independent PlayerProfile and Player wire cases for lossless edit boundaries."""

from copy import deepcopy
import hashlib
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from subscripts.binaryCodec import BinaryReader, BinaryWriter
from subscripts.fchUtil import character_json, compile_fch, decoded_character, encode_fch, parse_fch, verified_payload
from subscripts.playerDataUtil import pack_player_data_hex, unpack_player_data_hex
from tests.test_player_versions import string, wire_payload


def array(data):
    return struct.pack("<i", len(data)) + data


def sign(body):
    return array(body) + array(hashlib.sha512(body).digest())


def world_wire(uid, *, flags=(1, 0, 1), offset=0, map_data=b"\x00\xffmap"):
    points = b"".join(struct.pack("<B3f", flag, offset + 3 * i + 1, 2, 3) for i, flag in enumerate(flags))
    mapped = b"\x00" if map_data is None else b"\x01" + array(map_data)
    return struct.pack("<q", uid) + points + struct.pack("<3f", 10, 11, 12) + mapped


def profile_wire(nested, *, version=47, name="Wire Viking", timestamp=123, profiles=(), stat_count=0, worlds=()):
    body = struct.pack("<iii", version, stat_count, len(profiles)) + b"".join(profiles)
    body += b"\x01" + struct.pack("<i", len(worlds)) + b"".join(worlds)
    name_record = string(name) if isinstance(name, str) else name
    body += name_record + struct.pack("<q", 2**63 - 1) + string("seed") + struct.pack("<Bq", 0, timestamp)
    return sign(body + (b"\x00" if nested is None else b"\x01" + array(nested)))


def stats_wire(named=(), *, stat_count=0, groups=5):
    world_times = struct.pack("<i", len(named)) + b"".join(string(key) + struct.pack("<f", value)
                                                         for key, value in named)
    return bytes(4 * stat_count) + world_times + bytes(8) + struct.pack("<i", groups) + bytes(4 * (groups + 5))


def nested_with_item(item, inventory_version=110):
    nested, inventory, flags, _ = wire_payload(34, inventory_version)
    return nested[:inventory + 6] + item + nested[flags + 1:]


class SerializationBoundaryTests(unittest.TestCase):
    def test_profile_and_enemy_dimensions_and_numeric_stat_dictionary(self):
        group = stats_wire(stat_count=206)
        original = profile_wire(None, profiles=[group] * 10, stat_count=206)
        self.assertEqual(encode_fch(parse_fch(original)), original)
        for invalid, field in (
            (profile_wire(None, profiles=[group] * 11, stat_count=206), "profile_count"),
            (profile_wire(None, profiles=[stats_wire(groups=6)]), "enemy_stats"),
        ):
            verified_payload(invalid)
            with self.assertRaisesRegex(ValueError, field):
                parse_fch(invalid)
        model = parse_fch(original)
        with self.assertRaisesRegex(ValueError, "profile_count"):
            encode_fch(dict(model, profile_count=11, profiles=model["profiles"] + [model["profiles"][0]]))
        model["profiles"][0]["enemy_stats"].append({})
        with self.assertRaisesRegex(ValueError, "enemy_stats"):
            encode_fch(model)

    def test_timestamp_boundaries_and_duplicate_world_uids(self):
        for seconds in (-62135596800, 253402300799):
            with self.subTest(seconds=seconds):
                original = profile_wire(None, timestamp=seconds)
                self.assertEqual(encode_fch(parse_fch(original)), original)
        for seconds in (-62135596801, 253402300800, 2**63 - 1):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(ValueError, "date_created_unix"):
                parse_fch(profile_wire(None, timestamp=seconds))
        model = parse_fch(profile_wire(None, worlds=[world_wire(-2**63)]))
        for seconds in (-62135596801, 253402300800):
            with self.assertRaisesRegex(ValueError, "date_created_unix"):
                encode_fch(dict(model, date_created_unix=seconds))
        model["worlds"].append(deepcopy(model["worlds"][0]))
        for call, value in ((encode_fch, model), (parse_fch, profile_wire(None, worlds=[world_wire(-2**63)] * 2))):
            with self.assertRaisesRegex(ValueError, "Duplicate world UID.*Valheim rejects"):
                call(value)

    def test_wire_dictionary_duplicate_diagnostics_match_game_behavior(self):
        nested = wire_payload()[0]
        for field, entry in (
            ("known_stations", string("forge") + struct.pack("<i", 4)),
            ("known_texts", string("rune") + string("text")),
            ("player custom_data", string("mod.player") + string("retain me")),
        ):
            single = struct.pack("<i", 1) + entry
            duplicate = struct.pack("<i", 2) + entry * 2
            self.assertEqual(nested.count(single), 1)
            changed = nested.replace(single, duplicate, 1)
            behavior = "rejects" if field == "known_stations" else "keeps the last value"
            with self.assertRaisesRegex(ValueError, f"Duplicate key.*{field}.*Valheim {behavior}"):
                parse_fch(profile_wire(changed))
        double_counter = nested.replace(struct.pack("<5i", 2, -123, 7, 456, 0),
                                        struct.pack("<5i", 2, -123, 7, -123, 0), 1)
        with self.assertRaisesRegex(ValueError, "Duplicate key.*pseudo_drop_counters.*keeps the last value"):
            unpack_player_data_hex(double_counter.hex())
        double_item = nested.replace(b"\x02" + string("note") + string("crafted") + string("mod"),
                                     b"\x02" + string("note") + string("crafted") + string("note"), 1)
        with self.assertRaisesRegex(ValueError, "Duplicate key.*item custom_data.*keeps the last value"):
            unpack_player_data_hex(double_item.hex())
        stats = stats_wire([("same", 1), ("same", 2)])
        with self.assertRaisesRegex(ValueError, "Duplicate key.*known_worlds.*keeps the last value"):
            parse_fch(profile_wire(nested, profiles=[stats]))

    def test_malformed_and_noncanonical_string_framing(self):
        text = "\u00c5\U0001f9ea" * 25
        expected = "\u00c5\U0001f9ea".encode("utf-8") * 25
        writer = BinaryWriter()
        writer.write_string(text)
        self.assertEqual(writer.get_bytes(), b"\x96\x01" + expected)
        self.assertEqual(BinaryReader(b"\x96\x01" + expected).read_string(), text)
        for value, kind, detail in (
            (b"\x01\xff", ValueError, "Malformed UTF-8"),
            (b"\x81\x00x", ValueError, "Noncanonical"),
            (b"\x80", EOFError, "prefix"),
            (b"\x80" * 6, ValueError, "exceeds"),
            (b"\xff\xff\xff\xff\x08", ValueError, "exceeds"),
            (b"\xff\xff\xff\xff\x07", EOFError, "UTF-8 string"),
            (b"\x04abc", EOFError, "UTF-8 string"),
        ):
            with self.subTest(value=value), self.assertRaisesRegex(kind, detail):
                BinaryReader(value).read_string()
        for bad in (profile_wire(None, name=b"\x06Audit\xff"),
                    profile_wire(wire_payload()[0].replace(string("GP_Eikthyr"), b"\x01\xff", 1))):
            verified_payload(bad)
            with self.assertRaisesRegex(ValueError, "Malformed UTF-8"):
                parse_fch(bad)
        with self.assertRaisesRegex(ValueError, "Noncanonical boolean"):
            BinaryReader(b"\x02").read_bool()
        with self.assertRaisesRegex(ValueError, "Noncanonical compact item count"):
            BinaryReader(b"\x80\x7f").read_num_items()

    def test_explicit_default_item_fields_and_opaque_bits_round_trip(self):
        for version in (109, 110):
            with self.subTest(version=version):
                explicit = struct.pack("<i4BHHiq", -100, 2, 1, 255, 255, 1, 1, 0, 0)
                explicit += string("Name with explicit ID zero") + struct.pack("<iBB", 0, 0, 0xA5)
                nested = nested_with_item(explicit, version) + b"\x80\x00\xff"
                original = profile_wire(nested)
                decoded = json.loads(character_json(decoded_character(parse_fch(original))))
                record = decoded["player_data"]["inventory"][0]
                self.assertEqual(record["extra_item_flags"], 252)
                self.assertEqual(record["prefab_hash"], 0)
                self.assertEqual(record["cheated_flags"], 0xA5)
                self.assertIs(record["cheated"], version == 110)
                self.assertEqual(encode_fch(decoded), original)
                record["cheated"] = False
                expected = explicit[:-1] + bytes([0xA5 if version == 109 else 0xA4])
                self.assertEqual(encode_fch(decoded), profile_wire(nested_with_item(expected, version) + b"\x80\x00\xff"))

    def test_compact_custom_counts_at_actual_item_boundary(self):
        prefix = struct.pack("<i4B", 0, 2, 1, 0, 128)
        for count, encoded in ((0, b"\x00"), (127, b"\x7f"), (128, b"\x80\x80"),
                               (255, b"\x80\xff"), (256, b"\x81\x00"), (32767, b"\xff\xff")):
            with self.subTest(count=count):
                pairs = b"".join(string(str(i)) + string("v") for i in range(count))
                nested = nested_with_item(prefix + encoded + pairs + b"\x00")
                model = unpack_player_data_hex(nested.hex())
                self.assertEqual(len(model["inventory"][0]["custom_data"]), count)
                self.assertEqual(bytes.fromhex(pack_player_data_hex(model)), nested)
        for count in (32768, 32769):
            model["inventory"][0]["custom_data"] = {str(i): "v" for i in range(count)}
            with self.assertRaisesRegex(ValueError, r"inventory\[0\].custom_data count"):
                pack_player_data_hex(model)

    def test_writer_rejects_invalid_vectors_ranges_and_presence(self):
        wire = wire_payload()[0]
        root = decoded_character(parse_fch(profile_wire(wire, worlds=[world_wire(1)])))
        for field in ("skin_color", "hair_color"):
            for vector in ([0, 0], [0, 0, 0, 0]):
                with self.subTest(field=field, vector=vector), self.assertRaisesRegex(ValueError, field):
                    pack_player_data_hex(dict(root["player_data"], **{field: vector}))
        for field, bad in (("grid_y", -1), ("quality", 65536), ("variant", -2**31 - 1),
                           ("crafter_id", 2**63), ("cheated_flags", 256), ("extra_item_flags", 1),
                           ("prefab_hash", -2**31 - 1), ("durability", float("inf")),
                           ("equipped", 1), ("prefab", "Mismatched")):
            model = deepcopy(root["player_data"])
            model["inventory"][0][field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                pack_player_data_hex(model)
        for field, bad in (("spawn_point", [0, 0]), ("home_point", [0] * 4), ("have_death_point", None),
                           ("map_data_hex", "0x"), ("world_id", 2**63)):
            model = deepcopy(root)
            model["worlds"][0][field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                encode_fch(model)
        with self.assertRaisesRegex(ValueError, "negative length"):
            BinaryReader(struct.pack("<i", -1)).read_byte_array("test bytes")
        with self.assertRaisesRegex(EOFError, "test bytes"):
            BinaryReader(array(b"xx")[:-1]).read_byte_array("test bytes")

    def test_nonfinite_binary32_bits_and_world_map_availability_round_trip(self):
        nested = wire_payload()[0]
        special = bytes.fromhex("0100807f 000080ff 00000080")  # signaling NaN, -Inf, -0
        nested = nested[:4] + special + nested[16:] + b"\x01opaque"
        worlds = (world_wire(2**63 - 1, map_data=None), world_wire(-2**63, map_data=b""), world_wire(7))
        original = profile_wire(nested, worlds=worlds)
        model = json.loads(character_json(decoded_character(parse_fch(original))))
        self.assertEqual(model["player_data"]["max_health"], {"float32_hex": "0100807f"})
        self.assertEqual([record["map_data_hex"] for record in model["worlds"]], [None, "", "00ff6d6170"])
        self.assertEqual(encode_fch(model), original)
        model["character_name"] = "Other"
        self.assertEqual(encode_fch(model), profile_wire(nested, worlds=worlds, name="Other"))

    def test_malformed_nested_with_valid_digest_fails_before_creating_or_replacing_target(self):
        nested = wire_payload()[0]
        canonical = profile_wire(nested)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            target = Path(directory) / "new.fch"
            for bad, detail in ((nested[:-1], "Truncated"), (struct.pack("<i", 35) + nested[4:], "Unsupported"),
                                (b"", "Truncated")):
                invalid = profile_wire(bad)
                verified_payload(invalid)
                with self.assertRaisesRegex((ValueError, EOFError), f"Nested player data:.*{detail}"):
                    parse_fch(invalid)
                source.write_bytes(character_json(dict(parse_fch(canonical), player_data_hex=bad.hex())))
                with self.assertRaisesRegex((ValueError, EOFError), detail):
                    compile_fch(source, target)
                self.assertFalse(target.exists())
                target.write_bytes(canonical)
                with self.assertRaisesRegex((ValueError, EOFError), detail):
                    compile_fch(source, target)
                self.assertEqual(target.read_bytes(), canonical)
                target.unlink()
