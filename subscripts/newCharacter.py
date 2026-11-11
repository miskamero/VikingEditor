import random
import string
import time

from subscripts.playerDataUtil import pack_player_data_hex


CURRENT_SAVE_VERSION = 47
CURRENT_STAT_COUNT = 205
CURRENT_PROFILE_COUNT = 10


def generate_player_id():
    """
    Generate a random signed 64-bit player ID.
    """

    return random.randint(
        1,
        9223372036854775807
    )


def generate_start_seed():
    """
    Generate a random character start seed.

    This is stored as character metadata and is separate
    from a world's actual seed.
    """

    characters = string.ascii_letters + string.digits

    return "".join(
        random.choice(characters)
        for _ in range(10)
    )


def create_empty_profile():
    """
    Create a completely fresh statistics profile.
    """

    return {
        "stats": [0.0] * CURRENT_STAT_COUNT,
        "known_worlds": {},
        "known_world_keys": {},
        "known_commands": {},
        "enemy_stats": [
            {},
            {},
            {},
            {},
            {}
        ],
        "item_pickup_stats": {},
        "item_craft_stats": {},
        "pickable_stats": {},
        "food_eaten_stats": {},
        "pieces_placed_stats": {},
    }


def create_empty_player_data():
    """
    Create the nested Player.Save data for a new character.
    """

    return {
        "version": 34,
        "inventory_version": 110,
        "max_health": 25.0,
        "health": 25.0,
        "max_stamina": 50.0,

        "time_since_death": 0.0,

        "guardian_power": "",
        "guardian_power_cooldown": 0.0,

        "inventory": [],

        "known_recipes": [],
        "known_stations": {},
        "known_material": [],
        "shown_tutorials": [],
        "uniques": [],
        "trophies": [],
        "known_biomes": [],
        "known_texts": {},

        "beard": "",
        "hair": "",

        "skin_color": [
            1.0,
            1.0,
            1.0
        ],

        "hair_color": [
            1.0,
            1.0,
            1.0
        ],

        "model_index": 0,

        "foods": [],

        "skills": [],

        "custom_data": {},

        "stamina": 50.0,
        "max_eitr": 0.0,
        "eitr": 0.0,

        "build_ui_data_hex": "",
        "pseudo_drop_counters": {},
        "item_upgrade_seeds": {},
    }


def create_new_character(
    character_name="New Viking"
):
    """
    Create a complete fresh Valheim character
    in the editor's internal save-data format.
    """

    player_data = create_empty_player_data()

    player_data_hex = pack_player_data_hex(
        player_data
    )

    save_data = {
        "version": CURRENT_SAVE_VERSION,

        "stat_count": CURRENT_STAT_COUNT,
        "profile_count": CURRENT_PROFILE_COUNT,

        "stats": [],

        "profiles": [
            create_empty_profile()
            for _ in range(
                CURRENT_PROFILE_COUNT
            )
        ],

        "first_spawn": False,

        "worlds": [],

        "character_name": character_name,

        "player_id": generate_player_id(),

        "start_seed": generate_start_seed(),

        "used_cheats": False,

        "date_created_unix": int(
            time.time()
        ),

        "player_data_hex": player_data_hex,
    }

    return save_data
