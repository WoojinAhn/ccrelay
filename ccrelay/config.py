"""Configuration management."""

import json

from ccrelay.utils import CONFIG_DIR, CONFIG_FILE
from ccrelay.drive import drive_find_folder, drive_create_folder


def load_config() -> dict:
    """Load config from CONFIG_FILE.
    Returns dict with at least 'drive_folder_id'.
    If file doesn't exist, returns empty dict.
    """
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Save config to CONFIG_FILE.
    Creates CONFIG_DIR if needed.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def ensure_drive_root(config: dict) -> str:
    """Ensure ccrelay root folder exists on Drive, return its ID.
    1. Search Drive for folder named 'ccrelay'
    2. If found, use it (and update config if needed)
    3. If not found, create it at Drive root
    4. Save folder ID to config
    Returns folder ID.
    """
    folder_id = drive_find_folder("ccrelay")
    if folder_id:
        if config.get("drive_folder_id") != folder_id:
            config["drive_folder_id"] = folder_id
            save_config(config)
        return folder_id

    # Not found on Drive — create it
    folder_id = drive_create_folder("ccrelay", "root")
    config["drive_folder_id"] = folder_id
    save_config(config)
    return folder_id
