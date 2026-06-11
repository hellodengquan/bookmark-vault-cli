from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import bookmarks, tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Bookmark Vault API",
    description="基于 FastAPI + SQLite 的本地书签管理工具，支持标签分类和离线全文搜索",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bookmarks.router)
app.include_router(tags.router)


@app.get("/", tags=["root"])
async def root():
    return {
        "name": "Bookmark Vault API",
        "version": "1.0.0",
        "docs": "/docs",
        "description": "本地书签管理工具，支持标签分类和离线全文搜索",
    }


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
