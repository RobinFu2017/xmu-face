"""FastAPI 入口：启动时建库、加载 buffalo_l、重建内存人脸索引。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import auth_middleware
from app.config import DATA_DIR, QUERY_DIR, ROOT_DIR, UPLOAD_DIR
from app.db import SessionLocal, init_db
from app.face_engine import face_engine
from app.gallery_index import gallery_index
from app.routers import admin_api, pages, recognize_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    print("loading buffalo_l (CPU / ONNX Runtime)...")
    face_engine.load()
    with SessionLocal() as db:
        gallery_index.load_from_db(db)
    print(f"gallery index loaded: {gallery_index.size} samples")
    yield


app = FastAPI(title="face-web", lifespan=lifespan)

# 静态目录在 import 时就要存在，StaticFiles 会校验路径
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
QUERY_DIR.mkdir(parents=True, exist_ok=True)

app.include_router(pages.router)
app.include_router(admin_api.router)
app.include_router(recognize_api.router)

static_dir = ROOT_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 原图通过 /media 访问（对应 data/uploads）
app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")

# 包住页面、API 与 /media；识别页与 POST /api/recognize 在中间件内放行
app.middleware("http")(auth_middleware)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
