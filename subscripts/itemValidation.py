import json

GRID_WIDTH = 8
DEFAULT_GRID_HEIGHT = 4

MIN_STACK = 0
MAX_STACK = 65535

MIN_QUALITY = 0
MAX_QUALITY = 65535

MIN_VARIANT = -(2**31)
MAX_VARIANT = 2**31 - 1

MIN_DURABILITY = -(2**31) / 100
MAX_DURABILITY = (2**31 - 1) / 100

# Retain the narrower editing limits for recognized equipment slots.
EQUIPMENT_PROPERTY_LIMITS = {
    "stack": (1, 9999),
    "quality": (1, 99),
    "variant": (0, 99),
    "durability": (0.0, 99999.0),
}


def validate_item(item, player_data=None, *, inventory_rows=None, allow_hash_only=False):
    errors = []

    if not isinstance(item, dict):
        return ["Item data must be a dictionary."]

    prefab_hash = item.get("prefab_hash", 0)
    if type(prefab_hash) is not int or not -(2**31) <= prefab_hash < 2**31:
        errors.append("Prefab hash must fit in a signed 32-bit integer.")
    prefab = item.get("prefab", "" if allow_hash_only else None)

    if not isinstance(prefab, str):
        errors.append("Prefab must be a string.")
    elif not prefab.strip() and not (allow_hash_only and prefab == "" and prefab_hash):
        errors.append("Prefab cannot be empty.")

    stack = item.get("stack", 1)

    if not isinstance(stack, int) or isinstance(stack, bool):
        errors.append("Stack size must be an integer.")
    elif not MIN_STACK <= stack <= MAX_STACK:
        errors.append(
            f"Stack size must be between "
            f"{MIN_STACK} and {MAX_STACK}."
        )

    # Durability
    durability = item.get("durability", 100.0)

    if not isinstance(durability, (int, float)) or isinstance(
        durability, bool
    ):
        errors.append("Durability must be a number.")
    elif not MIN_DURABILITY <= durability <= MAX_DURABILITY:
        errors.append(
            f"Durability must be between "
            f"{MIN_DURABILITY} and {MAX_DURABILITY}."
        )

    # Grid position, 6 7 is Klinoff's fav slot nöfnöfnöf
    grid_x = item.get("grid_x")
    grid_y = item.get("grid_y")

    if not isinstance(grid_x, int) or isinstance(grid_x, bool):
        errors.append("Grid X must be an integer.")
    elif not 0 <= grid_x < GRID_WIDTH:
        errors.append(
            f"Grid X must be between 0 and {GRID_WIDTH - 1}."
        )

    if inventory_rows is None:
        inventory_rows = DEFAULT_GRID_HEIGHT
    if player_data:
        uniques = player_data.get("uniques", [])

        if "invrows 6" in uniques:
            inventory_rows = 6
        elif "invrows 5" in uniques:
            inventory_rows = 5

    if not isinstance(grid_y, int) or isinstance(grid_y, bool):
        errors.append("Grid Y must be an integer.")
    elif not 0 <= grid_y < inventory_rows:
        errors.append(
            f"Grid Y must be between 0 and {inventory_rows - 1}."
        )

    # Quality
    quality = item.get("quality", 1)

    if not isinstance(quality, int) or isinstance(quality, bool):
        errors.append("Quality must be an integer.")
    elif not MIN_QUALITY <= quality <= MAX_QUALITY:
        errors.append(
            f"Quality must be between "
            f"{MIN_QUALITY} and {MAX_QUALITY}."
        )

    # Variant
    variant = item.get("variant", 0)

    if not isinstance(variant, int) or isinstance(variant, bool):
        errors.append("Variant must be an integer.")
    elif not MIN_VARIANT <= variant <= MAX_VARIANT:
        errors.append(
            f"Variant must be between "
            f"{MIN_VARIANT} and {MAX_VARIANT}."
        )

    # Boolean values
    for field in ("equipped", "picked_up", "cheated"):
        if field in item and not isinstance(item[field], bool):
            errors.append(f"{field} must be a boolean.")

    # Crafter ID
    crafter_id = item.get("crafter_id", 0)

    if not isinstance(crafter_id, int) or isinstance(crafter_id, bool):
        errors.append("Crafter ID must be an integer.")
    elif not -(2**63) <= crafter_id <= 2**63 - 1:
        errors.append("Crafter ID must fit in a signed 64-bit integer.")

    # Crafter name
    crafter_name = item.get("crafter_name", "")

    if not isinstance(crafter_name, str):
        errors.append("Crafter name must be a string.")

    # Custom data
    custom_data = item.get("custom_data", {})

    if not isinstance(custom_data, dict):
        errors.append("Custom data must be a dictionary.")
    elif len(custom_data) > 32767:
        errors.append("Too many custom data entries for the inventory format.")
    elif not all(isinstance(k, str) and isinstance(v, str) for k, v in custom_data.items()):
        errors.append("Custom data keys and values must be strings.")

    for field in ("world_level", "cheated_flags"):
        value = item.get(field, 0)
        if type(value) is not int or not 0 <= value <= 255:
            errors.append(f"{field} must fit in an unsigned byte.")

    return errors


def is_valid_item(item, player_data=None):
    """Return True when the item passes validation."""

    return not validate_item(
        item,
        player_data
    )


def validate_clipboard_item(item, inventory_rows):
    """Check the item at its destination, including fields the form never exposes."""
    errors = validate_item(item, inventory_rows=inventory_rows, allow_hash_only=True)
    supported = {"prefab", "prefab_hash", "stack", "quality", "durability", "variant", "equipped",
                 "cheated", "cheated_flags", "custom_data", "crafter_id", "crafter_name",
                 "world_level", "picked_up", "grid_x", "grid_y"}
    if item.keys() - supported:
        errors.append("The item contains fields this save format cannot store.")
    if item.get("crafter_name") and not item.get("crafter_id"):
        errors.append("A crafter name requires a nonzero crafter ID.")
    if isinstance(item.get("prefab"), str) and "\x00" in item["prefab"]:
        errors.append("The prefab name contains a null character.")
    try:
        # Escaped, unpaired surrogates in JSON cannot be written as save strings.
        json.dumps(item, ensure_ascii=False).encode("utf-8")
    except (UnicodeError, RecursionError):
        errors.append("The item contains invalid text or nested data.")
    return errors
