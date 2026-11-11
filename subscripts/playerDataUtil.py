import struct
import io
import json
from pathlib import Path

from subscripts.itemDatabase import load_item_database

ITEM_HASH_TO_PREFAB = load_item_database()

def reload_item_database():
    ITEM_HASH_TO_PREFAB.clear()
    ITEM_HASH_TO_PREFAB.update(load_item_database())

def int32(value):
    value &= 0xFFFFFFFF

    if value >= 0x80000000:
        value -= 0x100000000

    return value


def get_stable_hash_code(text):
    encoded = text.encode("utf-16-le")

    chars = [
        int.from_bytes(
            encoded[i:i + 2],
            "little"
        )
        for i in range(0, len(encoded), 2)
    ]

    num = 5381
    num2 = num
    num3 = 0

    while num3 < len(chars) and chars[num3] != 0:
        num = int32(
            ((num << 5) + num) ^ chars[num3]
        )

        if (
            num3 == len(chars) - 1
            or chars[num3 + 1] == 0
        ):
            break

        num2 = int32(
            ((num2 << 5) + num2) ^ chars[num3 + 1]
        )

        num3 += 2

    return int32(
        num + num2 * 1566083941
    )

class PlayerDataReader:
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)

    def read_bytes(self, n: int) -> bytes:
        data = self.stream.read(n)

        if len(data) != n:
            raise EOFError(
                f"Unexpected end of stream: "
                f"expected {n} bytes, got {len(data)}"
            )

        return data

    def read_byte(self) -> int:
        return self.read_bytes(1)[0]

    def read_ushort(self) -> int:
        return struct.unpack("<H", self.read_bytes(2))[0]

    def read_int32(self) -> int:
        return struct.unpack("<i", self.read_bytes(4))[0]

    def read_float(self) -> float:
        return struct.unpack("<f", self.read_bytes(4))[0]

    def read_long(self) -> int:
        return struct.unpack("<q", self.read_bytes(8))[0]

    def read_bool(self) -> bool:
        return self.read_bytes(1)[0] != 0

    def read_vector3(self) -> list:
        return list(
            struct.unpack(
                "<fff",
                self.read_bytes(12)
            )
        )

    def read_7bit_encoded_int(self) -> int:
        value = 0
        shift = 0

        while True:
            byte = self.read_byte()

            value |= (byte & 0x7F) << shift

            if (byte & 0x80) == 0:
                break

            shift += 7

        return value

    def read_string(self) -> str:
        length = self.read_7bit_encoded_int()

        if length == 0:
            return ""

        return self.read_bytes(length).decode(
            "utf-8",
            errors="ignore"
        )

    def read_byte_array(self) -> bytes:
        length = self.read_int32()

        if length < 0:
            raise ValueError(
                f"Invalid byte array length: {length}"
            )

        return self.read_bytes(length)

    def read_num_items(self) -> int:
        """
        Valheim/ZPackage variable-size item count.

        < 128:
            one byte

        >= 128:
            two bytes
        """
        first = self.read_byte()

        if (first & 0x80) == 0:
            return first

        return ((first & 0x7F) << 8) | self.read_byte()


class PlayerDataWriter:
    def __init__(self):
        self.stream = io.BytesIO()

    def get_bytes(self) -> bytes:
        return self.stream.getvalue()

    def write_byte(self, val: int):
        self.stream.write(struct.pack("<B", val))

    def write_ushort(self, val: int):
        self.stream.write(struct.pack("<H", val))

    def write_int32(self, val: int):
        self.stream.write(struct.pack("<i", val))

    def write_float(self, val: float):
        self.stream.write(
            struct.pack("<f", float(val))
        )

    def write_long(self, val: int):
        self.stream.write(struct.pack("<q", val))

    def write_bool(self, val: bool):
        self.stream.write(
            b"\x01" if val else b"\x00"
        )

    def write_7bit_encoded_int(self, value: int):
        while value >= 0x80:
            self.stream.write(
                bytes([(value & 0x7F) | 0x80])
            )
            value >>= 7

        self.stream.write(bytes([value]))

    def write_string(self, val: str):
        encoded = val.encode("utf-8")

        self.write_7bit_encoded_int(len(encoded))
        self.stream.write(encoded)

    def write_byte_array(self, data: bytes):
        self.write_int32(len(data))
        self.stream.write(data)

    def write_num_items(self, value: int):
        if value < 128:
            self.write_byte(value)
        else:
            self.write_byte((value >> 8) | 0x80)
            self.write_byte(value & 0xFF)


# Helpers! Klinoff needs to clean this up later. Nöfnöf.
# TODO: clean up these helpers and maybe even move them to a better location. They are not really part of the core reader/writer classes?

def read_string_list(pkg: PlayerDataReader) -> list:
    count = pkg.read_int32()

    if count < 0:
        raise ValueError(
            f"Invalid list count: {count}"
        )

    return [
        pkg.read_string()
        for _ in range(count)
    ]


def read_string_int_dictionary(pkg: PlayerDataReader) -> dict:
    count = pkg.read_int32()

    if count < 0:
        raise ValueError(
            f"Invalid dictionary count: {count}"
        )

    return {
        pkg.read_string(): pkg.read_int32()
        for _ in range(count)
    }


def read_string_string_dictionary(pkg: PlayerDataReader) -> dict:
    count = pkg.read_int32()

    if count < 0:
        raise ValueError(
            f"Invalid dictionary count: {count}"
        )

    return {
        pkg.read_string(): pkg.read_string()
        for _ in range(count)
    }


def read_int_int_dictionary(pkg: PlayerDataReader) -> dict:
    count = pkg.read_int32()
    if count < 0:
        raise ValueError(f"Invalid dictionary count: {count}")
    return {pkg.read_int32(): pkg.read_int32() for _ in range(count)}


# Player.Save / Player.Load

def unpack_player_data_hex(hex_string: str) -> dict:
    """
    parses the nested Player.Save payload from a hex string into a Python dictionary.

    Supports player versions 33/34 and inventory versions 109/110.
    """

    if not hex_string:
        return {}

    raw_bytes = bytes.fromhex(hex_string)

    pkg = PlayerDataReader(raw_bytes)

    out = {}

    # player core stats

    out["version"] = pkg.read_int32()
    if out["version"] not in (33, 34):
        raise ValueError(f"Unsupported player data version: {out['version']}")

    out["max_health"] = pkg.read_float()
    out["health"] = pkg.read_float()
    out["max_stamina"] = pkg.read_float()

    out["time_since_death"] = pkg.read_float() # wtf?

    out["guardian_power"] = pkg.read_string()
    out["guardian_power_cooldown"] = pkg.read_float()

    # inventory
    #
    # Inventory.Save:
    #
    # int version = 109 or 110 (same item layout)
    # ushort item count
    # ItemData.Save()... klinoff knows this one

    out["inventory_version"] = pkg.read_int32()
    if out["inventory_version"] not in (109, 110):
        raise ValueError(f"Unsupported inventory version: {out['inventory_version']}")

    item_count = pkg.read_ushort()

    out["inventory"] = []

    for _ in range(item_count):

        # ItemData.Save:
        #
        # int durability * 100
        # byte x
        # byte y
        # byte world level
        # byte flags
        # optional fields...
        # byte cheated flags

        durability_raw = pkg.read_int32()

        item = {
            "durability": durability_raw * 0.01,
            "grid_x": pkg.read_byte(),
            "grid_y": pkg.read_byte(),
            "world_level": pkg.read_byte()
        }

        flags = pkg.read_byte()

        # bit 0 = picked up
        item["picked_up"] = bool(flags & 1)

        # bit 1 = equipped
        item["equipped"] = bool(flags & 2)

        # bit 2 = quality present
        if flags & 4:
            item["quality"] = pkg.read_ushort()
        else:
            item["quality"] = 1

        # bit 3 = stack present
        if flags & 8:
            item["stack"] = pkg.read_ushort()
        else:
            item["stack"] = 1

        # bit 4 = variant present
        if flags & 16:
            item["variant"] = pkg.read_int32()
        else:
            item["variant"] = 0

        # bit 5 = crafter present
        if flags & 32:
            item["crafter_id"] = pkg.read_long()
            item["crafter_name"] = pkg.read_string()
        else:
            item["crafter_id"] = 0
            item["crafter_name"] = ""

        # bit 6 = prefab hash present
        #
        # Valheim 1.0 no longer stores the prefab name here!!! important
        if flags & 64:
            item["prefab_hash"] = pkg.read_int32()
        else:
            item["prefab_hash"] = 0

        # keep the old field for now so the existing data model doesn't immediately break
        item["prefab"] = ITEM_HASH_TO_PREFAB.get(
            item["prefab_hash"],
            ""
        )

        # bit 7 = custom data present
        if flags & 128:
            custom_count = pkg.read_num_items()
        else:
            custom_count = 0

        item["custom_data"] = {}

        for _ in range(custom_count):
            key = pkg.read_string()
            value = pkg.read_string()

            item["custom_data"][key] = value

        # current item format always has now a extra cheated byte.
        cheated_flags = pkg.read_byte()
        item["cheated_flags"] = cheated_flags

        item["cheated"] = bool(
            cheated_flags & 1
        )

        out["inventory"].append(item)


    # recipes, stations, materials, tutorials, uniques, trophies, biomes, known texts
    out["known_recipes"] = read_string_list(pkg)
    out["known_stations"] = read_string_int_dictionary(pkg)
    out["known_material"] = read_string_list(pkg)
    out["shown_tutorials"] = read_string_list(pkg)
    out["uniques"] = read_string_list(pkg)
    out["trophies"] = read_string_list(pkg)
    out["known_biomes"] = read_string_list(pkg)
    out["known_texts"] = read_string_string_dictionary(pkg)

    # Appearance

    out["beard"] = pkg.read_string()
    out["hair"] = pkg.read_string()

    out["skin_color"] = pkg.read_vector3()
    out["hair_color"] = pkg.read_vector3()

    out["model_index"] = pkg.read_int32()

    # foods

    food_count = pkg.read_int32()

    if food_count < 0:
        raise ValueError(
            f"Invalid food count: {food_count}"
        )

    out["foods"] = []

    for _ in range(food_count):
        out["foods"].append({
            "name": pkg.read_string(),
            "time": pkg.read_float()
        })

    # skills, not like kevin, he does not have skills. nöfnöf.
    #
    # Skills.Save:
    # version = 2
    # count
    # id
    # level
    # accumulator

    out["skill_version"] = pkg.read_int32()
    if out["skill_version"] != 2:
        raise ValueError(f"Unsupported skill data version: {out['skill_version']}")

    skill_count = pkg.read_int32()

    if skill_count < 0:
        raise ValueError(
            f"Invalid skill count: {skill_count}"
        )

    out["skills"] = []

    for _ in range(skill_count):
        out["skills"].append({
            "id": pkg.read_int32(),
            "level": pkg.read_float(),
            "xp": pkg.read_float()
        })

    out["custom_data"] = read_string_string_dictionary(pkg)

    # Final stats
    out["stamina"] = pkg.read_float()
    out["max_eitr"] = pkg.read_float()
    out["eitr"] = pkg.read_float()

    # build ui state
    #
    # Player.Save:
    #
    # if Hud.instance:
    #     pkg.Write(Hud.instance.m_buildUi.SaveToBinary());
    # else:
    #     pkg.Write(new byte[0]);
    #
    # ZPackage byte[] = int32 length + bytes

    build_ui_data = pkg.read_byte_array()

    out["build_ui_data_hex"] = build_ui_data.hex()

    # Player.Save appends these in v34, in this order. Player.Load skips both
    # for v33. Keep the signed keys/values, including seeds we cannot interpret.
    if out["version"] >= 34:
        out["pseudo_drop_counters"] = read_int_int_dictionary(pkg)
        out["item_upgrade_seeds"] = read_int_int_dictionary(pkg)

    # Retain opaque extensions to supported layouts instead of dropping bytes.
    trailing_data = pkg.stream.read()
    if trailing_data:
        out["trailing_data_hex"] = trailing_data.hex()

    return out

def pack_player_data_hex(data: dict) -> str:
    """
    Serializes supported Player.Save payloads, preserving their versions.

    Current format:
        Player version: 33 or 34
        Inventory version: 109 or 110
        Inventory count: ushort
        Item format: compact flags + optional fields
    """

    # Missing versions retain the historical defaults for imported editor JSON.
    version = data.get("version", 33)
    inventory_version = data.get("inventory_version", 109)
    if version not in (33, 34):
        raise ValueError(f"Unsupported player data version: {version}")
    if inventory_version not in (109, 110):
        raise ValueError(f"Unsupported inventory version: {inventory_version}")
    if data.get("skill_version", 2) != 2:
        raise ValueError(f"Unsupported skill data version: {data['skill_version']}")
    if version == 33 and (data.get("pseudo_drop_counters") or data.get("item_upgrade_seeds")):
        raise ValueError("Player version 33 cannot store version 34 counters or upgrade seeds")

    pkg = PlayerDataWriter()

    # Player version
    pkg.write_int32(version)

    # Core stats
    pkg.write_float(
        data.get("max_health", 25.0)
    )

    pkg.write_float(
        data.get("health", 25.0)
    )

    pkg.write_float(
        data.get("max_stamina", 50.0)
    )

    pkg.write_float(
        data.get("time_since_death", 0.0)
    )

    pkg.write_string(
        data.get("guardian_power", "")
    )

    pkg.write_float(
        data.get("guardian_power_cooldown", 0.0)
    )

    # Inventory
    pkg.write_int32(inventory_version)

    inventory = data.get("inventory", [])

    pkg.write_ushort(len(inventory))

    for item in inventory:

        durability = item.get(
            "durability",
            100.0
        )

        durability_raw = int(
            durability * 100.0
        )

        pkg.write_int32(durability_raw)

        # Grid position + world level
        pkg.write_byte(
            item.get("grid_x", 0)
        )

        pkg.write_byte(
            item.get("grid_y", 0)
        )

        pkg.write_byte(
            item.get("world_level", 0)
        )

        # Build item flags
        flags = 0

        if item.get("picked_up", False):
            flags |= 1

        if item.get("equipped", False):
            flags |= 2

        if item.get("quality", 1) != 1:
            flags |= 4

        if item.get("stack", 1) != 1:
            flags |= 8

        if item.get("variant", 0) != 0:
            flags |= 16

        crafter_id = item.get(
            "crafter_id",
            0
        )

        if crafter_id != 0:
            flags |= 32

        # The current format stores the prefab as a stable hash.
        prefab = item.get(
            "prefab",
            ""
        )

        prefab_hash = item.get(
            "prefab_hash",
            0
        )

        if prefab:
            prefab_hash = get_stable_hash_code(
                prefab
            )

        if prefab_hash != 0:
            flags |= 64

        custom_data = item.get(
            "custom_data",
            {}
        )

        if custom_data:
            flags |= 128

        pkg.write_byte(flags)

        # Optional quality
        if flags & 4:
            pkg.write_ushort(
                item.get("quality", 1)
            )

        # Optional stack
        if flags & 8:
            pkg.write_ushort(
                item.get("stack", 1)
            )

        # Optional variant
        if flags & 16:
            pkg.write_int32(
                item.get("variant", 0)
            )

        # Optional crafter
        if flags & 32:
            pkg.write_long(crafter_id)

            pkg.write_string(
                item.get(
                    "crafter_name",
                    ""
                )
            )

        # Optional prefab hash
        if flags & 64:
            pkg.write_int32(prefab_hash)

        # Optional custom data
        if flags & 128:
            pkg.write_num_items(
                len(custom_data)
            )

            for k, v in custom_data.items():
                pkg.write_string(k)
                pkg.write_string(v)

        # Preserve uninterpreted bits while allowing the existing checkbox to
        # edit bit 0. Current ItemData.Load honors this bit only in v110;
        # retaining v109 avoids changing the meaning of legacy item flags.
        cheated_flags = item.get("cheated_flags", 0) & ~1

        if item.get("cheated", False):
            cheated_flags |= 1

        pkg.write_byte(cheated_flags)

    # Known recipes
    recipes = data.get(
        "known_recipes",
        []
    )

    pkg.write_int32(len(recipes))

    for recipe in recipes:
        pkg.write_string(recipe)

    # Known stations
    stations = data.get(
        "known_stations",
        {}
    )

    pkg.write_int32(len(stations))

    for k, v in stations.items():
        pkg.write_string(k)
        pkg.write_int32(v)

    # Known materials
    materials = data.get(
        "known_material",
        []
    )

    pkg.write_int32(len(materials))

    for material in materials:
        pkg.write_string(material)

    # Shown tutorials
    tutorials = data.get(
        "shown_tutorials",
        []
    )

    pkg.write_int32(len(tutorials))

    for tutorial in tutorials:
        pkg.write_string(tutorial)

    # Uniques
    uniques = data.get(
        "uniques",
        []
    )

    pkg.write_int32(len(uniques))

    for unique in uniques:
        pkg.write_string(unique)

    # Trophies
    trophies = data.get(
        "trophies",
        []
    )

    pkg.write_int32(len(trophies))

    for trophy in trophies:
        pkg.write_string(trophy)

    # Known biomes
    # Current Valheim format uses strings here.
    biomes = data.get(
        "known_biomes",
        []
    )

    pkg.write_int32(len(biomes))

    for biome in biomes:
        pkg.write_string(biome)

    # Known texts
    texts = data.get(
        "known_texts",
        {}
    )

    pkg.write_int32(len(texts))

    for k, v in texts.items():
        pkg.write_string(k)
        pkg.write_string(v)

    # Appearance
    pkg.write_string(
        data.get("beard", "")
    )

    pkg.write_string(
        data.get("hair", "")
    )

    for x in data.get(
        "skin_color",
        [1.0, 1.0, 1.0]
    ):
        pkg.write_float(x)

    for x in data.get(
        "hair_color",
        [1.0, 1.0, 1.0]
    ):
        pkg.write_float(x)

    pkg.write_int32(
        data.get("model_index", 0)
    )

    # Foods
    foods = data.get(
        "foods",
        []
    )

    pkg.write_int32(len(foods))

    for food in foods:
        pkg.write_string(
            food.get("name", "")
        )

        pkg.write_float(
            food.get("time", 0.0)
        )

    # Skills
    pkg.write_int32(2)

    skills = data.get(
        "skills",
        []
    )

    pkg.write_int32(len(skills))

    for skill in skills:
        pkg.write_int32(
            skill.get("id", 0)
        )

        pkg.write_float(
            skill.get("level", 1.0)
        )

        pkg.write_float(
            skill.get("xp", 0.0)
        )

    # Custom player data
    c_data = data.get(
        "custom_data",
        {}
    )

    pkg.write_int32(len(c_data))

    for k, v in c_data.items():
        pkg.write_string(k)
        pkg.write_string(v)

    # Final stamina/eitr values
    pkg.write_float(
        data.get("stamina", 50.0)
    )

    pkg.write_float(
        data.get("max_eitr", 0.0)
    )

    pkg.write_float(
        data.get("eitr", 0.0)
    )

    build_ui_hex = data.get(
        "build_ui_data_hex",
        ""
    )

    if build_ui_hex:
        build_ui_data = bytes.fromhex(
            build_ui_hex
        )
    else:
        build_ui_data = b""

    pkg.write_byte_array(
        build_ui_data
    )

    if version >= 34:
        for field in ("pseudo_drop_counters", "item_upgrade_seeds"):
            values = data.get(field, {})
            pkg.write_int32(len(values))
            for key, value in values.items():
                # JSON object keys become strings on export/import.
                pkg.write_int32(int(key))
                pkg.write_int32(value)

    pkg.stream.write(bytes.fromhex(data.get("trailing_data_hex", "")))

    return pkg.get_bytes().hex()
