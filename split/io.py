"""File I/O operations for groups and expense records."""

import json
import os
import tempfile
from pathlib import Path

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "groups.json"


def load_all_groups(filepath=DEFAULT_DATA_PATH):
    """Loads all group data from JSON."""
    path = Path(filepath)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_group(group_id, filepath=DEFAULT_DATA_PATH):
    """Loads data for a specific group. Returns None if group not found."""
    groups = load_all_groups(filepath)
    return groups.get(group_id)


def _atomic_write_json(data, filepath):
    """Atomically serialize `data` to `filepath` as JSON.

    The updated database is written to a temporary file in the same directory
    as the destination, flushed, and synced to disk before the destination is
    replaced with :func:`os.replace`. If serialization, writing, flushing,
    syncing, or replacement fails, the original file is left untouched and the
    temporary file is removed, so the previous database is preserved.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".groups_tmp-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Remove the temporary file without masking the original exception.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_group(group_id, group_data, filepath=DEFAULT_DATA_PATH):
    """Saves or updates a specific group in the JSON store."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    groups = load_all_groups(filepath)
    groups[group_id] = group_data
    _atomic_write_json(groups, filepath)
