import os
import tempfile
import sys
import json
import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path

import math
import struct

# Keep the direct script entry point as well as python -m subscripts.fchUtil.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subscripts.binaryCodec import (
    BinaryReader, BinaryWriter, INT32_MAX, NonfiniteFloat, decode_hex,
    require_array, require_int, require_object,
)


SUPPORTED_PROFILE_VERSIONS = (46, 47)
MAX_PROFILES = 10
MAX_ENEMY_GROUPS = 5
KNOWN_STAT_COUNT = 205
MIN_CREATION_SECONDS = -62135596800
MAX_CREATION_SECONDS = 253402300799
STATS_BEFORE_ENEMIES = ("known_worlds", "known_world_keys", "known_commands")
STATS_AFTER_ENEMIES = ("item_pickup_stats", "item_craft_stats", "pickable_stats", "food_eaten_stats",
                       "pieces_placed_stats")
WORLD_POINTS = (("have_custom_spawn", "spawn_point"), ("have_logout_point", "logout_point"),
                ("have_death_point", "death_point"))


def verified_payload(file_bytes: bytes, *, for_editing=False) -> bytes:
    file_reader = BinaryReader(file_bytes)

    #
    # outer .fch container:
    # 
    # int package_length
    # byte[] package
    # int hash_length
    # byte[] hash
    #

    zpackage_len = file_reader.read_int32()

    if zpackage_len < 0:
        raise ValueError(f"Invalid package length: {zpackage_len}")

    zpackage_bytes = file_reader.read_bytes(zpackage_len, "signed payload")

    hash_len = file_reader.read_int32()

    if hash_len < 0:
        raise ValueError(f"Invalid hash length: {hash_len}")

    stored_hash = file_reader.read_bytes(hash_len, "SHA-512 digest")

    calculated_hash = hashlib.sha512(zpackage_bytes).digest()

    if calculated_hash != stored_hash:
        raise ValueError("SHA-512 checksum mismatch. The character file may be damaged. Use a known-good backup.")

    if for_editing and file_reader.stream.read(1):
        raise ValueError("Cannot edit character: unsupported trailing data after the checksum.")
    return zpackage_bytes


def decompile_fch(fch_path: str) -> dict:
    print(f"Reading binary save: {fch_path}")
    with open(fch_path, "rb") as f:
        return parse_fch(f.read())


def validate_nested_player(raw):
    from subscripts.playerDataUtil import parse_player_data

    try:
        parse_player_data(raw)
    except (EOFError, ValueError) as exc:
        raise type(exc)(f"Nested player data: {exc}") from exc


def parse_fch(contents: bytes, *, validate_player=True) -> dict:
    pkg = BinaryReader(verified_payload(contents, for_editing=True))
    version = pkg.read_int32()
    if version not in SUPPORTED_PROFILE_VERSIONS:
        raise ValueError(f"Unsupported character profile version {version}. Editing supports versions 46 and 47.")

    stat_count = pkg.read_count("stat_count", 0)
    profile_count = pkg.read_count("profile_count", 0)
    require_int(profile_count, 0, MAX_PROFILES, "profile_count")
    # PlayerStats stores numeric stats in a dictionary rather than a fixed array.
    pkg.check_remaining(profile_count * (stat_count * 4 + 9 * 4), "statistics profiles")

    def read_stats(field):
        return pkg.read_dictionary(pkg.read_count(field, 5), pkg.read_string, pkg.read_float, field)

    profiles = []
    for index in range(profile_count):
        profile = {"stats": [pkg.read_float() for _ in range(stat_count)]}
        for field in STATS_BEFORE_ENEMIES:
            profile[field] = read_stats(f"profiles[{index}].{field}")
        group_field = f"profiles[{index}].enemy_stats"
        group_count = pkg.read_count(group_field, 0)
        require_int(group_count, 0, MAX_ENEMY_GROUPS, f"{group_field} count")
        profile["enemy_stats"] = [read_stats(f"{group_field}[{i}]") for i in range(group_count)]
        for field in STATS_AFTER_ENEMIES:
            profile[field] = read_stats(f"profiles[{index}].{field}")
        profiles.append(profile)

    first_spawn = pkg.read_bool()
    worlds = []
    seen_uids = set()
    for _ in range(pkg.read_count("world records", 60)):
        uid = pkg.read_long()
        if uid in seen_uids:
            raise ValueError(f"Duplicate world UID {uid}. Valheim rejects duplicate world records.")
        seen_uids.add(uid)
        world = {"world_id": uid}
        for flag, point in WORLD_POINTS:
            world[flag] = pkg.read_bool()
            world[point] = pkg.read_vector3()
        world["home_point"] = pkg.read_vector3()
        world["map_data_hex"] = pkg.read_byte_array("world map").hex() if pkg.read_bool() else None
        worlds.append(world)

    save_data = {
        "version": version, "stat_count": stat_count, "profile_count": profile_count,
        "stats": [], "profiles": profiles, "first_spawn": first_spawn, "worlds": worlds,
        "character_name": pkg.read_string(), "player_id": pkg.read_long(), "start_seed": pkg.read_string(),
        "used_cheats": pkg.read_bool(),
        "date_created_unix": require_int(pkg.read_long(), MIN_CREATION_SECONDS, MAX_CREATION_SECONDS,
                                         "date_created_unix"),
    }
    nested = pkg.read_byte_array("nested player data") if pkg.read_bool() else None
    if pkg.stream.read(1):
        raise ValueError("Cannot edit character: unsupported trailing data in the signed payload.")
    if validate_player and nested is not None:
        validate_nested_player(nested)
    save_data["player_data_hex"] = None if nested is None else nested.hex()
    print("Successfully unpacked save.")
    return save_data


def unique_json_object(pairs):
    parsed = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError(f"Duplicate JSON key {key!r}; supply a single value.")
        parsed[key] = value
    return parsed


def json_ready(value):
    if isinstance(value, NonfiniteFloat):
        return {"float32_hex": value.raw.hex()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"float32_hex": struct.pack("<f", value).hex()}
    if isinstance(value, dict):
        return {key: json_ready(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(entry) for entry in value]
    return value


def character_json(save_data):
    return (json.dumps(json_ready(save_data), indent=4, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def decoded_character(save_data):
    from subscripts.playerDataUtil import unpack_player_data_hex

    decoded = dict(save_data)
    raw = decoded.pop("player_data_hex")
    decoded["player_data"] = None if raw is None else unpack_player_data_hex(raw)
    return decoded


def nested_player_bytes(save_data):
    from subscripts.playerDataUtil import pack_player_data_hex

    source = save_data.get("player_data_hex")
    raw = None if source is None else decode_hex(source, "player_data_hex")
    if raw is not None:
        validate_nested_player(raw)
    if "player_data" not in save_data:
        return raw
    player = save_data["player_data"]
    decoded = None if player is None else bytes.fromhex(pack_player_data_hex(player))
    if "player_data_hex" in save_data and decoded != raw:
        raise ValueError(
            "player_data and player_data_hex disagree. Remove player_data_hex to compile the decoded edits, "
            "or remove player_data to compile the original hexadecimal payload."
        )
    return decoded


def compile_fch(json_path: str, fch_path: str):
    print(f"Reading JSON file: {json_path}")
    with open(json_path, "r", encoding="utf-8-sig") as source:
        save_data = json.load(source, object_pairs_hook=unique_json_object)
    return write_fch(save_data, fch_path)


def encode_fch(save_data: dict) -> bytes:
    require_object(save_data, "character")
    pkg = BinaryWriter()
    version = save_data.get("version", 46)
    if type(version) is not int or version not in SUPPORTED_PROFILE_VERSIONS:
        raise ValueError(f"Unsupported save version for writing: {version}")
    pkg.write_int32(version)

    stat_count = require_int(save_data.get("stat_count", KNOWN_STAT_COUNT), 0, INT32_MAX, "stat_count")
    profile_count = require_int(save_data.get("profile_count", MAX_PROFILES), 0, MAX_PROFILES, "profile_count")
    pkg.write_int32(stat_count)
    pkg.write_int32(profile_count)
    profiles = require_array(save_data.get("profiles", []), "profiles")
    if len(profiles) != profile_count:
        raise ValueError(f"Expected {profile_count} profiles, but JSON contains {len(profiles)}.")

    for index, profile in enumerate(profiles):
        field = f"profiles[{index}]"
        require_object(profile, field)
        stats = require_array(profile.get("stats", []), f"{field}.stats")
        if len(stats) != stat_count:
            raise ValueError(f"Profile {index}: expected {stat_count} stats, got {len(stats)}.")
        for stat_index, stat in enumerate(stats):
            pkg.write_float(stat, f"{field}.stats[{stat_index}]")
        for entry in STATS_BEFORE_ENEMIES:
            pkg.write_dictionary(profile.get(entry, {}), pkg.write_string, pkg.write_float, f"{field}.{entry}")
        groups = require_array(profile.get("enemy_stats", []), f"{field}.enemy_stats")
        pkg.write_int32(require_int(len(groups), 0, MAX_ENEMY_GROUPS, f"{field}.enemy_stats count"))
        for group_index, group in enumerate(groups):
            pkg.write_dictionary(group, pkg.write_string, pkg.write_float, f"{field}.enemy_stats[{group_index}]")
        for entry in STATS_AFTER_ENEMIES:
            pkg.write_dictionary(profile.get(entry, {}), pkg.write_string, pkg.write_float, f"{field}.{entry}")

    pkg.write_bool(save_data.get("first_spawn", False), "first_spawn")
    worlds = require_array(save_data.get("worlds", []), "worlds")
    pkg.write_int32(len(worlds), "worlds count")
    seen_uids = set()
    for index, world in enumerate(worlds):
        field = f"worlds[{index}]"
        require_object(world, field)
        uid = world.get("world_id")
        pkg.write_long(uid, f"{field}.world_id")
        if uid in seen_uids:
            raise ValueError(f"Duplicate world UID {uid}. Valheim rejects duplicate world records.")
        seen_uids.add(uid)
        for flag, point in WORLD_POINTS:
            pkg.write_bool(world.get(flag), f"{field}.{flag}")
            pkg.write_vector3(world.get(point), f"{field}.{point}")
        pkg.write_vector3(world.get("home_point"), f"{field}.home_point")
        map_data = world.get("map_data_hex")
        pkg.write_bool(map_data is not None)
        if map_data is not None:
            name = f"{field}.map_data_hex"
            pkg.write_byte_array(decode_hex(map_data, name), name)

    pkg.write_string(save_data.get("character_name", "Viking"), "character_name")
    pkg.write_long(save_data.get("player_id", 0), "player_id")
    pkg.write_string(save_data.get("start_seed", ""), "start_seed")
    pkg.write_bool(save_data.get("used_cheats", False), "used_cheats")
    created = require_int(save_data.get("date_created_unix", 0), MIN_CREATION_SECONDS, MAX_CREATION_SECONDS,
                          "date_created_unix")
    pkg.write_long(created)
    player = nested_player_bytes(save_data)
    pkg.write_bool(player is not None)
    if player is not None:
        pkg.write_byte_array(player, "nested player data")

    payload = pkg.get_bytes()
    framed = BinaryWriter()
    framed.write_byte_array(payload, "character payload")
    framed.write_byte_array(hashlib.sha512(payload).digest(), "SHA-512 checksum")
    return framed.get_bytes()


_UNINSPECTED = object()


def write_fch(save_data: dict, fch_path: str, *, destination=_UNINSPECTED):
    if destination is _UNINSPECTED:
        destination = read_file_snapshot(fch_path)
    contents = encode_fch(save_data)
    if destination is not None:
        parse_fch(destination.contents)
    revision = atomic_write(fch_path, contents, destination)
    print(f"Successfully compiled and hashed! File created at: {fch_path}")
    return revision


class RevisionConflict(OSError):
    def __init__(self, path):
        super().__init__(f"The file was changed, replaced, or removed externally.\n\n{path}")


@dataclass(frozen=True)
class FileRevision:
    digest: str
    device: int
    inode: int


@dataclass(frozen=True)
class FileSnapshot:
    contents: bytes
    revision: FileRevision


def regular_file(info):
    return stat.S_ISREG(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _read_stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _revision(contents, info):
    return FileRevision(hashlib.sha256(contents).hexdigest(), info.st_dev, info.st_ino)


def read_file_snapshot(path):
    """Read one regular file revision, or return None for an unoccupied path."""
    path = Path(path)
    try:
        entry = path.lstat()
    except FileNotFoundError:
        return None
    if not regular_file(entry):
        raise ValueError(f"Expected a regular file at {path}.")
    try:
        with path.open("rb") as source:
            before = os.fstat(source.fileno())
            if _read_stamp(entry) != _read_stamp(before):
                raise RevisionConflict(path)
            contents = source.read()
            after = os.fstat(source.fileno())
        entry = path.lstat()
    except FileNotFoundError as exc:
        raise RevisionConflict(path) from exc
    if not regular_file(entry) or not (_read_stamp(before) == _read_stamp(after) == _read_stamp(entry)):
        raise RevisionConflict(path)
    return FileSnapshot(contents, _revision(contents, after))


def require_revision(path, snapshot, expected):
    current = snapshot.revision if snapshot is not None else None
    if current != expected:
        raise RevisionConflict(path)


def require_destination_revision(path, expected):
    try:
        snapshot = read_file_snapshot(path)
    except ValueError as exc:
        raise RevisionConflict(path) from exc
    require_revision(path, snapshot, expected)
    return snapshot


def atomic_write(fch_path, contents, destination):
    # Finish writing on the same filesystem before replacing an existing character.
    output = tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(fch_path)), delete=False)
    temporary_path = output.name
    try:
        with output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        revision = _revision(contents, os.stat(temporary_path))
        if destination is None:
            # Publish a complete file only if the name is still vacant.
            try:
                if os.name == "nt":
                    os.rename(temporary_path, fch_path)
                else:
                    os.link(temporary_path, fch_path)
            except FileExistsError as exc:
                raise RevisionConflict(fch_path) from exc
        else:
            # Neither POSIX rename nor Windows MoveFileEx offers compare-and-replace.
            require_destination_revision(fch_path, destination.revision)
            os.replace(temporary_path, fch_path)
        return revision
    finally:
        Path(temporary_path).unlink(missing_ok=True)

def main(argv):
    if len(argv) != 3 or argv[0].lower() not in {"unpack", "pack"}:
        print("Usage: python -m subscripts.fchUtil unpack <character.fch> <output.json>\n"
              "       python -m subscripts.fchUtil pack <input.json> <output.fch>", file=sys.stderr)
        return 1
    mode, source, target = argv
    try:
        if mode.lower() == "pack":
            compile_fch(source, target)
        else:
            if Path(target).suffix.lower() != ".json":
                raise ValueError("Choose a destination with the .json extension.")
            if Path(target).exists() and os.path.samefile(source, target):
                raise ValueError("Choose a JSON destination separate from the source character.")
            data = decoded_character(decompile_fch(source))
            atomic_write(target, character_json(data), read_file_snapshot(target))
            print(f"JSON created at: {target}")
    except (OSError, ValueError, EOFError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
