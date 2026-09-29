"""全量备份：导出/导入 app.db 快照与 data/uploads 照片。"""

from __future__ import annotations

import gc
import io
import os
import sqlite3
import tempfile
import threading
import zipfile
from pathlib import Path
from shutil import copy2, copytree, rmtree

from sqlalchemy import func, select

from app.config import DATA_DIR, DB_PATH, UPLOAD_DIR
from app.db import SessionLocal, engine
from app.gallery_index import gallery_index
from app.models import FaceSample, Person

_lock = threading.Lock()
_PARKED_DB = DATA_DIR / "_restore_app.db"
_PARKED_UPLOADS = DATA_DIR / "_restore_uploads"


def build_export_zip() -> Path:
    """打出含 app.db 快照与 uploads/ 的 zip，返回临时文件路径。"""
    with _lock:
        if not DB_PATH.exists():
            raise ValueError("数据库不存在")
        fd, name = tempfile.mkstemp(suffix=".zip", prefix="face-backup-")
        os.close(fd)
        path = Path(name)
        try:
            _write_zip(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        print(f"[backup] export {path.name}")
        return path


def import_bundle(data: bytes) -> dict:
    """用 zip 覆盖当前库与 uploads，并重建内存索引。失败则尽量恢复。"""
    if not data:
        raise ValueError("空文件")
    with _lock:
        with tempfile.TemporaryDirectory(prefix="face-import-") as tmp:
            root = Path(tmp)
            db_src, uploads_src = _extract_bundle(data, root)
            _validate_db(db_src)
            try:
                _swap_in(db_src, uploads_src)
                result = _reload_index()
            except Exception:
                print("[backup] import failed, restoring previous data")
                _rollback()
                raise
            _clear_path(_PARKED_DB)
            _clear_path(_PARKED_UPLOADS)
            print(
                f"[backup] import ok people={result['person_count']} samples={result['sample_count']}"
            )
            return result


def _write_zip(dest: Path) -> None:
    snap = dest.with_suffix(".snap.db")
    try:
        _snapshot_db(snap)
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(snap, "app.db")
            if UPLOAD_DIR.exists():
                for file in UPLOAD_DIR.rglob("*"):
                    if file.is_file():
                        rel = Path("uploads") / file.relative_to(UPLOAD_DIR)
                        zf.write(file, rel.as_posix())
    finally:
        snap.unlink(missing_ok=True)


def _snapshot_db(dest: Path) -> None:
    """在线备份，得到不含 wal 的一致库文件。"""
    src = sqlite3.connect(DB_PATH.as_posix())
    try:
        dst = sqlite3.connect(dest.as_posix())
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _extract_bundle(data: bytes, root: Path) -> tuple[Path, Path | None]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("不是有效的 zip 文件") from exc

    db_src: Path | None = None
    uploads_root = root / "uploads"
    with zf:
        for info in zf.infolist():
            rel = _safe_arcname(info.filename)
            if rel is None:
                continue
            if rel.as_posix() == "app.db":
                db_src = root / "app.db"
                db_src.write_bytes(zf.read(info))
                continue
            if rel.parts and rel.parts[0] == "uploads" and not info.is_dir():
                target = root.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
    if db_src is None or not db_src.exists():
        raise ValueError("压缩包中缺少 app.db")
    uploads_src = uploads_root if uploads_root.exists() else None
    return db_src, uploads_src


def _safe_arcname(name: str) -> Path | None:
    """只接受 app.db 与 uploads/ 下的相对路径。"""
    cleaned = name.replace("\\", "/").strip()
    if not cleaned or cleaned.endswith("/"):
        return None
    cleaned = cleaned.lstrip("/")
    parts = tuple(p for p in cleaned.split("/") if p not in ("", "."))
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"非法路径: {name}")
    rel = Path(*parts)
    posix = rel.as_posix()
    if posix == "app.db":
        return rel
    if parts[0] == "uploads":
        return rel
    return None


def _validate_db(path: Path) -> None:
    conn = sqlite3.connect(path.as_posix())
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"数据库无法读取: {exc}") from exc
    finally:
        conn.close()
    names = {row[0] for row in rows}
    missing = {"person", "face_sample"} - names
    if missing:
        raise ValueError("不是本系统的数据库（缺少人员或人脸表）")


def _checkpoint_and_dispose() -> None:
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH.as_posix())
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    engine.dispose()
    gc.collect()


def _swap_in(db_src: Path, uploads_src: Path | None) -> None:
    _clear_path(_PARKED_DB)
    _clear_path(_PARKED_UPLOADS)
    _checkpoint_and_dispose()
    if DB_PATH.exists():
        DB_PATH.rename(_PARKED_DB)
    for side in (Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm")):
        if side.exists():
            side.unlink()
    copy2(db_src, DB_PATH)
    if UPLOAD_DIR.exists():
        UPLOAD_DIR.rename(_PARKED_UPLOADS)
    if uploads_src is not None and uploads_src.exists():
        copytree(uploads_src, UPLOAD_DIR)
    else:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _rollback() -> None:
    engine.dispose()
    gc.collect()
    if _PARKED_DB.exists():
        if DB_PATH.exists():
            DB_PATH.unlink()
        _PARKED_DB.rename(DB_PATH)
    if _PARKED_UPLOADS.exists():
        if UPLOAD_DIR.exists():
            rmtree(UPLOAD_DIR)
        _PARKED_UPLOADS.rename(UPLOAD_DIR)
    elif not UPLOAD_DIR.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _reload_index()
    except Exception as exc:  # noqa: BLE001
        print(f"[backup] restore index failed: {exc}")


def _reload_index() -> dict:
    with SessionLocal() as db:
        gallery_index.load_from_db(db)
        person_count = int(db.scalar(select(func.count()).select_from(Person)) or 0)
        sample_count = int(db.scalar(select(func.count()).select_from(FaceSample)) or 0)
    return {
        "person_count": person_count,
        "sample_count": sample_count,
        "index_size": gallery_index.size,
    }


def _clear_path(path: Path) -> None:
    if path.is_dir():
        rmtree(path)
    elif path.exists():
        path.unlink()
