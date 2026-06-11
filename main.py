from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_database, get_configured_db_path
from app.config import load_config
from app.routers import bookmarks, tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import _current_db_path
    if _current_db_path is not None:
        db_path = _current_db_path
    else:
        cfg = load_config()
        db_path = cfg.db_path
    init_database(db_path)
    app.state.db_path = db_path
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


@app.get("/api/config", tags=["config"])
async def get_config_info():
    cfg = load_config()
    return {
        "db_path": cfg.db_path,
        "config_source": cfg.config_source,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
