from pathlib import Path
import json
import os
import hashlib
import io
import tempfile
from functools import lru_cache

import UnityPy
from UnityPy.enums import ClassIDType

# LOCALAPPDATA on Windows, XDG config directory elsewhere.
# Same formula as VALHEIM_CONFIG_PATH; duplicated so that subscripts
# stays free of any ui import.
ITEM_DATABASE_PATH = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config")
    / "VikingEditor"
    / "valheim_items.json"
)

def get_bundles_dir(valheim_dir):
    return (
        Path(valheim_dir)
        / "valheim_Data"
        / "StreamingAssets"
        / "SoftRef"
        / "Bundles"
    )

def int32(value):
    """Convert an integer to C# signed Int32 with overflow behavior."""
    value &= 0xFFFFFFFF

    if value >= 0x80000000:
        value -= 0x100000000

    return value


def get_stable_hash_code(text):
    """
    Exact equivalent of Valheim's C# GetStableHashCode().
    """

    encoded = text.encode("utf-16-le")

    chars = [
        int.from_bytes(encoded[i:i + 2], "little")
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


def get_script_class_name(component):
    try:
        mono = component.read()

        if not mono.m_Script:
            return None

        script = mono.m_Script.deref()

        if script is None:
            return None

        return script.read().m_ClassName

    except Exception:
        return None


def get_item_shared_name(component):
    """Return ItemDrop.m_itemData.m_shared.m_name."""

    try:
        mono = component.read()

        item_data = mono.m_itemData

        if item_data is None:
            return None

        shared = item_data.m_shared

        if shared is None:
            return None

        return shared.m_name

    except Exception:
        return None


def load_item_database():
    """Load the cached Valheim item database."""

    try:
        with ITEM_DATABASE_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return {
            int(prefab_hash): item["prefab"]
            for prefab_hash, item in data.get("items", {}).items()
        }

    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Warning: could not load item database: {exc}")
        return {}


@lru_cache(maxsize=1)
def load_item_icons():
    """Read optional icon metadata; older item databases remain supported."""
    try:
        data = json.loads(ITEM_DATABASE_PATH.read_text(encoding="utf-8"))
        return {entry["prefab"]: entry.get("icons", [])
                for entry in data.get("items", {}).values()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def get_item_icon_path(prefab, variant=0):
    icons = load_item_icons().get(prefab, [])
    if not isinstance(icons, list) or not icons:
        return None
    if not isinstance(variant, int) or not 0 <= variant < len(icons):
        variant = 0
    for name in (icons[variant], icons[0]):
        # Only content-addressed PNG names inside our own cache are accepted.
        if (isinstance(name, str) and len(name) == 68 and name.endswith(".png")
                and all(c in "0123456789abcdef" for c in name[:-4])):
            path = ITEM_DATABASE_PATH.parent / "item_icons" / name
            if path.is_file():
                return path
    return None


def extract_item_icons(component, sprite_cache):
    """Export shared icon variants, retaining empty entries for missing sprites."""
    try:
        references = component.read().m_itemData.m_shared.m_icons
    except Exception:
        return []
    icons = []
    for reference in references or []:
        try:
            sprite = reference.deref()
            if sprite is None:
                icons.append(None)
                continue
            key = (id(sprite.assets_file), sprite.path_id)
            if key in sprite_cache:
                icons.append(sprite_cache[key])
                continue
            # UnityPy handles sprite atlas cropping and alpha reconstruction.
            image = sprite.read().image.convert("RGBA")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            payload = buffer.getvalue()
        except Exception as exc:
            print(f"Warning: could not decode item icon: {exc}")
            icons.append(None)
            continue
        # Disk errors fail the update, while decoding failures above use fallback icons.
        filename = hashlib.sha256(payload).hexdigest() + ".png"
        folder = ITEM_DATABASE_PATH.parent / "item_icons"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as output:
            temporary = Path(output.name)
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        sprite_cache[key] = filename
        icons.append(filename)
    return icons


def find_valheim_bundles(valheim_dir):
    bundles_dir = get_bundles_dir(valheim_dir)

    if not bundles_dir.is_dir():
        raise FileNotFoundError(
            f"Valheim bundles directory not found: {bundles_dir}"
        )

    return [
        path
        for path in bundles_dir.iterdir()
        if path.is_file()
    ]


def update_item_database(valheim_dir, progress_callback=None, cancel_callback=None):
    bundle_files = find_valheim_bundles(valheim_dir)

    if bundle_files is None:
        raise FileNotFoundError(
            f"this error should not be possible? please make a bug report with this message: {valheim_dir}"
        )

    print("Loading Valheim bundles...")

    env = UnityPy.Environment()

    for index, bundle_path in enumerate(bundle_files, 1):
        message = f"Loading {index}/{len(bundle_files)}"
        print(f"\r{message}", end="", flush=True)
        if progress_callback:
            progress_callback(index, len(bundle_files), message)
        if cancel_callback and cancel_callback():
            print("\nItem database update cancelled.")
            return None
        env.load_file(str(bundle_path))

    print()
    print("All bundles loaded.")
    print()

    if progress_callback:
        progress_callback(
            len(bundle_files),
            len(bundle_files),
            "Finalizing, just a moment..."
        )

    script_cache = {}

    # prefab name -> localized shared name
    items = {}
    item_components = {}

    game_objects_checked = 0
    itemdrops_checked = 0

    for obj in env.objects:

        if cancel_callback and cancel_callback():
            return None

        if obj.type != ClassIDType.GameObject:
            continue

        game_objects_checked += 1

        try:
            prefab_name = obj.peek_name()
        except Exception:
            continue

        if not prefab_name:
            continue

        try:
            game_object = obj.read()
        except Exception:
            continue

        for entry in game_object.m_Component:

            try:
                component = entry.component.deref()

                if component is None:
                    continue

                if component.type != ClassIDType.MonoBehaviour:
                    continue

                cache_key = (
                    component.assets_file.name,
                    component.path_id,
                )

                if cache_key not in script_cache:
                    script_cache[cache_key] = (
                        get_script_class_name(component)
                    )

                if script_cache[cache_key] != "ItemDrop":
                    continue

                itemdrops_checked += 1

                shared_name = get_item_shared_name(component)

                # Only actual localized item names.
                if (
                    shared_name is not None
                    and shared_name.startswith("$item_")
                ):
                    items[prefab_name] = shared_name
                    item_components[prefab_name] = component

                break

            except Exception:
                continue

    # Build hash -> item data.
    hash_to_item = {}

    hash_collisions = []
    sprite_cache = {}

    for index, (prefab_name, shared_name) in enumerate(sorted(items.items()), 1):
        if cancel_callback and cancel_callback():
            return None
        if progress_callback:
            progress_callback(index, len(items), f"Extracting item icons: {index}/{len(items)}")

        prefab_hash = get_stable_hash_code(prefab_name)

        existing = hash_to_item.get(prefab_hash)

        if existing is not None:
            if existing["prefab"] != prefab_name:
                hash_collisions.append(
                    {
                        "hash": prefab_hash,
                        "first": existing["prefab"],
                        "second": prefab_name,
                    }
                )

                continue

        hash_to_item[prefab_hash] = {
            "prefab": prefab_name,
            "shared_name": shared_name,
            "icons": extract_item_icons(item_components[prefab_name], sprite_cache),
        }

    output = {
        "valheim_version": "1.0",
        "source": str(get_bundles_dir(valheim_dir)),
        "item_count": len(hash_to_item),
        "icon_count": len(sprite_cache),
        "game_objects_checked": game_objects_checked,
        "itemdrops_checked": itemdrops_checked,
        "hash_collision_count": len(hash_collisions),
        "items": {
            str(prefab_hash): item
            for prefab_hash, item in sorted(hash_to_item.items())
        },
    }

    if hash_collisions:
        output["hash_collisions"] = hash_collisions

    ITEM_DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if cancel_callback and cancel_callback():
        return None
    # Publish only a complete database; cancelled scans leave the old one usable.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     dir=ITEM_DATABASE_PATH.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(output, file, indent=2, ensure_ascii=False)
    try:
        temporary.replace(ITEM_DATABASE_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    load_item_icons.cache_clear()

    print()
    print("========================================")
    print("Valheim item extraction complete")
    print("========================================")
    print(f"GameObjects checked:     {game_objects_checked}")
    print(f"ItemDrops checked:       {itemdrops_checked}")
    print(f"Unique item prefabs:     {len(items)}")
    print(f"Unique item hashes:      {len(hash_to_item)}")
    print(f"Hash collisions:         {len(hash_collisions)}")
    print()
    print(f"Output: {ITEM_DATABASE_PATH}")

    return {
        prefab_hash: item["prefab"]
        for prefab_hash, item in hash_to_item.items()
    }
