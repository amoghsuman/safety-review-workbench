"""Checkpoint and resume logic for interrupted runs"""

import json
from pathlib import Path

_PROJECT_ROOT    = Path(__file__).resolve().parent.parent
_CHECKPOINT_FILE = _PROJECT_ROOT / "logs" / "checkpoint.json"


def load_checkpoint() -> set:
    if not _CHECKPOINT_FILE.exists():
        return set()
    try:
        data = json.loads(_CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return set(data.get("processed_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_checkpoint(processed_ids: set) -> None:
    _CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CHECKPOINT_FILE.write_text(
        json.dumps({"processed_ids": sorted(processed_ids)}, indent=2),
        encoding="utf-8",
    )


def clear_checkpoint() -> None:
    if _CHECKPOINT_FILE.exists():
        _CHECKPOINT_FILE.unlink()


def checkpoint_exists() -> bool:
    if not _CHECKPOINT_FILE.exists():
        return False
    try:
        data = json.loads(_CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return bool(data.get("processed_ids"))
    except (json.JSONDecodeError, OSError):
        return False
