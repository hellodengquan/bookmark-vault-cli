from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

DEFAULT_DB_NAME = "bookmarks.db"
CONFIG_FILENAME = "bookmark-vault.toml"

USER_CONFIG_DIR = Path.home()
CWD_CONFIG_DIR = Path.cwd()


@dataclass
class Config:
    db_path: str = DEFAULT_DB_NAME
    default_tag: Optional[str] = None
    sort_by: str = "created_at"
    order: str = "desc"
    page_size: int = 20
    color: bool = True

    config_source: Optional[str] = None
    _raw: Dict[str, Any] = field(default_factory=dict)


def _read_toml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _resolve_db_path(db_path: str, config_file: Path) -> str:
    p = Path(db_path)
    if p.is_absolute():
        return str(p)
    base = config_file.parent
    return str((base / p).resolve())


def load_config() -> Config:
    config = Config()

    user_config_path = USER_CONFIG_DIR / CONFIG_FILENAME
    cwd_config_path = CWD_CONFIG_DIR / CONFIG_FILENAME

    user_data = _read_toml(user_config_path)
    cwd_data = _read_toml(cwd_config_path)

    merged: Dict[str, Any] = {}
    if user_data:
        merged.update(user_data)
        config.config_source = str(user_config_path)
    if cwd_data:
        merged.update(cwd_data)
        config.config_source = str(cwd_config_path)

    config._raw = merged

    database = merged.get("database", {})
    if isinstance(database, dict):
        if "path" in database:
            raw_path = str(database["path"])
            if config.config_source:
                config.db_path = _resolve_db_path(raw_path, Path(config.config_source))
            else:
                config.db_path = raw_path

    cli = merged.get("cli", {})
    if isinstance(cli, dict):
        if "default_tag" in cli:
            config.default_tag = cli["default_tag"] if cli["default_tag"] else None
        if "sort_by" in cli:
            config.sort_by = str(cli["sort_by"])
        if "order" in cli:
            config.order = str(cli["order"])
        if "page_size" in cli:
            config.page_size = int(cli["page_size"])
        if "color" in cli:
            config.color = bool(cli["color"])

    return config


def get_config_paths() -> Dict[str, Optional[str]]:
    return {
        "user": str(USER_CONFIG_DIR / CONFIG_FILENAME),
        "cwd": str(CWD_CONFIG_DIR / CONFIG_FILENAME),
    }
