import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.database import reset_engine, set_db_path, init_database, get_session_factory
from app.config import load_config


@pytest.fixture(autouse=True)
def _reset_db_state():
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def shared_db(tmp_path):
    db_path = str(tmp_path / "shared-test.db")
    set_db_path(db_path)
    init_database(db_path)
    return db_path


@pytest.fixture
def config_file(tmp_path, shared_db):
    toml_path = tmp_path / "bookmark-vault.toml"
    toml_path.write_text(
        f'[database]\npath = "{shared_db}"\n\n[cli]\npage_size = 10\n',
        encoding="utf-8",
    )
    return toml_path


class TestConfiguredDbPathConsistency:
    def test_cli_and_api_read_same_config(self, monkeypatch, tmp_path, shared_db, config_file):
        monkeypatch.setattr("app.config.USER_CONFIG_DIR", tmp_path / "home")
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", tmp_path)

        reset_engine()
        cfg = load_config()

        from app.database import get_configured_db_path
        api_db_path = get_configured_db_path()

        assert cfg.db_path == api_db_path, (
            f"CLI 配置路径 ({cfg.db_path}) != database 模块路径 ({api_db_path})"
        )

    def test_data_written_by_cli_visible_to_api(self, shared_db):
        from app import crud, schemas

        db = get_session_factory(shared_db)()
        try:
            bookmark_in = schemas.BookmarkCreate(
                url="https://cli-test.com",
                title="CLI 写入的书签",
                description="通过 CRUD 层直接写入",
                tags=["cli", "test"],
            )
            created = crud.create_bookmark(db, bookmark_in)
            assert created.id is not None
        finally:
            db.close()

        from main import app
        client = TestClient(app)
        resp = client.get(f"/api/bookmarks/{created.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "CLI 写入的书签"
        assert data["url"] == "https://cli-test.com"
        tag_names = [t["name"] for t in data["tags"]]
        assert "cli" in tag_names
        assert "test" in tag_names

    def test_data_written_by_api_visible_to_cli(self, shared_db):
        from main import app

        client = TestClient(app)
        resp = client.post(
            "/api/bookmarks",
            json={
                "url": "https://api-test.com",
                "title": "API 写入的书签",
                "description": "通过 HTTP 接口写入",
                "tags": ["api", "test"],
            },
        )
        assert resp.status_code == 201
        created_id = resp.json()["id"]

        from app import crud
        db = get_session_factory(shared_db)()
        try:
            bookmark = crud.get_bookmark(db, created_id)
            assert bookmark is not None
            assert bookmark.title == "API 写入的书签"
            assert bookmark.url == "https://api-test.com"
            tag_names = [t.name for t in bookmark.tags]
            assert "api" in tag_names
            assert "test" in tag_names
        finally:
            db.close()

    def test_api_config_endpoint_matches_load_config(self, monkeypatch, tmp_path, shared_db, config_file):
        monkeypatch.setattr("app.config.USER_CONFIG_DIR", tmp_path / "home")
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", tmp_path)

        reset_engine()
        from main import app
        client = TestClient(app)

        resp = client.get("/api/config")
        assert resp.status_code == 200
        api_config = resp.json()

        cfg = load_config()

        assert os.path.abspath(api_config["db_path"]) == os.path.abspath(cfg.db_path), (
            f"API 返回 db_path={api_config['db_path']} != "
            f"load_config() 返回 db_path={cfg.db_path}"
        )

    def test_cli_command_uses_config_db_path(self, monkeypatch, tmp_path, shared_db, config_file):
        monkeypatch.setattr("app.config.USER_CONFIG_DIR", tmp_path / "home")
        monkeypatch.setattr("app.config.CWD_CONFIG_DIR", tmp_path)

        from click.testing import CliRunner
        from cli import cli

        reset_engine()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_file), "bookmark", "add",
             "-u", "https://cli-runner.com", "-t", "CLI Runner 书签", "--tag", "runner"]
        )
        assert result.exit_code == 0, f"CLI 添加书签失败: {result.output}"

        from main import app
        client = TestClient(app)
        resp = client.get("/api/bookmarks")
        assert resp.status_code == 200
        items = resp.json()["items"]
        titles = [bm["title"] for bm in items]
        assert "CLI Runner 书签" in titles

    def test_delete_on_one_side_reflects_on_other(self, shared_db):
        from main import app
        client = TestClient(app)

        create_resp = client.post(
            "/api/bookmarks",
            json={
                "url": "https://to-delete.com",
                "title": "待删除书签",
                "tags": ["delete-test"],
            },
        )
        assert create_resp.status_code == 201
        created_id = create_resp.json()["id"]

        from app import crud
        db = get_session_factory(shared_db)()
        try:
            success = crud.delete_bookmark(db, created_id)
            assert success is True
        finally:
            db.close()

        get_resp = client.get(f"/api/bookmarks/{created_id}")
        assert get_resp.status_code == 404

    def test_tag_operations_consistent(self, shared_db):
        from main import app
        client = TestClient(app)

        create_resp = client.post(
            "/api/tags",
            json={"name": "一致性测试", "color": "#00FF00"},
        )
        assert create_resp.status_code == 201

        from app import crud
        db = get_session_factory(shared_db)()
        try:
            tag = crud.get_tag_by_name(db, "一致性测试")
            assert tag is not None
            assert tag.color == "#00FF00"

            crud.update_tag(db, tag, schemas.TagUpdate(color="#0000FF"))
        finally:
            db.close()

        list_resp = client.get("/api/tags")
        assert list_resp.status_code == 200
        found = False
        for t in list_resp.json():
            if t["name"] == "一致性测试":
                assert t["color"] == "#0000FF"
                found = True
        assert found, "标签在 API 端未找到"


from app import schemas
