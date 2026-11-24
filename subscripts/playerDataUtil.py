from decimal import Decimal, InvalidOperation

from subscripts.binaryCodec import (
    BinaryReader as PlayerDataReader, BinaryWriter as PlayerDataWriter,
    decode_hex, require_array, require_bool, require_int, require_object,
)
from subscripts.itemDatabase import load_item_database

ITEM_HASH_TO_PREFAB = load_item_database()

def reload_item_database(items=None):
    updated = load_item_database() if items is None else items
    ITEM_HASH_TO_PREFAB.clear()
    ITEM_HASH_TO_PREFAB.update(updated)


def display_item_prefab(item):
    return item.get("prefab") or ITEM_HASH_TO_PREFAB.get(item.get("prefab_hash"), "")

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

def read_string_list(pkg, field):
    return [pkg.read_string() for _ in range(pkg.read_count(field, 1))]


def read_dictionary(pkg, field, key, value, minimum_item_bytes, *, game_rejects=False):
    return pkg.read_dictionary(
        pkg.read_count(field, minimum_item_bytes), key, value, field, game_rejects=game_rejects,
    )


def item_is_cheated(item, inventory_version):
    """Return the effective saved flag. Legacy bytes have no effective flag."""
    return inventory_version == 110 and bool(item.get("cheated", item.get("cheated_flags", 0) & 1))


def unpack_player_data_hex(hex_string: str) -> dict:
    if hex_string is None:
        return {}
    return parse_player_data(decode_hex(hex_string, "player_data_hex"))

def parse_player_data(raw_bytes: bytes) -> dict:
    """Decode Player 33/34 with Inventory 109/110, retaining opaque bytes."""
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
    pkg.check_remaining(item_count * 9, "inventory records")

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
            "durability": durability_raw / 100,
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
        item["prefab"] = ITEM_HASH_TO_PREFAB.get(item["prefab_hash"], "") if item["prefab_hash"] else ""

        # bit 7 = custom data present
        if flags & 128:
            custom_count = pkg.read_num_items()
        else:
            custom_count = 0

        pkg.check_remaining(custom_count * 2, "item custom_data")
        item["custom_data"] = pkg.read_dictionary(
            custom_count, pkg.read_string, pkg.read_string, "item custom_data",
        )
        # Remember the optional flags whose payload matches the usual absent-field default.
        extra_flags = sum(bit for bit, key, absent in (
            (4, "quality", 1), (8, "stack", 1), (16, "variant", 0),
            (32, "crafter_id", 0), (64, "prefab_hash", 0), (128, "custom_data", {}),
        ) if flags & bit and item[key] == absent)
        if extra_flags:
            item["extra_item_flags"] = extra_flags

        # Inventory 109 consumes this byte without interpreting any bits.
        item["cheated_flags"] = pkg.read_byte()
        item["cheated"] = item_is_cheated(item, out["inventory_version"])

        out["inventory"].append(item)


    # recipes, stations, materials, tutorials, uniques, trophies, biomes, known texts
    out["known_recipes"] = read_string_list(pkg, "known_recipes")
    out["known_stations"] = read_dictionary(
        pkg, "known_stations", pkg.read_string, pkg.read_int32, 5, game_rejects=True,
    )
    for field in ("known_material", "shown_tutorials", "uniques", "trophies", "known_biomes"):
        out[field] = read_string_list(pkg, field)
    out["known_texts"] = read_dictionary(pkg, "known_texts", pkg.read_string, pkg.read_string, 2)

    # Appearance

    out["beard"] = pkg.read_string()
    out["hair"] = pkg.read_string()

    out["skin_color"] = pkg.read_vector3()
    out["hair_color"] = pkg.read_vector3()

    out["model_index"] = pkg.read_int32()

    # foods

    food_count = pkg.read_count("food", 5)

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

    skill_count = pkg.read_count("skill", 12)

    out["skills"] = []

    for _ in range(skill_count):
        out["skills"].append({
            "id": pkg.read_int32(),
            "level": pkg.read_float(),
            "xp": pkg.read_float()
        })

    out["custom_data"] = read_dictionary(pkg, "player custom_data", pkg.read_string, pkg.read_string, 2)

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

    build_ui_data = pkg.read_byte_array("build_ui_data")

    out["build_ui_data_hex"] = build_ui_data.hex()

    # Player.Save appends these in v34, in this order. Player.Load skips both
    # for v33. Keep the signed keys/values, including seeds we cannot interpret.
    if out["version"] >= 34:
        for field in ("pseudo_drop_counters", "item_upgrade_seeds"):
            out[field] = read_dictionary(pkg, field, pkg.read_int32, pkg.read_int32, 8)

    # Retain opaque extensions to supported layouts instead of dropping bytes.
    trailing_data = pkg.stream.read()
    if trailing_data:
        out["trailing_data_hex"] = trailing_data.hex()

    return out

def write_item(pkg, item, inventory_version, field):
    item = require_object(item, field)
    durability = item.get("durability", 100.0)
    try:
        if isinstance(durability, bool) or not isinstance(durability, (int, float)):
            raise ValueError
        scaled = Decimal(str(durability)) * 100
        # Keep stored hundredths exact. Explicit fractional edits use the
        # integer-hundredths quantization from ItemData.Save.
        if not scaled.is_finite() or not -(2**31) <= scaled <= 2**31 - 1:
            raise ValueError
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"{field}.durability must fit in signed 32-bit hundredths.") from exc
    pkg.write_int32(int(scaled), f"{field}.durability")
    for key in ("grid_x", "grid_y", "world_level"):
        pkg.write_byte(item.get(key, 0), f"{field}.{key}")

    flags = require_int(item.get("extra_item_flags", 0), 0, 255, f"{field}.extra_item_flags")
    if flags & 3:
        raise ValueError(f"{field}.extra_item_flags may contain only optional-field bits 2 through 7.")
    if require_bool(item.get("picked_up", False), f"{field}.picked_up"):
        flags |= 1
    if require_bool(item.get("equipped", False), f"{field}.equipped"):
        flags |= 2

    quality = require_int(item.get("quality", 1), 0, 65535, f"{field}.quality")
    stack = require_int(item.get("stack", 1), 0, 65535, f"{field}.stack")
    variant = require_int(item.get("variant", 0), -(2**31), 2**31 - 1, f"{field}.variant")
    crafter = require_int(item.get("crafter_id", 0), -(2**63), 2**63 - 1, f"{field}.crafter_id")
    crafter_name = item.get("crafter_name", "")
    if not isinstance(crafter_name, str):
        raise ValueError(f"{field}.crafter_name must be a string.")
    if crafter_name and not (crafter or flags & 32):
        raise ValueError(f"{field}.crafter_name requires a crafter ID or an explicitly present crafter field.")

    prefab = item.get("prefab", "")
    prefab_hash = require_int(item.get("prefab_hash", 0), -(2**31), 2**31 - 1, f"{field}.prefab_hash")
    if not isinstance(prefab, str) or "\x00" in prefab:
        raise ValueError(f"{field}.prefab must be a string without null characters.")
    if prefab:
        try:
            expected_hash = get_stable_hash_code(prefab)
        except UnicodeError as exc:
            raise ValueError(f"{field}.prefab contains invalid Unicode.") from exc
        if "prefab_hash" in item and prefab_hash != expected_hash:
            raise ValueError(f"{field}.prefab and prefab_hash disagree; supply matching values or remove one.")
        prefab_hash = expected_hash
    custom = require_object(item.get("custom_data", {}), f"{field}.custom_data")
    require_int(len(custom), 0, 32767, f"{field}.custom_data count")
    for bit, present in (
        (4, quality != 1), (8, stack != 1), (16, variant != 0),
        (32, crafter != 0), (64, prefab_hash != 0), (128, bool(custom)),
    ):
        if present:
            flags |= bit

    pkg.write_byte(flags)
    if flags & 4:
        pkg.write_ushort(quality)
    if flags & 8:
        pkg.write_ushort(stack)
    if flags & 16:
        pkg.write_int32(variant)
    if flags & 32:
        pkg.write_long(crafter)
        pkg.write_string(crafter_name, f"{field}.crafter_name")
    if flags & 64:
        pkg.write_int32(prefab_hash)
    if flags & 128:
        pkg.write_num_items(len(custom))
        for key, value in custom.items():
            pkg.write_string(key, f"{field}.custom_data key")
            pkg.write_string(value, f"{field}.custom_data[{key!r}]")

    # Inventory 109's entire byte is opaque. In 110 only bit 0 is editable.
    extra = require_int(item.get("cheated_flags", 0), 0, 255, f"{field}.cheated_flags")
    if "cheated" in item:
        require_bool(item["cheated"], f"{field}.cheated")
    if inventory_version == 110:
        extra = (extra & ~1) | item_is_cheated(item, inventory_version)
    pkg.write_byte(extra)


def write_counter_dictionary(pkg, value, field):
    counters = require_object(value, field)
    keys = {}
    for key, value in counters.items():
        number = key
        if isinstance(key, str):
            try:
                number = int(key)
            except ValueError as exc:
                raise ValueError(f"{field} key {key!r} must be a signed 32-bit integer.") from exc
            if str(number) != key:
                raise ValueError(f"{field} key {key!r} must use its canonical decimal spelling.")
        require_int(number, -(2**31), 2**31 - 1, f"{field} key")
        if number in keys:
            raise ValueError(f"Duplicate key {number} in {field}.")
        keys[number] = value
    pkg.write_dictionary(keys, pkg.write_int32, pkg.write_int32, field)


def pack_player_data_hex(data: dict) -> str:
    """Serialize the supported Player layouts, preserving versions and opaque data."""
    require_object(data, "player_data")
    version = data.get("version", 33)
    inventory_version = data.get("inventory_version", 109)
    skill_version = data.get("skill_version", 2)
    if type(version) is not int or version not in (33, 34):
        raise ValueError(f"Unsupported player data version: {version}")
    if type(inventory_version) is not int or inventory_version not in (109, 110):
        raise ValueError(f"Unsupported inventory version: {inventory_version}")
    if type(skill_version) is not int or skill_version != 2:
        raise ValueError(f"Unsupported skill data version: {skill_version}")
    if version == 33 and (data.get("pseudo_drop_counters") or data.get("item_upgrade_seeds")):
        raise ValueError("Player version 33 cannot store version 34 counters or upgrade seeds")

    pkg = PlayerDataWriter()
    pkg.write_int32(version)
    for field, default in (("max_health", 25.0), ("health", 25.0), ("max_stamina", 50.0),
                           ("time_since_death", 0.0)):
        pkg.write_float(data.get(field, default), field)
    pkg.write_string(data.get("guardian_power", ""), "guardian_power")
    pkg.write_float(data.get("guardian_power_cooldown", 0.0), "guardian_power_cooldown")

    pkg.write_int32(inventory_version)
    inventory = require_array(data.get("inventory", []), "inventory")
    pkg.write_ushort(len(inventory), "inventory count")
    for index, item in enumerate(inventory):
        write_item(pkg, item, inventory_version, f"inventory[{index}]")

    for field in ("known_recipes", "known_stations", "known_material", "shown_tutorials",
                  "uniques", "trophies", "known_biomes", "known_texts"):
        if field in ("known_stations", "known_texts"):
            write_value = pkg.write_int32 if field == "known_stations" else pkg.write_string
            pkg.write_dictionary(data.get(field, {}), pkg.write_string, write_value, field)
        else:
            entries = require_array(data.get(field, []), field)
            pkg.write_int32(len(entries), f"{field} count")
            for index, entry in enumerate(entries):
                pkg.write_string(entry, f"{field}[{index}]")

    for field in ("beard", "hair"):
        pkg.write_string(data.get(field, ""), field)
    for field in ("skin_color", "hair_color"):
        pkg.write_vector3(data.get(field, [1.0, 1.0, 1.0]), field)
    pkg.write_int32(data.get("model_index", 0), "model_index")

    foods = require_array(data.get("foods", []), "foods")
    pkg.write_int32(len(foods), "foods count")
    for index, food in enumerate(foods):
        require_object(food, f"foods[{index}]")
        pkg.write_string(food.get("name", ""), f"foods[{index}].name")
        pkg.write_float(food.get("time", 0.0), f"foods[{index}].time")

    pkg.write_int32(skill_version)
    skills = require_array(data.get("skills", []), "skills")
    pkg.write_int32(len(skills), "skills count")
    for index, skill in enumerate(skills):
        require_object(skill, f"skills[{index}]")
        pkg.write_int32(skill.get("id", 0), f"skills[{index}].id")
        pkg.write_float(skill.get("level", 1.0), f"skills[{index}].level")
        pkg.write_float(skill.get("xp", 0.0), f"skills[{index}].xp")
    pkg.write_dictionary(data.get("custom_data", {}), pkg.write_string, pkg.write_string, "player custom_data")

    for field, default in (("stamina", 50.0), ("max_eitr", 0.0), ("eitr", 0.0)):
        pkg.write_float(data.get(field, default), field)
    pkg.write_byte_array(decode_hex(data.get("build_ui_data_hex", ""), "build_ui_data_hex"), "build_ui_data")

    for field in ("pseudo_drop_counters", "item_upgrade_seeds"):
        if field in data or version == 34:
            entries = require_object(data.get(field, {}), field)
            if version == 34:
                write_counter_dictionary(pkg, entries, field)
    pkg.write_bytes(decode_hex(data.get("trailing_data_hex", ""), "trailing_data_hex"))
    return pkg.get_bytes().hex()
