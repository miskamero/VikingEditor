GRID_WIDTH = 8
DEFAULT_GRID_HEIGHT = 4

MIN_STACK = 1
MAX_STACK = 9999

MIN_QUALITY = 1
MAX_QUALITY = 99

MIN_VARIANT = 0
MAX_VARIANT = 99

MIN_DURABILITY = 0.0
MAX_DURABILITY = 99999.0


def validate_item(item, player_data=None):
    errors = []

    if not isinstance(item, dict):
        return ["Item data must be a dictionary."]

    prefab = item.get("prefab")

    if not isinstance(prefab, str):
        errors.append("Prefab must be a string.")
    elif not prefab.strip():
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
    for field in ("equipped", "picked_up"):
        if field in item and not isinstance(item[field], bool):
            errors.append(f"{field} must be a boolean.")

    # Crafter ID
    crafter_id = item.get("crafter_id", 0)

    if not isinstance(crafter_id, int) or isinstance(crafter_id, bool):
        errors.append("Crafter ID must be an integer.")

    # Crafter name
    crafter_name = item.get("crafter_name", "")

    if not isinstance(crafter_name, str):
        errors.append("Crafter name must be a string.")

    # Custom data
    custom_data = item.get("custom_data", {})

    if not isinstance(custom_data, dict):
        errors.append("Custom data must be a dictionary.")

    return errors


def is_valid_item(item, player_data=None):
    """Return True when the item passes validation."""

    return not validate_item(
        item,
        player_data
    )
