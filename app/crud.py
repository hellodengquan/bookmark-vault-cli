from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy import select, func, delete, text
from sqlalchemy.orm import Session, selectinload

from app.models import Bookmark, Tag, bookmark_tag
from app import schemas


def _get_or_create_tags(db: Session, tag_names: List[str]) -> List[Tag]:
    tags: List[Tag] = []
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        tag = db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    return tags


def create_bookmark(db: Session, bookmark_in: schemas.BookmarkCreate) -> Bookmark:
    tags = _get_or_create_tags(db, bookmark_in.tags or [])
    bookmark = Bookmark(
        url=bookmark_in.url,
        title=bookmark_in.title,
        description=bookmark_in.description,
        tags=tags,
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return bookmark


def get_bookmark(db: Session, bookmark_id: int) -> Optional[Bookmark]:
    stmt = (
        select(Bookmark)
        .options(selectinload(Bookmark.tags))
        .where(Bookmark.id == bookmark_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_bookmarks(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    tag: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
) -> Tuple[int, List[Bookmark]]:
    count_stmt = select(func.count(Bookmark.id))
    stmt = select(Bookmark).options(selectinload(Bookmark.tags))

    if tag:
        count_stmt = (
            count_stmt
            .join(bookmark_tag, Bookmark.id == bookmark_tag.c.bookmark_id)
            .join(Tag, Tag.id == bookmark_tag.c.tag_id)
            .where(Tag.name == tag)
        )
        stmt = (
            stmt
            .join(bookmark_tag, Bookmark.id == bookmark_tag.c.bookmark_id)
            .join(Tag, Tag.id == bookmark_tag.c.tag_id)
            .where(Tag.name == tag)
        )

    total = db.execute(count_stmt).scalar_one()

    sort_column = getattr(Bookmark, sort_by, Bookmark.created_at)
    if order == "asc":
        stmt = stmt.order_by(sort_column.asc())
    else:
        stmt = stmt.order_by(sort_column.desc())

    stmt = stmt.offset(skip).limit(limit)
    items = list(db.execute(stmt).scalars().all())
    return total, items


def update_bookmark(
    db: Session,
    bookmark: Bookmark,
    bookmark_in: schemas.BookmarkUpdate,
) -> Bookmark:
    update_data = bookmark_in.model_dump(exclude_unset=True)
    tags_data = update_data.pop("tags", None)

    for field, value in update_data.items():
        setattr(bookmark, field, value)

    if tags_data is not None:
        bookmark.tags = _get_or_create_tags(db, tags_data)

    bookmark.updated_at = datetime.utcnow()
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return bookmark


def delete_bookmark(db: Session, bookmark_id: int) -> bool:
    bookmark = get_bookmark(db, bookmark_id)
    if bookmark is None:
        return False
    db.delete(bookmark)
    db.commit()
    return True


def _has_chinese(text: str) -> bool:
    import re
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _build_fts_query(terms: List[str]) -> str:
    parts = []
    for term in terms:
        term = term.replace("'", "''").replace('"', '""')
        if _has_chinese(term):
            parts.append(f'"{term}"*')
        else:
            parts.append(f"{term}*")
    return " AND ".join(parts)


def _generate_snippet(text: Optional[str], query: str, max_len: int = 120) -> Optional[str]:
    if not text:
        return None
    import re
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return text[:max_len] + ("..." if len(text) > max_len else "")
    start = max(0, idx - 30)
    end = min(len(text), idx + len(query) + 60)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    highlighted = re.sub(
        f"({re.escape(query)})",
        r"<mark>\1</mark>",
        snippet,
        flags=re.IGNORECASE,
    )
    return highlighted


def search_bookmarks(
    db: Session,
    query: str,
    skip: int = 0,
    limit: int = 50,
    tag: Optional[str] = None,
) -> Tuple[int, List[dict]]:
    if not query or not query.strip():
        return 0, []

    raw_query = query.strip()

    import re
    terms = [t for t in re.split(r"\s+", raw_query) if t]
    fts_query_str = _build_fts_query(terms)

    params: dict = {"skip": skip, "limit": limit}

    join_clause_fts = ""
    join_clause_like = ""
    extra_where = ""
    if tag:
        join_clause_fts = (
            "JOIN bookmark_tag bt ON b.id = bt.bookmark_id "
            "JOIN tags t ON bt.tag_id = t.id "
        )
        join_clause_like = (
            "JOIN bookmark_tag bt ON b.id = bt.bookmark_id "
            "JOIN tags t ON bt.tag_id = t.id "
        )
        extra_where = " AND t.name = :tag_name"
        params["tag_name"] = tag

    total = 0
    rows = []
    used_like_fallback = False

    try:
        params_fts = dict(params)
        params_fts["fts_query"] = fts_query_str

        count_sql = text(
            f"""
            SELECT COUNT(*) FROM bookmarks_fts fts
            JOIN bookmarks b ON fts.rowid = b.id
            {join_clause_fts}
            WHERE bookmarks_fts MATCH :fts_query{extra_where}
            """
        )
        total = db.execute(count_sql, params_fts).scalar_one()

        if total > 0:
            search_sql = text(
                f"""
                SELECT
                    b.id,
                    b.url,
                    b.title,
                    b.description,
                    b.created_at,
                    b.updated_at,
                    snippet(bookmarks_fts, 1, '<mark>', '</mark>', '...', 20) AS snip
                FROM bookmarks_fts fts
                JOIN bookmarks b ON fts.rowid = b.id
                {join_clause_fts}
                WHERE bookmarks_fts MATCH :fts_query{extra_where}
                ORDER BY rank
                LIMIT :limit OFFSET :skip
                """
            )
            rows = db.execute(search_sql, params_fts).mappings().all()
    except Exception:
        total = 0
        rows = []

    if total == 0:
        used_like_fallback = True
        like_pattern = f"%{raw_query}%"
        params_like = dict(params)
        params_like["like_q"] = like_pattern

        count_sql = text(
            f"""
            SELECT COUNT(*) FROM bookmarks b
            {join_clause_like}
            WHERE (b.title LIKE :like_q OR b.description LIKE :like_q OR b.url LIKE :like_q){extra_where}
            """
        )
        total = db.execute(count_sql, params_like).scalar_one()

        if total > 0:
            search_sql = text(
                f"""
                SELECT
                    b.id,
                    b.url,
                    b.title,
                    b.description,
                    b.created_at,
                    b.updated_at
                FROM bookmarks b
                {join_clause_like}
                WHERE (b.title LIKE :like_q OR b.description LIKE :like_q OR b.url LIKE :like_q){extra_where}
                ORDER BY b.updated_at DESC
                LIMIT :limit OFFSET :skip
                """
            )
            rows = db.execute(search_sql, params_like).mappings().all()

    result_items: List[dict] = []
    for row in rows:
        bookmark_obj = db.execute(
            select(Bookmark).options(selectinload(Bookmark.tags)).where(Bookmark.id == row["id"])
        ).scalar_one()

        if used_like_fallback:
            title_snip = _generate_snippet(bookmark_obj.title, raw_query)
            desc_snip = _generate_snippet(bookmark_obj.description, raw_query)
            url_snip = _generate_snippet(bookmark_obj.url, raw_query)
            snippet = title_snip or desc_snip or url_snip
        else:
            snippet = row.get("snip")

        item = {
            "id": bookmark_obj.id,
            "url": bookmark_obj.url,
            "title": bookmark_obj.title,
            "description": bookmark_obj.description,
            "created_at": bookmark_obj.created_at,
            "updated_at": bookmark_obj.updated_at,
            "tags": bookmark_obj.tags,
            "snippet": snippet,
        }
        result_items.append(item)

    return total, result_items


def create_tag(db: Session, tag_in: schemas.TagCreate) -> Tag:
    tag = Tag(name=tag_in.name, color=tag_in.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def get_tag(db: Session, tag_id: int) -> Optional[Tag]:
    return db.execute(select(Tag).where(Tag.id == tag_id)).scalar_one_or_none()


def get_tag_by_name(db: Session, name: str) -> Optional[Tag]:
    return db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()


def get_tags(db: Session, skip: int = 0, limit: int = 100) -> List[Tag]:
    stmt = (
        select(Tag)
        .order_by(Tag.name.asc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def get_tags_with_count(db: Session, skip: int = 0, limit: int = 100) -> List[dict]:
    stmt = (
        select(
            Tag.id,
            Tag.name,
            Tag.color,
            Tag.created_at,
            func.count(bookmark_tag.c.bookmark_id).label("bookmark_count"),
        )
        .outerjoin(bookmark_tag, Tag.id == bookmark_tag.c.tag_id)
        .group_by(Tag.id, Tag.name, Tag.color, Tag.created_at)
        .order_by(func.count(bookmark_tag.c.bookmark_id).desc(), Tag.name.asc())
        .offset(skip)
        .limit(limit)
    )
    rows = db.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def update_tag(db: Session, tag: Tag, tag_in: schemas.TagUpdate) -> Tag:
    update_data = tag_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int) -> bool:
    tag = get_tag(db, tag_id)
    if tag is None:
        return False
    db.delete(tag)
    db.commit()
    return True
