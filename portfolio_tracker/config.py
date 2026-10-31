"""Configuration manager and persistent settings for Portfolio Tracker."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

APP_NAME = "StockACBPortfolioTracker"
LEGACY_APP_NAME = "PortfolioTracker"
ENV_DB_PATH_KEY = "PORTFOLIO_DB_PATH"


def get_default_app_dir() -> Path:
    """Return platform-standard directory for storing application configuration and defaults."""
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        app_dir = root / APP_NAME
        legacy_dir = root / LEGACY_APP_NAME
        if not app_dir.exists() and legacy_dir.exists():
            return legacy_dir
        return app_dir
    
    # macOS / Linux fallback
    home_dir = Path.home() / f".{APP_NAME.lower()}"
    legacy_home = Path.home() / f".{LEGACY_APP_NAME.lower()}"
    if not home_dir.exists() and legacy_home.exists():
        return legacy_home
    try:
        home_dir.mkdir(parents=True, exist_ok=True)
        return home_dir
    except (PermissionError, OSError):
        # Fallback to current working directory if user home has restricted permissions
        local_dir = Path.cwd() / f".{APP_NAME.lower()}"
        try:
            local_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            pass
        return local_dir


def get_default_db_path() -> Path:
    """Return default path to portfolio.db."""
    return get_default_app_dir() / "portfolio.db"


def get_config_path() -> Path:
    """Return path to config.json."""
    return get_default_app_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    """Load and return configuration dictionary from config.json."""
    config_file = get_config_path()
    if not config_file.is_file():
        return {}
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration dictionary to config.json."""
    config_file = get_config_path()
    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except (PermissionError, OSError):
        pass


def get_active_db_path() -> Path:
    """Resolve active database path according to priority:

    1. PORTFOLIO_DB_PATH environment variable (for testing & CLI overrides)
    2. 'db_path' setting in config.json (e.g. user selected Google Drive / OneDrive)
    3. Default standard path (%LOCALAPPDATA%/PortfolioTracker/portfolio.db)
    """
    env_override = os.environ.get(ENV_DB_PATH_KEY)
    if env_override and env_override.strip():
        resolved = Path(env_override.strip()).expanduser().resolve()
    else:
        cfg = load_config()
        configured_path = cfg.get("db_path")
        if configured_path and str(configured_path).strip():
            resolved = Path(str(configured_path).strip()).expanduser().resolve()
        else:
            resolved = get_default_db_path()

    # Ensure target parent directory exists if permitted
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        pass
    return resolved


def set_custom_db_path(new_path: Union[str, Path], migrate_existing: bool = True) -> Path:
    """Set custom database location in config.json and optionally migrate existing DB.

    Args:
        new_path: Target directory or file path for portfolio.db.
        migrate_existing: If True and an existing database is found at the current active path,
                         it is safely copied to the new location.

    Returns:
        The resolved Path to the active database file.
    """
    target = Path(new_path).expanduser().resolve()
    if target.is_dir() or (not target.suffix and not target.exists()):
        target = target / "portfolio.db"

    target.parent.mkdir(parents=True, exist_ok=True)

    current_db = get_active_db_path()

    if migrate_existing and current_db.is_file() and current_db != target:
        # Copy main db file
        shutil.copy2(current_db, target)
        # Check and copy WAL and SHM if present
        current_wal = Path(str(current_db) + "-wal")
        target_wal = Path(str(target) + "-wal")
        if current_wal.is_file():
            shutil.copy2(current_wal, target_wal)

        current_shm = Path(str(current_db) + "-shm")
        target_shm = Path(str(target) + "-shm")
        if current_shm.is_file():
            shutil.copy2(current_shm, target_shm)

    cfg = load_config()
    cfg["db_path"] = str(target)
    save_config(cfg)
    return target
