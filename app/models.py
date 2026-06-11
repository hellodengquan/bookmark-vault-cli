from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Table, ForeignKey, Index, event, DDL
from sqlalchemy.orm import relationship

from app.database import Base

bookmark_tag = Table(
    "bookmark_tag",
    Base.metadata,
    Column("bookmark_id", Integer, ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
)


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    tags = relationship("Tag", secondary=bookmark_tag, back_populates="bookmarks")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    color = Column(String(7), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookmarks = relationship("Bookmark", secondary=bookmark_tag, back_populates="tags")


create_fts_bookmarks_ddl = DDL(
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks_fts USING fts5(
        title,
        description,
        url,
        content='bookmarks',
        content_rowid='id',
        tokenize='unicode61'
    )
    """
)

create_fts_trigger_after_insert = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS bookmarks_ai AFTER INSERT ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(rowid, title, description, url)
        VALUES (new.id, new.title, new.description, new.url);
    END;
    """
)

create_fts_trigger_after_delete = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS bookmarks_ad AFTER DELETE ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, description, url)
        VALUES ('delete', old.id, old.title, old.description, old.url);
    END;
    """
)

create_fts_trigger_after_update = DDL(
    """
    CREATE TRIGGER IF NOT EXISTS bookmarks_au AFTER UPDATE ON bookmarks BEGIN
        INSERT INTO bookmarks_fts(bookmarks_fts, rowid, title, description, url)
        VALUES ('delete', old.id, old.title, old.description, old.url);
        INSERT INTO bookmarks_fts(rowid, title, description, url)
        VALUES (new.id, new.title, new.description, new.url);
    END;
    """
)

event.listen(Base.metadata, "after_create", create_fts_bookmarks_ddl)
event.listen(Base.metadata, "after_create", create_fts_trigger_after_insert)
event.listen(Base.metadata, "after_create", create_fts_trigger_after_delete)
event.listen(Base.metadata, "after_create", create_fts_trigger_after_update)
