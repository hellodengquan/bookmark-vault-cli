from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud, schemas

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


@router.post("", response_model=schemas.Bookmark, status_code=status.HTTP_201_CREATED)
def create_bookmark(bookmark_in: schemas.BookmarkCreate, db: Session = Depends(get_db)):
    bookmark = crud.create_bookmark(db, bookmark_in)
    return bookmark


@router.get("", response_model=schemas.BookmarkListResponse)
def list_bookmarks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    tag: Optional[str] = Query(None, description="按标签名称过滤"),
    sort_by: str = Query("created_at", description="排序字段: created_at, updated_at, title"),
    order: str = Query("desc", description="排序方式: asc, desc"),
    db: Session = Depends(get_db),
):
    if sort_by not in ("created_at", "updated_at", "title"):
        sort_by = "created_at"
    if order not in ("asc", "desc"):
        order = "desc"
    total, items = crud.get_bookmarks(db, skip=skip, limit=limit, tag=tag, sort_by=sort_by, order=order)
    return {"total": total, "items": items}


@router.get("/search", response_model=schemas.SearchResponse)
def search_bookmarks(
    q: str = Query(..., description="搜索关键词"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    tag: Optional[str] = Query(None, description="按标签名称过滤"),
    db: Session = Depends(get_db),
):
    total, items = crud.search_bookmarks(db, query=q, skip=skip, limit=limit, tag=tag)
    return {"total": total, "items": items}


@router.get("/{bookmark_id}", response_model=schemas.Bookmark)
def get_bookmark(bookmark_id: int, db: Session = Depends(get_db)):
    bookmark = crud.get_bookmark(db, bookmark_id)
    if bookmark is None:
        raise HTTPException(status_code=404, detail="书签未找到")
    return bookmark


@router.put("/{bookmark_id}", response_model=schemas.Bookmark)
def update_bookmark(
    bookmark_id: int,
    bookmark_in: schemas.BookmarkUpdate,
    db: Session = Depends(get_db),
):
    bookmark = crud.get_bookmark(db, bookmark_id)
    if bookmark is None:
        raise HTTPException(status_code=404, detail="书签未找到")
    updated = crud.update_bookmark(db, bookmark, bookmark_in)
    return updated


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark(bookmark_id: int, db: Session = Depends(get_db)):
    success = crud.delete_bookmark(db, bookmark_id)
    if not success:
        raise HTTPException(status_code=404, detail="书签未找到")
    return None
