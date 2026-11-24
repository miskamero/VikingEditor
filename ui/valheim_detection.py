import os
import sys
import re
import psutil
import json
from pathlib import Path
from typing import Optional

# LOCALAPPDATA on Windows, XDG config directory elsewhere.
VALHEIM_CONFIG_PATH = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config")
    / "VikingEditor"
    / "VikingConfig.json"
)

DEFAULT_CONFIG = {
    "valheim_dir": "",
    "auto_backup": True,
    "backup_dir": "",
    "last_save_dir": "",
    "max_backups_per_character": 15,
    "is_first_launch": True
}

def is_valheim_running() -> bool:
    try:
        processes = psutil.process_iter(['pid', 'name', 'exe'])

        for proc in processes:
            try:
                proc_name = (proc.info['name'] or "").lower()

                if 'valheim' in proc_name:
                    return True

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):
                continue

        return False

    except Exception as e:
        print(f"Error checking for Valheim process: {e}")
        return False

def get_valheim_process_info() -> Optional[dict]:
    try:
        processes = psutil.process_iter(
            ['pid', 'name', 'exe', 'cmdline']
        )

        for proc in processes:
            try:
                proc_name = (proc.info['name'] or "").lower()

                if 'valheim' in proc_name:
                    return {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'exe': proc.info['exe'],
                        'cmdline': proc.info['cmdline']
                    }

            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess
            ):
                continue

        return None

    except Exception as e:
        print(f"Error getting Valheim process info: {e}")
        return None

def valheim_warning_message() -> str:
    info = get_valheim_process_info()

    if info:
        return (
            f"WARNING: Valheim is currently running!\n\n"
            f"Process Name: {info['name']}\n"
            f"Process ID: {info['pid']}\n"
            f"Executable: {info['exe']}\n\n"
            f"Please close Valheim before using this editor "
            f"to avoid potential conflicts."
        )

    return "Valheim is not currently running."

def is_valid_valheim_installation(path: Path) -> bool:
    if not path.is_dir():
        return False

    bundles_dir = (
        path
        / "valheim_Data"
        / "StreamingAssets"
        / "SoftRef"
        / "Bundles"
    )

    return bundles_dir.is_dir()

def get_steam_installations() -> list[Path]:
    installations = []

    candidates = [
        Path(base) / "Steam"
        for base in (
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("LOCALAPPDATA"),
        )
        if base
    ]

    # Linux Steam: ~/.steam/steam is the canonical symlink,
    # ~/.local/share/Steam the flatpak-less default location.
    candidates.append(Path.home() / ".steam" / "steam")
    candidates.append(Path.home() / ".local" / "share" / "Steam")

    for steam_path in candidates:
        if steam_path.is_dir() and steam_path not in installations:
            installations.append(steam_path)

    return installations

def parse_steam_library_paths(steam_path: Path) -> list[Path]:
    library_file = (
        steam_path
        / "steamapps"
        / "libraryfolders.vdf"
    )

    if not library_file.is_file():
        return []

    try:
        content = library_file.read_text(
            encoding="utf-8",
            errors="ignore"
        )
    except OSError:
        return []

    paths = []

    # Steam's VDF contains entries such as:
    #
    # "path"    "C:\\Program Files (x86)\\Steam"
    #
    # Match the path regardless of which library entry contains it.
    matches = re.findall(
        r'"path"\s*"([^"]+)"',
        content,
        re.IGNORECASE
    )

    for match in matches:
        library_path = Path(match.replace("\\\\", "\\"))

        if library_path.is_dir():
            paths.append(library_path)

    return paths

def find_valheim_installation() -> Optional[Path]:
    """
    Try to find the Valheim installation through Steam.

    Returns:
        Path: Valheim installation directory if found.
        None: If Valheim cannot be found.
    """

    checked_libraries = []

    for steam_path in get_steam_installations():

        libraries = [steam_path]

        libraries.extend(
            parse_steam_library_paths(steam_path)
        )

        for library in libraries:

            if library in checked_libraries:
                continue

            checked_libraries.append(library)

            valheim_path = (
                library
                / "steamapps"
                / "common"
                / "Valheim"
            )

            if is_valid_valheim_installation(valheim_path):
                return valheim_path

    return None

def load_config() -> dict:
    if not VALHEIM_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG.copy()

    try:
        with VALHEIM_CONFIG_PATH.open(
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return DEFAULT_CONFIG.copy()

        config = DEFAULT_CONFIG.copy()
        config.update(data)

        return config

    except (OSError, ValueError, TypeError):
        return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    VALHEIM_CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with VALHEIM_CONFIG_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            config,
            file,
            indent=2
        )

def load_saved_valheim_path() -> Optional[Path]:
    config = load_config()

    path = config.get("valheim_dir")

    if not path:
        return None

    return Path(path)


def is_steam_cloud_path(path: Path) -> bool:
    for candidate in (path.absolute(), path.resolve()):
        parts = tuple(part.lower() for part in candidate.parts)
        if any(parts[i] == "userdata" and parts[i + 2:i + 4] == ("892970", "remote")
               for i in range(len(parts) - 3)):
            return True
    return False


def get_valheim_character_save_directory(*, legacy=False) -> Path:
    folder = "characters" if legacy else "characters_local"
    windows_data = Path("AppData") / "LocalLow" / "IronGate" / "Valheim"
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE") or Path.home()) / windows_data / folder

    native = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    native = native / "unity3d" / "IronGate" / "Valheim"
    bases = [native]
    for steam in get_steam_installations():
        for library in [steam, *parse_steam_library_paths(steam)]:
            prefix = library / "steamapps" / "compatdata" / "892970" / "pfx"
            bases.append(prefix / "drive_c" / "users" / "steamuser" / windows_data)

    return next((base / folder for base in bases if (base / folder).is_dir()),
                next((base / folder for base in bases if base.is_dir()), native / folder))
