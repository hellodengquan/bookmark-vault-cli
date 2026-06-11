from __future__ import annotations

import re
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from app.database import SessionLocal, engine, Base
from app import crud, schemas

console = Console()


def _init_db():
    Base.metadata.create_all(bind=engine)


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


def _print_bookmark_table(bookmarks, title: str = "📚 书签列表") -> None:
    table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("标题", style="bold", overflow="fold")
    table.add_column("URL", style="blue", overflow="fold")
    table.add_column("标签", style="cyan", overflow="fold")
    table.add_column("更新时间", style="dim", width=19)

    for bm in bookmarks:
        tags = ", ".join(t.name for t in bm.tags) if bm.tags else "-"
        table.add_row(
            str(bm.id),
            bm.title,
            bm.url,
            tags,
            bm.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)


@click.group(help="Bookmark Vault - 基于 SQLite 的本地书签管理工具")
def cli():
    pass


@click.group(help="书签管理：增删改查、搜索、标签过滤")
def bookmark():
    pass


@click.group(help="标签管理：增删改查及标签计数")
def tag():
    pass


cli.add_command(bookmark)
cli.add_command(tag)


@bookmark.command("add", help="添加新书签（可同时指定多个标签）")
@click.option("--url", "-u", required=True, help="书签 URL")
@click.option("--title", "-t", required=True, help="书签标题")
@click.option("--desc", "-d", default=None, help="书签描述")
@click.option("--tag", "tags", multiple=True, help="标签名称，可多次指定")
def add_bookmark(url: str, title: str, desc: Optional[str], tags: tuple):
    _init_db()
    db = SessionLocal()
    try:
        bookmark_in = schemas.BookmarkCreate(
            url=url,
            title=title,
            description=desc,
            tags=list(tags),
        )
        bookmark = crud.create_bookmark(db, bookmark_in)
        console.print(f"[green]✓ 书签添加成功！[/green] ID: [bold]{bookmark.id}[/bold]")
        _print_bookmark_detail(bookmark)
    except Exception as e:
        console.print(f"[red]✗ 添加失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@bookmark.command("list", help="列出书签（支持按标签过滤、排序、分页）")
@click.option("--tag", "-t", default=None, help="按标签名称过滤")
@click.option("--sort", "-s", default="created_at",
              type=click.Choice(["created_at", "updated_at", "title"]),
              help="排序字段")
@click.option("--order", "-o", default="desc",
              type=click.Choice(["asc", "desc"]),
              help="排序方式")
@click.option("--skip", default=0, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=20, type=int, help="显示的条目数")
def list_bookmarks(tag: Optional[str], sort: str, order: str, skip: int, limit: int):
    _init_db()
    db = SessionLocal()
    try:
        total, items = crud.get_bookmarks(
            db, skip=skip, limit=limit, tag=tag, sort_by=sort, order=order
        )
        if total == 0:
            if tag:
                console.print(f"[yellow]ℹ 标签 '{tag}' 下没有书签[/yellow]")
            else:
                console.print("[yellow]ℹ 暂无书签，使用 'bookmark add' 添加第一个书签吧[/yellow]")
            return

        _print_bookmark_table(items)
        console.print(f"[dim]共 {total} 条记录，显示第 {skip + 1}-{min(skip + limit, total)} 条[/dim]")
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@bookmark.command("get", help="查看单个书签详情")
@click.argument("bookmark_id", type=int)
def get_bookmark(bookmark_id: int):
    _init_db()
    db = SessionLocal()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            console.print(f"[red]✗ 书签 ID={bookmark_id} 不存在[/red]")
            raise SystemExit(1)
        _print_bookmark_detail(bookmark)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        raise SystemExit(1)
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
    _init_db()
    db = SessionLocal()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            console.print(f"[red]✗ 书签 ID={bookmark_id} 不存在[/red]")
            raise SystemExit(1)

        update_data = {}
        if title is not None:
            update_data["title"] = title
        if url is not None:
            update_data["url"] = url
        if desc is not None:
            update_data["description"] = desc
        if tags is not None:
            update_data["tags"] = list(tags)

        if not update_data:
            console.print("[yellow]ℹ 未提供任何更新字段[/yellow]")
            raise SystemExit(1)

        bookmark_in = schemas.BookmarkUpdate(**update_data)
        updated = crud.update_bookmark(db, bookmark, bookmark_in)
        console.print(f"[green]✓ 书签更新成功！[/green]")
        _print_bookmark_detail(updated)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@bookmark.command("delete", help="删除书签")
@click.argument("bookmark_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接删除")
def delete_bookmark(bookmark_id: int, yes: bool):
    _init_db()
    db = SessionLocal()
    try:
        bookmark = crud.get_bookmark(db, bookmark_id)
        if bookmark is None:
            console.print(f"[red]✗ 书签 ID={bookmark_id} 不存在[/red]")
            raise SystemExit(1)

        if not yes:
            console.print(f"[yellow]即将删除书签:[/yellow] {bookmark.title}")
            if not click.confirm("确定要删除吗？"):
                console.print("[dim]已取消删除[/dim]")
                raise SystemExit(0)

        success = crud.delete_bookmark(db, bookmark_id)
        if success:
            console.print(f"[green]✓ 书签 ID={bookmark_id} 已删除[/green]")
        else:
            console.print("[red]✗ 删除失败[/red]")
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]✗ 删除失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@bookmark.command("search", help="离线全文搜索书签（标题、描述、URL）")
@click.argument("query")
@click.option("--tag", "-t", default=None, help="按标签名称过滤")
@click.option("--skip", default=0, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=20, type=int, help="显示的条目数")
def search_bookmarks(query: str, tag: Optional[str], skip: int, limit: int):
    _init_db()
    db = SessionLocal()
    try:
        total, items = crud.search_bookmarks(
            db, query=query, skip=skip, limit=limit, tag=tag
        )
        if total == 0:
            console.print(f"[yellow]ℹ 未找到与 '{query}' 相关的书签[/yellow]")
            return

        table = Table(
            title=f"🔍 搜索结果: {query}",
            box=box.ROUNDED,
            header_style="bold magenta",
            show_lines=False,
        )
        table.add_column("ID", style="dim", width=6, justify="right")
        table.add_column("标题 / 摘要", style="bold", overflow="fold")
        table.add_column("标签", style="cyan", overflow="fold")
        table.add_column("更新时间", style="dim", width=19)

        for item in items:
            snippet = item.get("snippet") or item.get("description") or ""
            snippet_plain = _strip_markup(snippet)
            tags = ", ".join(t.name for t in item["tags"]) if item["tags"] else "-"

            title_text = Text(item["title"])
            if snippet_plain:
                snippet_text = Text("\n")
                snippet_text.append(snippet_plain, style="dim")
                combined = Text.assemble(title_text, snippet_text)
            else:
                combined = title_text

            table.add_row(
                str(item["id"]),
                combined,
                tags,
                item["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)
        console.print(f"[dim]共找到 {total} 条结果，显示第 {skip + 1}-{min(skip + limit, total)} 条[/dim]")
    except Exception as e:
        console.print(f"[red]✗ 搜索失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@tag.command("list", help="列出所有标签（含书签数量）")
@click.option("--skip", default=0, type=int, help="跳过的条目数")
@click.option("--limit", "-n", default=50, type=int, help="显示的条目数")
def list_tags(skip: int, limit: int):
    _init_db()
    db = SessionLocal()
    try:
        tags = crud.get_tags_with_count(db, skip=skip, limit=limit)
        if not tags:
            console.print("[yellow]ℹ 暂无标签[/yellow]")
            return

        table = Table(
            title="🏷️  标签列表",
            box=box.ROUNDED,
            header_style="bold magenta",
            show_lines=False,
        )
        table.add_column("ID", style="dim", width=6, justify="right")
        table.add_column("标签名", style="bold cyan")
        table.add_column("颜色", style="yellow")
        table.add_column("书签数", style="green", justify="right")
        table.add_column("创建时间", style="dim", width=19)

        for t in tags:
            table.add_row(
                str(t["id"]),
                t["name"],
                t.get("color") or "-",
                str(t["bookmark_count"]),
                t["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]✗ 查询失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@tag.command("add", help="创建新标签")
@click.argument("name")
@click.option("--color", "-c", default=None, help="标签颜色（如 #FF5733）")
def add_tag(name: str, color: Optional[str]):
    _init_db()
    db = SessionLocal()
    try:
        existing = crud.get_tag_by_name(db, name)
        if existing is not None:
            console.print(f"[yellow]ℹ 标签 '{name}' 已存在[/yellow]")
            raise SystemExit(1)

        tag_in = schemas.TagCreate(name=name, color=color)
        tag = crud.create_tag(db, tag_in)
        console.print(f"[green]✓ 标签 '{tag.name}' 创建成功！[/green] ID: [bold]{tag.id}[/bold]")
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]✗ 创建失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@tag.command("update", help="更新标签信息")
@click.argument("tag_id", type=int)
@click.option("--name", "-n", default=None, help="新标签名称")
@click.option("--color", "-c", default=None, help="新标签颜色")
def update_tag(tag_id: int, name: Optional[str], color: Optional[str]):
    _init_db()
    db = SessionLocal()
    try:
        tag = crud.get_tag(db, tag_id)
        if tag is None:
            console.print(f"[red]✗ 标签 ID={tag_id} 不存在[/red]")
            raise SystemExit(1)

        if name is None and color is None:
            console.print("[yellow]ℹ 未提供任何更新字段[/yellow]")
            raise SystemExit(1)

        if name and name != tag.name:
            existing = crud.get_tag_by_name(db, name)
            if existing is not None:
                console.print(f"[red]✗ 标签名称 '{name}' 已存在[/red]")
                raise SystemExit(1)

        tag_in = schemas.TagUpdate(name=name, color=color)
        updated = crud.update_tag(db, tag, tag_in)
        console.print(f"[green]✓ 标签更新成功！[/green] {updated.name}")
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]✗ 更新失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


@tag.command("delete", help="删除标签")
@click.argument("tag_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接删除")
def delete_tag(tag_id: int, yes: bool):
    _init_db()
    db = SessionLocal()
    try:
        tag = crud.get_tag(db, tag_id)
        if tag is None:
            console.print(f"[red]✗ 标签 ID={tag_id} 不存在[/red]")
            raise SystemExit(1)

        if not yes:
            console.print(f"[yellow]即将删除标签:[/yellow] {tag.name}")
            if not click.confirm("确定要删除吗？（书签不会被删除）"):
                console.print("[dim]已取消删除[/dim]")
                raise SystemExit(0)

        success = crud.delete_tag(db, tag_id)
        if success:
            console.print(f"[green]✓ 标签 '{tag.name}' 已删除[/green]")
        else:
            console.print("[red]✗ 删除失败[/red]")
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]✗ 删除失败:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    cli()
