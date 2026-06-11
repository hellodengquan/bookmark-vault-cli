from __future__ import annotations

import enum
import re
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from app.database import get_session_factory, init_database
from app import crud, schemas
from app.config import Config, load_config, get_config_paths, CONFIG_FILENAME

console = Console()
err_console = Console(stderr=True)


class ExitCode(enum.IntEnum):
    OK = 0
    USAGE = 2
    NOT_FOUND = 4
    CONFLICT = 6
    DATA_ERR = 8
    UNAVAILABLE = 11


def _exit(code: ExitCode, msg: str, style: str = "red") -> None:
    err_console.print(f"[{style}]✗ {msg}[/{style}]")
    raise SystemExit(code)


def _get_db_session():
    ctx = click.get_current_context()
    cfg: Config = ctx.obj["config"]
    return get_session_factory(cfg.db_path)()


def _init_db_from_config():
    ctx = click.get_current_context()
    cfg: Config = ctx.obj["config"]
    init_database(cfg.db_path)
    console = ctx.obj["console"]
    if not cfg.color:
        console.no_color = True


def _strip_markup(text: str) -> str:
    return re.sub(r"</?mark>", "", text)


def _print_bookmark_detail(bookmark) -> None:
    tags_str = ", ".join(
        f"[cyan]{tag.name}[/cyan]" for tag in bookmark.tags
    ) if bookmark.tags else "[dim]无标签[/dim]"

    content = f"""
[bold green]标题:[/bold green] {bookmark.title}
[bold blue]URL:[/bold blue] {bookmark.url}
[bold yellow]描述:[/bold yellow] {bookmark.description or '[dim]无描述[/dim]'}

[bold magenta]标签:[/bold magenta] {tags_str}

[dim]创建时间: {bookmark.created_at.strftime('%Y-%m-%d %H:%M:%S')}
更新时间: {bookmark.updated_at.strftime('%Y-%m-%d %H:%M:%S')}
ID: {bookmark.id}[/dim]
"""
    console.print(Panel(content.strip(), title="📑 书签详情", border_style="green"))


def _print_bookmark_table(bookmarks, title: str = "📚 书签列表", total: int = 0,
                          skip: int = 0, limit: int = 0) -> None:
    table = Table(
        title=title,
        box=box.HEAVY_HEAD,
        header_style="bold bright_white on blue",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold yellow", width=5, justify="right")
    table.add_column("标题", style="bold", max_width=36, overflow="fold")
    table.add_column("URL", style="bright_blue", max_width=40, overflow="fold")
    table.add_column("描述", style="dim", max_width=30, overflow="fold")
    table.add_column("标签", style="cyan", max_width=20, overflow="fold")
    table.add_column("创建时间", style="dim", width=19)
    table.add_column("更新时间", style="dim", width=19)

    for bm in bookmarks:
        tags = ", ".join(t.name for t in bm.tags) if bm.tags else "[dim]-[/dim]"
        desc = (bm.description[:28] + "...") if bm.description and len(bm.description) > 30 else (bm.description or "[dim]-[/dim]")
        table.add_row(
            str(bm.id),
            bm.title,
            bm.url,
            desc,
            tags,
            bm.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            bm.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)
    if total > 0:
        console.print(
            f"[dim]共 {total} 条记录，显示第 {skip + 1}-{min(skip + limit, total)} 条[/dim]"
        )


def _print_search_table(items, query: str, total: int = 0,
                        skip: int = 0, limit: int = 0) -> None:
    table = Table(
        title=f"🔍 搜索结果: {query}",
        box=box.HEAVY_HEAD,
        header_style="bold bright_white on blue",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold yellow", width=5, justify="right")
    table.add_column("标题", style="bold", max_width=28, overflow="fold")
    table.add_column("摘要", style="dim italic", max_width=36, overflow="fold")
    table.add_column("标签", style="cyan", max_width=20, overflow="fold")
    table.add_column("更新时间", style="dim", width=19)

    for item in items:
        snippet = item.get("snippet") or item.get("description") or ""
        snippet_plain = _strip_markup(snippet)
        if len(snippet_plain) > 60:
            snippet_plain = snippet_plain[:57] + "..."
        tags = ", ".join(t.name for t in item["tags"]) if item["tags"] else "[dim]-[/dim]"

        table.add_row(
            str(item["id"]),
            item["title"],
            snippet_plain or "[dim]-[/dim]",
            tags,
            item["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)
    if total > 0:
        console.print(
            f"[dim]共找到 {total} 条结果，显示第 {skip + 1}-{min(skip + limit, total)} 条[/dim]"
        )


def _print_tag_table(tags) -> None:
    table = Table(
        title="🏷️  标签列表",
        box=box.HEAVY_HEAD,
        header_style="bold bright_white on blue",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold yellow", width=5, justify="right")
    table.add_column("标签名", style="bold cyan", max_width=20, overflow="fold")
    table.add_column("颜色", max_width=12)
    table.add_column("书签数", style="green", width=8, justify="right")
    table.add_column("创建时间", style="dim", width=19)

    for t in tags:
        color_val = t.get("color")
        if color_val:
            color_cell = f"[{color_val} on {color_val}]████[/] {color_val}"
        else:
            color_cell = "[dim]-[/dim]"
        table.add_row(
            str(t["id"]),
            t["name"],
            color_cell,
            str(t["bookmark_count"]),
            t["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


def _print_empty_table(entity: str, hint: str = "") -> None:
    table = Table(
        box=box.HEAVY_HEAD,
        header_style="bold bright_white on blue",
        show_lines=False,
    )
    table.add_column(entity, style="yellow", justify="center")
    msg = f"暂无{entity}"
    if hint:
        msg += f"  →  {hint}"
    table.add_row(msg)
    console.print(table)


def _coerce_tag_filter(tag_opt: Optional[str], cfg: Config) -> Optional[str]:
    if tag_opt is not None:
        return tag_opt if tag_opt else None
    return cfg.default_tag


@click.group(help="Bookmark Vault - 基于 SQLite 的本地书签管理工具")
@click.option("--db-path", "db_path", default=None,
              help=f"数据库文件路径（默认: 项目目录/bookmarks.db），可在配置文件中设置")
@click.option("--color/--no-color", "color_flag", default=None,
              help="是否启用彩色输出")
@click.option("--config", "config_path", default=None, type=click.Path(),
              help=f"指定配置文件路径（默认搜索: ~/{CONFIG_FILENAME}, ./{CONFIG_FILENAME}）")
@click.pass_context
def cli(ctx: click.Context, db_path: Optional[str], color_flag: Optional[bool],
        config_path: Optional[str]):
    from app.config import Config
    import pathlib

    if config_path:
        config_path_obj = pathlib.Path(config_path)
        cfg = _load_config_from_file(config_path_obj)
    else:
        cfg = load_config()

    if db_path:
        import os
        p = pathlib.Path(db_path)
        cfg.db_path = str(p.resolve()) if not p.is_absolute() else db_path

    if color_flag is not None:
        cfg.color = color_flag

    if not cfg.color:
        console.no_color = True
        err_console.no_color = True

    ctx.obj = {"config": cfg, "console": console}


def _load_config_from_file(path) -> Config:
    import sys
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    from pathlib import Path as _Path
    from app.config import Config, _resolve_db_path

    cfg = Config()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        _exit(ExitCode.USAGE, f"配置文件不存在: {path}")
    except Exception as e:
        _exit(ExitCode.USAGE, f"配置文件解析失败: {e}")

    cfg.config_source = str(path)
    cfg._raw = data

    database = data.get("database", {})
    if isinstance(database, dict) and "path" in database:
        cfg.db_path = _resolve_db_path(str(database["path"]), _Path(path))

    cli_cfg = data.get("cli", {})
    if isinstance(cli_cfg, dict):
        if "default_tag" in cli_cfg:
            cfg.default_tag = cli_cfg["default_tag"] if cli_cfg["default_tag"] else None
        if "sort_by" in cli_cfg:
            cfg.sort_by = str(cli_cfg["sort_by"])
        if "order" in cli_cfg:
            cfg.order = str(cli_cfg["order"])
        if "page_size" in cli_cfg:
            cfg.page_size = int(cli_cfg["page_size"])
        if "color" in cli_cfg:
            cfg.color = bool(cli_cfg["color"])

    return cfg


@click.group(help="配置管理：查看配置文件路径和当前生效配置")
def config_cmd():
    pass


@config_cmd.command("show", help="显示当前生效的配置")
@click.pass_context
def config_show(ctx: click.Context):
    cfg: Config = ctx.obj["config"]
    paths = get_config_paths()

    table = Table(
        title="⚙️  当前配置",
        box=box.HEAVY_HEAD,
        header_style="bold bright_white on blue",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("配置项", style="bold cyan", width=18)
    table.add_column("值", style="bold")
    table.add_column("来源", style="dim", width=40)

    def source(kind: str, default: bool = False) -> str:
        if kind == "cli":
            return "命令行参数"
        if cfg.config_source:
            return cfg.config_source
        if default:
            return "内置默认"
        return "—"

    table.add_row("db_path", cfg.db_path, source("config"))
    table.add_row("default_tag", cfg.default_tag or "(未设置)",
                  source("config") if cfg.default_tag else source("default", default=True))
    table.add_row("sort_by", cfg.sort_by, source("config"))
    table.add_row("order", cfg.order, source("config"))
    table.add_row("page_size", str(cfg.page_size), source("config"))
    table.add_row("color", "启用" if cfg.color else "禁用",
                  source("config") if cfg.config_source else source("default", default=True))
    table.add_row("config_source", cfg.config_source or "(未加载)", source("default", default=True))

    console.print(table)

    path_table = Table(
        title="📁 配置文件搜索路径",
        box=box.ROUNDED,
        header_style="bold magenta",
        show_lines=False,
    )
    path_table.add_column("位置", style="bold", width=10)
    path_table.add_column("路径", style="blue")

    import os
    for name, p in paths.items():
        exists = os.path.exists(p)
        status = "[green]✓ 存在[/green]" if exists else "[dim]不存在[/dim]"
        path_table.add_row(
            "用户目录" if name == "user" else "当前目录",
            f"{p}  {status}"
        )

    console.print(path_table)


@config_cmd.command("paths", help="显示配置文件搜索路径")
def config_paths():
    paths = get_config_paths()
    import os
    for name, p in paths.items():
        exists = os.path.exists(p)
        label = "用户目录" if name == "user" else "当前目录"
        status = "[green]✓[/green]" if exists else "[dim]✗[/dim]"
        console.print(f"  {status} [bold]{label}:[/bold] {p}")


@click.group(help="书签管理：增删改查、搜索、标签过滤")
def bookmark():
    pass


@click.group(help="标签管理：增删改查及标签计数")
def tag():
    pass


cli.add_command(bookmark)
cli.add_command(tag)
cli.add_command(config_cmd, name="config")


@bookmark.command("add", help="添加新书签（可同时指定多个标签）")
@click.option("--url", "-u", required=True, help="书签 URL")
@click.option("--title", "-t", required=True, help="书签标题")
@click.option("--desc", "-d", default=None, help="书签描述")
@click.option("--tag", "tags", multiple=True, help="标签名称，可多次指定")
def add_bookmark(url: str, title: str, desc: Optional[str], tags: tuple):
    _init_db_from_config()
    db = _get_db_session()
    try:
        bookmark_in = schemas.BookmarkCreate(
            url=url, title=title, description=desc, tags=list(tags) if tags else [],
        )
        bookmark = crud.create_bookmark(db, bookmark_in)
        console.print(f"[green]✓ 书签添加成功！[/green] ID: [bold]{bookmark.id}[/bold]")
        _print_bookmark_detail(bookmark)
    except ValueError as e:
        _exit(ExitCode.USAGE, f"参数错误: {e}")
    except Exception as e:
        err_msg = str(e)
        if "UNIQUE constraint" in err_msg or "already exists" in err_msg:
            _exit(ExitCode.CONFLICT, f"书签已存在: {e}")
        _exit(ExitCode.UNAVAILABLE, f"添加失败: {e}")
    finally:
        db.close()


@bookmark.command("list", help="列出书签（支持按标签过滤、排序、分页）")
@click.option("--tag", "-t", default=None, help="按标签名称过滤")
@click.option("--sort", "-s", default=None,
              type=click.Choice(["created_at", "updated_at", "title"]),
              help="排序字段")
@click.option("--order", "-o", default=None,
              type=click.Choice(["asc", "desc"]),
              help="排序方式")
@click.option("--skip", default=None, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=None, type=int, help="显示的条目数")
@click.pass_context
def list_bookmarks(ctx: click.Context, tag: Optional[str], sort: Optional[str],
                   order: Optional[str], skip: Optional[int], limit: Optional[int]):
    cfg: Config = ctx.obj["config"]

    tag_filter = _coerce_tag_filter(tag, cfg)
    sort_by = sort if sort else cfg.sort_by
    order_dir = order if order else cfg.order
    page_size = limit if limit is not None else cfg.page_size
    skip_val = skip if skip is not None else 0

    _init_db_from_config()
    db = _get_db_session()
    try:
        total, items = crud.get_bookmarks(
            db, skip=skip_val, limit=page_size, tag=tag_filter,
            sort_by=sort_by, order=order_dir
        )
        if total == 0:
            if tag_filter:
                _print_empty_table("书签", f"标签 '{tag_filter}' 下没有书签")
            else:
                _print_empty_table("书签", "使用 bookmark add 添加第一个书签")
            return

        _print_bookmark_table(items, total=total, skip=skip_val, limit=page_size)
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"查询失败: {e}")
    finally:
        db.close()


@bookmark.command("get", help="查看单个书签详情")
@click.argument("bookmark_id", type=int)
def get_bookmark(bookmark_id: int):
    _init_db_from_config()
    db = _get_db_session()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            _exit(ExitCode.NOT_FOUND, f"书签 ID={bookmark_id} 不存在")
        _print_bookmark_detail(bookmark)
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"查询失败: {e}")
    finally:
        db.close()


@bookmark.command("update", help="更新书签信息")
@click.argument("bookmark_id", type=int)
@click.option("--title", "-t", default=None, help="新标题")
@click.option("--url", "-u", default=None, help="新 URL")
@click.option("--desc", "-d", default=None, help="新描述")
@click.option("--tag", "tags", multiple=True, default=None,
              help="新的标签列表（会覆盖原有标签），可多次指定")
def update_bookmark(bookmark_id: int, title: Optional[str], url: Optional[str],
                    desc: Optional[str], tags: Optional[tuple]):
    _init_db_from_config()
    db = _get_db_session()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            _exit(ExitCode.NOT_FOUND, f"书签 ID={bookmark_id} 不存在")

        update_data = {}
        if title is not None:
            update_data["title"] = title
        if url is not None:
            update_data["url"] = url
        if desc is not None:
            update_data["description"] = desc
        if tags:
            update_data["tags"] = list(tags)

        if not update_data:
            _exit(ExitCode.USAGE, "未提供任何更新字段，请至少指定一个选项")

        try:
            bookmark_in = schemas.BookmarkUpdate(**update_data)
        except ValueError as e:
            _exit(ExitCode.USAGE, f"参数错误: {e}")

        updated = crud.update_bookmark(db, bookmark, bookmark_in)
        console.print("[green]✓ 书签更新成功！[/green]")
        _print_bookmark_detail(updated)
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"更新失败: {e}")
    finally:
        db.close()


@bookmark.command("delete", help="删除书签")
@click.argument("bookmark_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接删除")
def delete_bookmark(bookmark_id: int, yes: bool):
    _init_db_from_config()
    db = _get_db_session()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            _exit(ExitCode.NOT_FOUND, f"书签 ID={bookmark_id} 不存在")

        if not yes:
            console.print(f"[yellow]即将删除书签:[/yellow] {bookmark.title}")
            if not click.confirm("确定要删除吗？"):
                console.print("[dim]已取消删除[/dim]")
                raise SystemExit(ExitCode.OK)

        success = crud.delete_bookmark(db, bookmark_id)
        if success:
            console.print(f"[green]✓ 书签 ID={bookmark_id} 已删除[/green]")
        else:
            _exit(ExitCode.UNAVAILABLE, "删除失败")
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"删除失败: {e}")
    finally:
        db.close()


@bookmark.command("search", help="离线全文搜索书签（标题、描述、URL）")
@click.argument("query")
@click.option("--tag", "-t", default=None, help="按标签名称过滤")
@click.option("--skip", default=None, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=None, type=int, help="显示的条目数")
@click.pass_context
def search_bookmarks(ctx: click.Context, query: str, tag: Optional[str],
                     skip: Optional[int], limit: Optional[int]):
    cfg: Config = ctx.obj["config"]

    tag_filter = _coerce_tag_filter(tag, cfg)
    page_size = limit if limit is not None else cfg.page_size
    skip_val = skip if skip is not None else 0

    _init_db_from_config()
    db = _get_db_session()
    try:
        total, items = crud.search_bookmarks(
            db, query=query, skip=skip_val, limit=page_size, tag=tag_filter
        )
        if total == 0:
            hint = f"标签 '{tag_filter}' 下" if tag_filter else ""
            _print_empty_table("搜索结果", f"{hint}未找到与 '{query}' 相关的书签")
            return

        _print_search_table(items, query, total=total, skip=skip_val, limit=page_size)
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"搜索失败: {e}")
    finally:
        db.close()


@tag.command("list", help="列出所有标签（含书签数量）")
@click.option("--skip", default=0, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=None, type=int, help="显示的条目数")
@click.pass_context
def list_tags(ctx: click.Context, skip: int, limit: Optional[int]):
    cfg: Config = ctx.obj["config"]
    page_size = limit if limit is not None else cfg.page_size

    _init_db_from_config()
    db = _get_db_session()
    try:
        tags = crud.get_tags_with_count(db, skip=skip, limit=page_size)
        if not tags:
            _print_empty_table("标签", "使用 tag add 创建第一个标签")
            return

        _print_tag_table(tags)
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"查询失败: {e}")
    finally:
        db.close()


@tag.command("add", help="创建新标签")
@click.argument("name")
@click.option("--color", "-c", default=None, help="标签颜色（如 #FF5733）")
def add_tag(name: str, color: Optional[str]):
    _init_db_from_config()
    db = _get_db_session()
    try:
        existing = crud.get_tag_by_name(db, name)
        if existing is not None:
            _exit(ExitCode.CONFLICT, f"标签 '{name}' 已存在（ID={existing.id}）")

        try:
            tag_in = schemas.TagCreate(name=name, color=color)
        except ValueError as e:
            _exit(ExitCode.USAGE, f"参数错误: {e}")

        tag = crud.create_tag(db, tag_in)
        console.print(f"[green]✓ 标签 '{tag.name}' 创建成功！[/green] ID: [bold]{tag.id}[/bold]")
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"创建失败: {e}")
    finally:
        db.close()


@tag.command("update", help="更新标签信息")
@click.argument("tag_id", type=int)
@click.option("--name", "-n", default=None, help="新标签名称")
@click.option("--color", "-c", default=None, help="新标签颜色")
def update_tag(tag_id: int, name: Optional[str], color: Optional[str]):
    _init_db_from_config()
    db = _get_db_session()
    try:
        tag = crud.get_tag(db, tag_id)
        if tag is None:
            _exit(ExitCode.NOT_FOUND, f"标签 ID={tag_id} 不存在")

        if name is None and color is None:
            _exit(ExitCode.USAGE, "未提供任何更新字段，请至少指定 --name 或 --color")

        if name and name != tag.name:
            existing = crud.get_tag_by_name(db, name)
            if existing is not None:
                _exit(ExitCode.CONFLICT, f"标签名称 '{name}' 已存在（ID={existing.id}）")

        try:
            tag_in = schemas.TagUpdate(name=name, color=color)
        except ValueError as e:
            _exit(ExitCode.USAGE, f"参数错误: {e}")

        updated = crud.update_tag(db, tag, tag_in)
        console.print(f"[green]✓ 标签更新成功！[/green] {updated.name}")
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"更新失败: {e}")
    finally:
        db.close()


@tag.command("delete", help="删除标签")
@click.argument("tag_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接删除")
def delete_tag(tag_id: int, yes: bool):
    _init_db_from_config()
    db = _get_db_session()
    try:
        tag = crud.get_tag(db, tag_id)
        if tag is None:
            _exit(ExitCode.NOT_FOUND, f"标签 ID={tag_id} 不存在")

        if not yes:
            console.print(f"[yellow]即将删除标签:[/yellow] {tag.name}")
            if not click.confirm("确定要删除吗？（书签不会被删除）"):
                console.print("[dim]已取消删除[/dim]")
                raise SystemExit(ExitCode.OK)

        success = crud.delete_tag(db, tag_id)
        if success:
            console.print(f"[green]✓ 标签 '{tag.name}' 已删除[/green]")
        else:
            _exit(ExitCode.UNAVAILABLE, "删除失败")
    except SystemExit:
        raise
    except Exception as e:
        _exit(ExitCode.UNAVAILABLE, f"删除失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
