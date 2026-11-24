import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from subscripts import playerDataUtil
from subscripts.newCharacter import create_empty_player_data, create_new_character

# Known Valheim stable hashes. Tests install this catalog for their own scope.
WOOD_PREFAB_HASH = -151837501
ITEMS = {WOOD_PREFAB_HASH: "Wood", -110263489: "SwordIron"}


def item(**changes):
    value = dict(prefab="Wood", grid_x=0, grid_y=0, stack=1,
                 quality=1, variant=0, durability=100.0, equipped=False,
                 picked_up=True, cheated=False, crafter_id=0,
                 crafter_name="", custom_data={}, world_level=0)
    value.update(changes)
    return value
