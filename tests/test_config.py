"""Tests for configuration persistence and database path resolution."""

import json
import os
from pathlib import Path

import pytest

from portfolio_tracker.config import (
    ENV_DB_PATH_KEY,
    get_active_db_path,
    get_config_path,
    get_default_db_path,
    load_config,
    save_config,
    set_custom_db_path,
)


def test_default_config_path():
    """Verify config path is within user profile directory."""
    cfg_path = get_config_path()
    assert cfg_path.name == "config.json"
    assert "portfolio" in str(cfg_path).lower()


def test_load_and_save_config(tmp_path, monkeypatch):
    """Test saving and loading arbitrary settings in config.json."""
    fake_config = tmp_path / "config.json"
    monkeypatch.setattr("portfolio_tracker.config.get_config_path", lambda: fake_config)

    # When file does not exist
    assert load_config() == {}

    # Save settings
    test_data = {"db_path": str(tmp_path / "custom.db"), "theme": "dark"}
    save_config(test_data)

    loaded = load_config()
    assert loaded == test_data


def test_active_db_path_resolution(tmp_path, monkeypatch):
    """Test resolution order: env var > config.json > default."""
    fake_app_dir = tmp_path / "app_dir"
    fake_config = fake_app_dir / "config.json"
    monkeypatch.setattr("portfolio_tracker.config.get_default_app_dir", lambda: fake_app_dir)
    monkeypatch.setattr("portfolio_tracker.config.get_config_path", lambda: fake_config)
    monkeypatch.delenv(ENV_DB_PATH_KEY, raising=False)

    # 1. No env var, no config -> default path
    default_path = get_default_db_path()
    assert get_active_db_path() == default_path

    # 2. Config has db_path -> config path
    custom_path = tmp_path / "google_drive" / "portfolio.db"
    save_config({"db_path": str(custom_path)})
    assert get_active_db_path() == custom_path.resolve()

    # 3. Env var set -> overrides config
    env_override_path = tmp_path / "env_override" / "test.db"
    monkeypatch.setenv(ENV_DB_PATH_KEY, str(env_override_path))
    assert get_active_db_path() == env_override_path.resolve()


def test_set_custom_db_path_migration(tmp_path, monkeypatch):
    """Test migrating existing database file to a new target path (e.g. Google Drive)."""
    fake_config = tmp_path / "config.json"
    monkeypatch.setattr("portfolio_tracker.config.get_config_path", lambda: fake_config)
    monkeypatch.delenv(ENV_DB_PATH_KEY, raising=False)

    # Create an initial db file at active path
    old_db = tmp_path / "initial" / "portfolio.db"
    old_db.parent.mkdir(parents=True, exist_ok=True)
    old_db.write_text("DUMMY_SQLITE_DATA")
    monkeypatch.setattr("portfolio_tracker.config.get_default_db_path", lambda: old_db)

    # Migrate to Google Drive target folder
    gdrive_target = tmp_path / "GoogleDrive" / "PortfolioTracker" / "portfolio.db"
    resolved_target = set_custom_db_path(gdrive_target, migrate_existing=True)

    assert resolved_target == gdrive_target.resolve()
    assert gdrive_target.exists()
    assert gdrive_target.read_text() == "DUMMY_SQLITE_DATA"

    # Verify config was updated
    cfg = load_config()
    assert cfg.get("db_path") == str(gdrive_target.resolve())
