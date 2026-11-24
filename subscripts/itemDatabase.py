from pathlib import Path
import json
import os
import hashlib
import io
import re
import tempfile
from functools import lru_cache

import UnityPy
from UnityPy.enums import ClassIDType
from subscripts.fchUtil import atomic_write, read_file_snapshot

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


def cached_prefabs(contents):
    try:
        entries = json.loads(contents)["items"]
        if not isinstance(entries, dict):
            raise ValueError("expected an items object")
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Warning: could not load item database: {exc}")
        return {}
    prefabs = {}
    for key, item in entries.items():
        if isinstance(item, dict) and isinstance(item.get("prefab"), str) and item["prefab"]:
            try:
                prefabs[int(key)] = item["prefab"]
            except ValueError:
                continue
    return prefabs


def load_item_database():
    """Load the cached Valheim item database."""
    try:
        return cached_prefabs(ITEM_DATABASE_PATH.read_bytes())
    except OSError as exc:
        print(f"Warning: could not load item database: {exc}")
        return {}


@lru_cache(maxsize=1)
def load_item_icons():
    """Read optional icon metadata; older item databases remain supported."""
    try:
        data = json.loads(ITEM_DATABASE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return {}
    # A damaged entry must not disable icons for every other item.
    return {entry["prefab"]: entry["icons"]
            for entry in data["items"].values()
            if isinstance(entry, dict) and isinstance(entry.get("prefab"), str)
            and isinstance(entry.get("icons"), list)}


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


def extract_item_icons(component, sprite_cache, errors=None, *, icon_directory=None):
    """Export shared icon variants, retaining empty entries for missing sprites."""
    try:
        references = component.read().m_itemData.m_shared.m_icons
    except Exception as exc:
        if errors is not None:
            errors.append(f"Cannot read icon references: {type(exc).__name__}: {exc}")
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
            if errors is not None:
                errors.append(f"{type(exc).__name__}: {exc}")
            print(f"Warning: could not decode item icon: {exc}")
            icons.append(None)
            continue
        # Disk errors fail the update, while decoding failures above use fallback icons.
        filename = hashlib.sha256(payload).hexdigest() + ".png"
        folder = icon_directory if icon_directory is not None else ITEM_DATABASE_PATH.parent / "item_icons"
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


def has_bundle_header(path):
    with path.open("rb") as stream:
        header = stream.read(32)
    return len(header) == 32 and header.startswith(b"UnityFS\0") and int.from_bytes(header[8:12], "big") >= 6


def find_valheim_bundles(valheim_dir):
    bundles_dir = get_bundles_dir(valheim_dir)

    if not bundles_dir.is_dir():
        raise FileNotFoundError(
            f"Valheim bundles directory not found: {bundles_dir}"
        )

    files = {path.name: path for path in bundles_dir.iterdir() if path.is_file()}
    manifest = bundles_dir.parent / "manifest"
    if not manifest.is_file():
        manifest = bundles_dir.parent / "manifest_extended"
    if manifest.is_file():
        source = manifest.read_text(encoding="utf-8-sig")
        bundle_ids = set(re.findall(r"^(?:- bundle: |  bundle: |  - )([0-9a-fA-F]+)[ \t]*$", source, re.M))
        if not source.startswith("SoftRef manifest - Text\n") or not bundle_ids:
            raise ValueError(f"Cannot read the bundle list in {manifest.name}. Verify the Valheim installation.")
        missing = sorted(bundle_ids - files.keys())
        if missing:
            raise ValueError(f"Missing {len(missing)} Valheim bundle(s), including {missing[0]}. Verify the installation.")
        candidates = [files[name] for name in sorted(bundle_ids)]
        for path in candidates:
            if not has_bundle_header(path):
                raise ValueError(f"Valheim bundle {path.name} has an invalid header. Verify the installation.")
    else:
        candidates = [path for path in sorted(files.values()) if has_bundle_header(path)]
    if not candidates:
        raise ValueError(f"No Unity asset bundles were found in {bundles_dir}. Select a complete Valheim installation.")
    return candidates


def expected_catalog_prefabs(valheim_dir, snapshot):
    extended = get_bundles_dir(valheim_dir).parent / "manifest_extended"
    if not extended.is_file():
        return set()
    source = extended.read_text(encoding="utf-8-sig")
    if not source.startswith("SoftRef manifest - Text\n"):
        raise ValueError("Cannot read manifest_extended. Verify the Valheim installation.")
    prefab_names = {Path(path).stem for path in re.findall(r"^  path in bundle: ([^\n]+\.prefab)$", source, re.M)}
    # Require proven item assets when the source still advertises them. A
    # different installation can legitimately omit items from the old cache.
    previous = set(cached_prefabs(snapshot.contents).values()) if snapshot is not None else set()
    return prefab_names & (previous | {"Club", "Torch", "Wood"})


def update_item_database(valheim_dir, progress_callback=None, cancel_callback=None):
    if cancel_callback and cancel_callback():
        return None
    bundle_files = find_valheim_bundles(valheim_dir)
    previous = read_file_snapshot(ITEM_DATABASE_PATH)
    expected = expected_catalog_prefabs(valheim_dir, previous)

    env = UnityPy.Environment()

    for index, bundle_path in enumerate(bundle_files, 1):
        message = f"Loading {index}/{len(bundle_files)}"
        print(f"\r{message}", end="", flush=True)
        if progress_callback:
            progress_callback(index, len(bundle_files), message)
        if cancel_callback and cancel_callback():
            print("\nItem database update cancelled.")
            return None
        try:
            bundle = env.load_file(str(bundle_path))
            if not getattr(bundle, "files", None):
                raise ValueError("no readable assets")
        except Exception as exc:
            raise ValueError(f"Could not load Valheim bundle {bundle_path.name}: {exc}. Verify the installation.") from exc

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
    unreadable_items = set()
    readable_items = set()

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
                    id(component.assets_file),
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
                if not isinstance(shared_name, str):
                    unreadable_items.add(prefab_name)
                else:
                    readable_items.add(prefab_name)

                # Only actual localized item names.
                if (
                    isinstance(shared_name, str)
                    and shared_name.startswith("$item_")
                ):
                    items[prefab_name] = shared_name
                    item_components[prefab_name] = component

                break

            except Exception:
                continue

    if not items:
        raise ValueError("No Valheim items could be extracted. Verify the installation or try updating again.")
    missing = sorted((expected - items.keys()) | (unreadable_items - readable_items))
    if missing:
        raise ValueError(f"Incomplete item catalog: could not extract {len(missing)} item(s), including {missing[0]}.")

    ITEM_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ITEM_DATABASE_PATH.parent, prefix="item-catalog-") as directory:
        return stage_item_catalog(items, item_components, Path(directory), previous,
                                  get_bundles_dir(valheim_dir), game_objects_checked, itemdrops_checked,
                                  progress_callback, cancel_callback)


def stage_item_catalog(items, item_components, icon_directory, previous, source, game_objects_checked,
                       itemdrops_checked, progress_callback, cancel_callback):
    # Build hash -> item data.
    hash_to_item = {}

    hash_collisions = []
    sprite_cache = {}
    icon_errors = []

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
            "icons": extract_item_icons(item_components[prefab_name], sprite_cache, icon_errors,
                                        icon_directory=icon_directory),
        }

    if hash_collisions:
        collision = hash_collisions[0]
        raise ValueError(f"Item hash {collision['hash']} is shared by {collision['first']} and {collision['second']}.")
    if icon_errors:
        raise RuntimeError(f"Incomplete item icons: {icon_errors[0]}")
    if not sprite_cache:
        raise RuntimeError("No item icons could be extracted. Verify the installation and its asset files.")

    output = {
        "valheim_version": "1.0",
        "source": str(source),
        "item_count": len(hash_to_item),
        "icon_count": len(sprite_cache),
        "icon_error_count": len(icon_errors),
        "game_objects_checked": game_objects_checked,
        "itemdrops_checked": itemdrops_checked,
        "hash_collision_count": len(hash_collisions),
        "items": {
            str(prefab_hash): item
            for prefab_hash, item in sorted(hash_to_item.items())
        },
    }

    if cancel_callback and cancel_callback():
        return None
    encoded = json.dumps(output, indent=2, ensure_ascii=False).encode("utf-8")
    # Icons are immutable blobs. The existing manifest keeps referring to the
    # same files until the complete replacement manifest is published.
    folder = ITEM_DATABASE_PATH.parent / "item_icons"
    folder.mkdir(exist_ok=True)
    for staged in icon_directory.iterdir():
        if cancel_callback and cancel_callback():
            return None
        path = folder / staged.name
        payload = staged.read_bytes()
        snapshot = read_file_snapshot(path)
        if snapshot is None:
            atomic_write(path, payload, None)
        elif snapshot.contents != payload:
            raise ValueError(f"Cached icon {path.name} is damaged. Remove that icon and retry the update.")
    if cancel_callback and cancel_callback():
        return None
    atomic_write(ITEM_DATABASE_PATH, encoded, previous)
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
