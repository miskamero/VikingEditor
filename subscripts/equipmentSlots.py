"""Conservative recognition of EAQ 3.2's saved equipment cells.

See docs/equipment-slots.md for supported layouts and limitations.
Backups are evidence of dimensions, never a second editable inventory.
"""
import base64
import binascii
from collections import Counter

from subscripts.fchUtil import BinaryReader


EAQ_EQUIPMENT = ("Helmet", "Chest", "Legs", "Shoulder", "Utility", "Trinket", "Utility2", "Utility3")
OTHER_SLOT_KEYS = ("ExtraSlots", "EquipmentSlotInventory", "QuickSlotInventory", "ExtendedPlayerData")
SLOT_KEYS = ("eaqs_", *OTHER_SLOT_KEYS)


def _metadata(item):
    value = item.get("custom_data", {})
    return value if isinstance(value, dict) else {}


def _has_keys(values, prefixes):
    return isinstance(values, dict) and any(str(key).removeprefix("<|>").startswith(prefixes) for key in values)


def item_has_slot_mod_data(item):
    return _has_keys(_metadata(item), SLOT_KEYS)


def has_slot_mod_data(data):
    """Whether bulk/dimension changes could affect stored slot-mod data.

    Return-slot memory does not prove a layout or an active mod. Keep the
    protection: mods can also put real slots inside the usual vanilla grid.
    """
    return (any(_has_keys(data.get(field, {}), SLOT_KEYS) for field in ("custom_data", "known_texts"))
            or any(item_has_slot_mod_data(item) for item in data.get("inventory", [])))


def eaq_inventory_rows(data):
    """Saved ordinary-row boundary for the verified width-8 EAQ layout, or None."""
    custom = data.get("custom_data", {})
    if not isinstance(custom, dict):
        return None
    # Conflicting mod storage cannot establish which topology currently owns a cell.
    if (any(_has_keys(field, OTHER_SLOT_KEYS) for field in (custom, data.get("known_texts", {})))
            or any(_has_keys(_metadata(item), OTHER_SLOT_KEYS) for item in data.get("inventory", []))):
        return None
    try:
        row_text = custom["eaqs_visible_rows"]
        if not isinstance(row_text, str) or not row_text.isascii() or not row_text.isdecimal():
            return None
        rows = int(row_text)
        encoded = custom["eaqs_backup"]
        if not isinstance(encoded, str) or len(encoded) > 16 * 1024 * 1024:
            return None
        reader = BinaryReader(base64.b64decode(encoded, validate=True))
        if reader.read_int32() != 1:
            return None
        reader.read_string()  # Date and world name are not slot configuration.
        reader.read_string()
        count, width, height, saved_rows = (reader.read_int32() for _ in range(4))
        compressed = reader.read_byte_array()
        # CaptureBaseRows/SetBaseRows permit rows mods to reduce the base to 1.
        if (not compressed or reader.stream.read(1) or not 1 <= rows <= 253
                or (width, height, saved_rows) != (8, 3, rows) or not 0 <= count <= 24):
            return None
    except (KeyError, TypeError, ValueError, EOFError, OverflowError, binascii.Error):
        return None
    return rows


def eaq_equipment(data, root_save):
    """Return saved slot occupants, not a claim that the mod is currently active."""
    if not isinstance(root_save, dict) or type(root_save.get("player_id")) is not int:
        return []
    rows = eaq_inventory_rows(data)
    if rows is None:
        return []
    items = data.get("inventory", [])
    positions = Counter((item.get("grid_x"), item.get("grid_y")) for item in items
                        if type(item.get("grid_x")) is int and type(item.get("grid_y")) is int)
    found = []
    for item in items:
        x, y = item.get("grid_x"), item.get("grid_y")
        metadata = _metadata(item)
        if (type(x) is not int or type(y) is not int or not 0 <= x < 8 or y != rows + 1
                or positions[(x, y)] != 1 or not isinstance(metadata, dict)):
            continue
        slot_id = EAQ_EQUIPMENT[x]  # Upstream indices 8..15, width 8.
        if (metadata.get("eaqs_player") != str(root_save["player_id"])
                or metadata.get("eaqs_slot") != slot_id
                or _has_keys(metadata, OTHER_SLOT_KEYS)):
            continue
        found.append((slot_id, item))
    return sorted(found, key=lambda entry: entry[1]["grid_x"])
