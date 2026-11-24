import re


GRID_WIDTH = 8
DEFAULT_GRID_HEIGHT = 4
MAX_GRID_HEIGHT = 9
POCKET_KEYS = ((5, "invslot1"), (6, "invslot2"))


def _row_keys(uniques):
    for index, key in enumerate(uniques):
        parts = key.split(" ")
        if parts[0].lower() == "invrows":
            yield index, parts


def effective_inventory_rows(uniques):
    # Player.TryGetUniqueKeyValue splits on literal spaces and returns the
    # second token of the first matching key, even when that token is invalid.
    for _, parts in _row_keys(uniques):
        if len(parts) < 2:
            continue
        token = parts[1].rstrip("\0").strip(" \t\r\n\v\f")
        if re.fullmatch(r"[+-]?[0-9]+", token):
            digits = token.lstrip("+-").lstrip("0") or "0"
            if len(digits) <= 10:
                value = int(digits) * (-1 if token.startswith("-") else 1)
                if -(2**31) <= value < 2**31:
                    return min(MAX_GRID_HEIGHT, max(0, value))
        break
    # Missing or unparseable Int32 leaves the vanilla 8 x 4 inventory at spawn.
    return DEFAULT_GRID_HEIGHT


def pockets_are_editable(uniques):
    row_keys = list(_row_keys(uniques))
    if row_keys and (len(row_keys) != 1 or row_keys[0][1][1:] not in (["4"], ["5"], ["6"])):
        return False
    owned = {key for _, key in POCKET_KEYS}
    purchases = [key for key in uniques if key.lower() in owned]
    return set(purchases) <= owned and len(purchases) == len(set(purchases))


def resize_pocket_keys(uniques, old_rows, new_rows):
    """Edit the unambiguous row key and the purchase keys for crossed tiers."""
    updated = list(uniques)
    original = next(_row_keys(uniques), None)
    if original is not None:
        index, parts = original
        if new_rows == DEFAULT_GRID_HEIGHT:
            # Match the editor's default-height representation. OnSpawned
            # inserts invrows 4 without calling SetInventorySize on this spawn.
            del updated[index]
        else:
            updated[index] = f"{parts[0]} {new_rows}"
    elif new_rows != DEFAULT_GRID_HEIGHT:
        updated.append(f"invrows {new_rows}")
    for tier, key in POCKET_KEYS:
        if new_rows < tier <= old_rows:
            updated = [entry for entry in updated if entry != key]
        elif old_rows < tier <= new_rows and key not in updated:
            updated.append(key)
    return updated


def is_playable_position(x, y, rows):
    return type(x) is int and type(y) is int and 0 <= x < GRID_WIDTH and 0 <= y < rows
