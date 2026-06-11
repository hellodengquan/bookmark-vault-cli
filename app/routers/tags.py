from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud, schemas

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.post("", response_model=schemas.Tag, status_code=status.HTTP_201_CREATED)
def create_tag(tag_in: schemas.TagCreate, db: Session = Depends(get_db)):
    existing = crud.get_tag_by_name(db, tag_in.name)
    if existing is not None:
        raise HTTPException(status_code=400, detail="标签名称已存在")
    tag = crud.create_tag(db, tag_in)
    return tag


@router.get("", response_model=List[schemas.TagWithCount])
def list_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    tags = crud.get_tags_with_count(db, skip=skip, limit=limit)
    return tags


@router.get("/{tag_id}", response_model=schemas.Tag)
def get_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = crud.get_tag(db, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签未找到")
    return tag


@router.put("/{tag_id}", response_model=schemas.Tag)
def update_tag(
    tag_id: int,
    tag_in: schemas.TagUpdate,
    db: Session = Depends(get_db),
):
    tag = crud.get_tag(db, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="标签未找到")
    if tag_in.name and tag_in.name != tag.name:
        existing = crud.get_tag_by_name(db, tag_in.name)
        if existing is not None:
            raise HTTPException(status_code=400, detail="标签名称已存在")
    updated = crud.update_tag(db, tag, tag_in)
    return updated


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    success = crud.delete_tag(db, tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="标签未找到")
    return None
