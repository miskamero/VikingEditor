"""Conservative recognition of EAQ 3.2's saved equipment cells.

See docs/equipment-slots.md for the pinned upstream format and limitations.
Backups are evidence of dimensions, never a second editable inventory.
"""
import base64
import binascii
from collections import Counter

from subscripts.fchUtil import BinaryReader


EAQ_EQUIPMENT = ("Helmet", "Chest", "Legs", "Shoulder", "Utility", "Trinket", "Utility2", "Utility3")


def has_slot_mod_data(data):
    keys = ("eaqs_", "ExtraSlots", "EquipmentSlotInventory", "QuickSlotInventory", "ExtendedPlayerData")
    for field in ("custom_data", "known_texts"):
        values = data.get(field, {})
        if isinstance(values, dict) and any(str(key).removeprefix("<|>").startswith(keys) for key in values):
            return True
    return any(any(str(key).startswith(("eaqs_", "ExtraSlots")) for key in item.get("custom_data", {}))
               for item in data.get("inventory", []))


def eaq_equipment(data, root_save):
    """Return corroborated occupied cells, keeping references to the real items."""
    if not isinstance(root_save, dict) or not isinstance(root_save.get("player_id"), int):
        return []
    custom = data.get("custom_data", {})
    if not isinstance(custom, dict):
        return []
    # Conflicting mod storage cannot establish which topology currently owns a cell.
    for field in (custom, data.get("known_texts", {})):
        if isinstance(field, dict) and any(
                str(key).removeprefix("<|>").startswith(
                    ("ExtraSlots", "EquipmentSlotInventory", "QuickSlotInventory", "ExtendedPlayerData"))
                for key in field):
            return []
    if any(any(str(key).startswith("ExtraSlots") for key in item.get("custom_data", {}))
           for item in data.get("inventory", [])):
        return []
    try:
        row_text = custom["eaqs_visible_rows"]
        if not isinstance(row_text, str) or not row_text.isascii() or not row_text.isdecimal():
            return []
        rows = int(row_text)
        encoded = custom["eaqs_backup"]
        if not isinstance(encoded, str) or len(encoded) > 16 * 1024 * 1024:
            return []
        reader = BinaryReader(base64.b64decode(encoded, validate=True))
        if reader.read_int32() != 1:
            return []
        reader.read_string()  # Date and world name are not slot configuration.
        reader.read_string()
        count, width, height, saved_rows = (reader.read_int32() for _ in range(4))
        compressed = reader.read_byte_array()
        if (not compressed or reader.stream.read(1) or not 4 <= rows <= 253
                or (width, height, saved_rows) != (8, 3, rows) or not 0 <= count <= 24):
            return []
    except (KeyError, TypeError, ValueError, EOFError, OverflowError, binascii.Error):
        return []
    items = data.get("inventory", [])
    positions = Counter((item.get("grid_x"), item.get("grid_y")) for item in items)
    found = []
    for item in items:
        x, y = item.get("grid_x"), item.get("grid_y")
        metadata = item.get("custom_data", {})
        if (type(x) is not int or type(y) is not int or not 0 <= x < 8 or y != rows + 1
                or positions[(x, y)] != 1 or not isinstance(metadata, dict)):
            continue
        slot_id = EAQ_EQUIPMENT[x]  # Upstream indices 8..15, width 8.
        if (metadata.get("eaqs_player") != str(root_save["player_id"])
                or metadata.get("eaqs_slot") != slot_id
                or any(str(key).startswith("ExtraSlots") for key in metadata)):
            continue
        found.append((slot_id, item))
    return sorted(found, key=lambda entry: entry[1]["grid_x"])
