import os
import tempfile
from pathlib import Path

import pytest

from app.config import Config, load_config, _read_toml, _resolve_db_path


class TestConfigParsing:
    def test_default_config_values(self):
        cfg = Config()
        assert cfg.db_path == "bookmarks.db"
        assert cfg.default_tag is None
        assert cfg.sort_by == "created_at"
        assert cfg.order == "desc"
        assert cfg.page_size == 20
        assert cfg.color is True
        assert cfg.config_source is None

    def test_read_toml_nonexistent_file(self):
        result = _read_toml(Path("/nonexistent/path/config.toml"))
        assert result is None

    def test_read_toml_valid_file(self, tmp_path):
        toml_file = tmp_path / "test.toml"
        toml_file.write_text(
            '[database]\npath = "./custom.db"\n\n[cli]\npage_size = 10\n',
            encoding="utf-8",
        )
        result = _read_toml(toml_file)
        assert result is not None
        assert result["database"]["path"] == "./custom.db"
        assert result["cli"]["page_size"] == 10

    def test_read_toml_invalid_toml(self, tmp_path):
        toml_file = tmp_path / "bad.toml"
        toml_file.write_text("this is not valid toml [[[\n", encoding="utf-8")
        result = _read_toml(toml_file)
        assert result is None

    def test_resolve_db_path_absolute(self):
        result = _resolve_db_path("/tmp/abs.db", Path("/home/user/config.toml"))
        assert result == "/tmp/abs.db"

    def test_resolve_db_path_relative(self):
        config_file = Path("/home/user/projects/bookmark-vault.toml")
        result = _resolve_db_path("./data/bookmarks.db", config_file)
        expected = str((config_file.parent / "./data/bookmarks.db").resolve())
        assert result == expected


class TestLoadConfig:
    def test_load_config_no_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.config.USER_CONFIG_DIR", tmp_path / "home")
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", tmp_path / "cwd")
        cfg = load_config()
        assert cfg.db_path == "bookmarks.db"
        assert cfg.config_source is None

    def test_load_config_from_cwd(self, monkeypatch, tmp_path):
        user_dir = tmp_path / "home"
        user_dir.mkdir()
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()

        cwd_config = cwd_dir / "bookmark-vault.toml"
        cwd_config.write_text(
            '[database]\npath = "./cwd.db"\n\n[cli]\npage_size = 15\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.config.USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", cwd_dir)

        cfg = load_config()
        assert cfg.page_size == 15
        assert cfg.config_source == str(cwd_config)

    def test_load_config_cwd_overrides_user(self, monkeypatch, tmp_path):
        user_dir = tmp_path / "home"
        user_dir.mkdir()
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()

        user_config = user_dir / "bookmark-vault.toml"
        user_config.write_text(
            '[database]\npath = "/user/db.db"\n\n[cli]\npage_size = 5\n',
            encoding="utf-8",
        )

        cwd_config = cwd_dir / "bookmark-vault.toml"
        cwd_config.write_text(
            '[database]\npath = "/cwd/db.db"\n\n[cli]\npage_size = 30\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.config.USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", cwd_dir)

        cfg = load_config()
        assert cfg.page_size == 30
        assert cfg.config_source == str(cwd_config)

    def test_load_config_relative_db_path_resolved(self, monkeypatch, tmp_path):
        cwd_dir = tmp_path / "project"
        cwd_dir.mkdir()

        cwd_config = cwd_dir / "bookmark-vault.toml"
        cwd_config.write_text(
            '[database]\npath = "./data/my.db"\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.config.USER_CONFIG_DIR", tmp_path / "home")
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", cwd_dir)

        cfg = load_config()
        assert os.path.isabs(cfg.db_path)
        assert cfg.db_path.endswith("my.db")

    def test_load_config_cli_section(self, monkeypatch, tmp_path):
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        user_dir = tmp_path / "home"
        user_dir.mkdir()

        cwd_config = cwd_dir / "bookmark-vault.toml"
        cwd_config.write_text(
            '[cli]\ndefault_tag = "工作"\nsort_by = "title"\norder = "asc"\npage_size = 50\ncolor = false\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.config.USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", cwd_dir)

        cfg = load_config()
        assert cfg.default_tag == "工作"
        assert cfg.sort_by == "title"
        assert cfg.order == "asc"
        assert cfg.page_size == 50
        assert cfg.color is False

    def test_load_config_empty_default_tag(self, monkeypatch, tmp_path):
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        user_dir = tmp_path / "home"
        user_dir.mkdir()

        cwd_config = cwd_dir / "bookmark-vault.toml"
        cwd_config.write_text(
            '[cli]\ndefault_tag = ""\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("app.config.USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", cwd_dir)

        cfg = load_config()
        assert cfg.default_tag is None
