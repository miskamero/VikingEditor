"""Self-check for the remembered save directory. Run: python3 tests_last_save_dir.py"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)

os.environ.setdefault("LOCALAPPDATA", tempfile.gettempdir())
os.environ.setdefault("USERPROFILE", str(Path.home()))

from ui.mainWindow import MainWindow
from ui.valheim_detection import DEFAULT_CONFIG, get_valheim_character_save_directory

last_save_dir = MainWindow.last_save_dir
remember_save_dir = MainWindow.remember_save_dir

local = get_valheim_character_save_directory()
fallback = str(next((path for path in (local, *local.parents) if path.is_dir()), Path.home()))

# No remembered directory yet -> fall back to the detected save directory.
assert last_save_dir(SimpleNamespace(config=DEFAULT_CONFIG.copy())) == fallback

# A remembered directory that still exists wins.
with tempfile.TemporaryDirectory() as tmp:
    assert last_save_dir(SimpleNamespace(config={"last_save_dir": tmp})) == tmp

# A remembered directory that was deleted must not be offered.
assert last_save_dir(SimpleNamespace(config={"last_save_dir": tmp})) == fallback

# Blank and whitespace-only values behave like "not set".
assert last_save_dir(SimpleNamespace(config={"last_save_dir": "   "})) == fallback

# Opening a file stores its parent directory, not the file itself.
with tempfile.TemporaryDirectory() as tmp:
    saved = {}
    obj = SimpleNamespace(config=DEFAULT_CONFIG.copy())
    import ui.mainWindow as mw
    original = mw.save_config
    mw.save_config = saved.update
    try:
        remember_save_dir(obj, str(Path(tmp) / "klinoff.fch"))
    finally:
        mw.save_config = original
    assert obj.config["last_save_dir"] == tmp
    assert saved["last_save_dir"] == tmp, "config must be persisted"

print("all checks passed")
