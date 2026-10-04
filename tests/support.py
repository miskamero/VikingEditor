import os
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from subscripts import itemDatabase

# avoid reading the user's cached item database when the parser is imported
ITEMS = {itemDatabase.get_stable_hash_code(name): name for name in ("Wood", "SwordIron")}
with patch.object(itemDatabase, "load_item_database", return_value=ITEMS):
    from subscripts import playerDataUtil
    from subscripts.newCharacter import create_empty_player_data, create_new_character


def item(**changes):
    value = dict(prefab="Wood", grid_x=0, grid_y=0, stack=1,
                 quality=1, variant=0, durability=100.0, equipped=False,
                 picked_up=True, cheated=False, crafter_id=0,
                 crafter_name="", custom_data={}, world_level=0)
    value.update(changes)
    return value
