import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

import json

from subscripts.newCharacter import create_new_character
from subscripts.fchUtil import compile_fch, decompile_fch


BASE_DIR = Path(__file__).resolve().parent.parent
TEST_DIR = BASE_DIR / "test_new_character"

TEST_DIR.mkdir(exist_ok=True)

json_path = TEST_DIR / "new_character.json"
fch_path = TEST_DIR / "new_character.fch"


print("Creating new character...")

save_data = create_new_character("Test Viking")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(
        save_data,
        f,
        indent=2
    )

print("Compiling .fch...")

compile_fch(
    str(json_path),
    str(fch_path)
)

print("Reading .fch back...")

loaded_data = decompile_fch(
    str(fch_path)
)

print()
print("=== RESULT ===")
print(f"Character: {loaded_data['character_name']}")
print(f"Player ID: {loaded_data['player_id']}")
print(f"Start Seed: {loaded_data['start_seed']}")
print(f"Version: {loaded_data['version']}")
print(f"Profiles: {loaded_data['profile_count']}")
print(f"Stats: {loaded_data['stat_count']}")
print(f"Worlds: {len(loaded_data['worlds'])}")
print(f"Player data present: {bool(loaded_data['player_data_hex'])}")

print()
print("=== CHECKS ===")

assert loaded_data["character_name"] == "Test Viking"
assert loaded_data["version"] == 47
assert loaded_data["profile_count"] == 10
assert loaded_data["stat_count"] == 205
assert loaded_data["player_id"] == save_data["player_id"]
assert loaded_data["start_seed"] == save_data["start_seed"]
assert loaded_data["used_cheats"] is False
assert loaded_data["worlds"] == []
assert loaded_data["player_data_hex"] == save_data["player_data_hex"]

print("All checks passed!")
print()
print(f"Created: {fch_path}")
