from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class Tag(TagBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TagWithCount(Tag):
    bookmark_count: int = 0


class BookmarkBase(BaseModel):
    url: str = Field(..., max_length=2048)
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v:
            raise ValueError("URL不能为空")
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("ftp://") or v.startswith("file://")):
            raise ValueError("URL必须以 http://、https://、ftp:// 或 file:// 开头")
        return v


class BookmarkCreate(BookmarkBase):
    tags: Optional[List[str]] = []


class BookmarkUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=2048)
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not (v.startswith("http://") or v.startswith("https://") or v.startswith("ftp://") or v.startswith("file://")):
                raise ValueError("URL必须以 http://、https://、ftp:// 或 file:// 开头")
        return v


class Bookmark(BookmarkBase):
    id: int
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []

    model_config = {"from_attributes": True}


class BookmarkListResponse(BaseModel):
    total: int
    items: List[Bookmark]


class SearchResult(Bookmark):
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    total: int
    items: List[SearchResult]
