import json
import re
import stat
from pathlib import Path

from subscripts.fchUtil import atomic_write, read_file_snapshot, regular_file


LEGACY_BACKUP = re.compile(r"(.+)_\d{4}-\d{2}-\d{2}_\d{6}(?:\d{6})?")
MARKER_SUFFIX = ".viking-backup.json"
VALHEIM_SAVE_FOLDERS = {"characters", "characters_local"}


def plain_directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def ownership_path(path):
    return path.with_name(path.name + MARKER_SUFFIX)


def write_backup(path, contents, source_name):
    revision = atomic_write(path, contents, None)
    data = {
        "format": "VikingEditor backup 1",
        "filename": path.name,
        "source": source_name,
        "sha256": revision.digest,
        "device": revision.device,
        "inode": revision.inode,
    }
    # Publish ownership last. A backup without a marker is still recoverable.
    atomic_write(ownership_path(path), json.dumps(data).encode("utf-8"), None)


def owned_backup(root, path):
    """Return (recovery snapshot, original filename) only for a proven backup."""
    if (path.suffix.lower() != ".fch" or path.parent.parent != root
            or path.parent.name.lower() in VALHEIM_SAVE_FOLDERS):
        return None
    try:
        if not plain_directory(path.parent):
            return None
        marker = ownership_path(path)
        info = marker.lstat()
        if not regular_file(info) or info.st_size > 4096:
            return None
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        source = data.get("source")
        if (data.get("format") != "VikingEditor backup 1" or data.get("filename") != path.name
                or not isinstance(source, str) or Path(source).name != source
                or not source.lower().endswith(".fch")):
            return None
        snapshot = read_file_snapshot(path)
    except (OSError, ValueError, RecursionError):
        return None
    if snapshot is None:
        return None
    revision = snapshot.revision
    if (not revision.inode or type(data.get("inode")) is not int or type(data.get("device")) is not int
            or revision.inode != data.get("inode")
            or revision.device != data.get("device") or revision.digest != data.get("sha256")):
        return None
    return snapshot, source


def managed_backups(root, directory):
    if directory.parent != root or not plain_directory(directory):
        return
    for path in directory.glob("*.fch"):
        owned = owned_backup(root, path)
        if owned:
            yield path, owned[0].revision


def remove_owned_backup(root, path, revision):
    owned = owned_backup(root, path)
    if owned is None or owned[0].revision != revision:
        raise ValueError(f"Backup ownership or file contents changed. The file was kept.\n\n{path}")
    path.unlink()
    ownership_path(path).unlink(missing_ok=True)
