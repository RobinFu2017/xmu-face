"""管理 API：人员 CRUD、人脸上传、样本删除、识别日志查询。无鉴权，知道路径即可调用。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import MATCH_THRESHOLD, MAX_SAMPLES_PER_PERSON, UPLOAD_DIR
from app.db import get_db
from app.face_engine import (
    FaceEngineError,
    bbox_to_json,
    embedding_to_bytes,
    face_engine,
)
from app.gallery_index import gallery_index
from app.models import FaceSample, Person, RecognitionLog, utcnow

router = APIRouter(prefix="/api", tags=["admin"])


class PersonCreate(BaseModel):
    employee_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    department: str = ""


class PersonUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    status: str | None = None  # active | disabled


def _person_dict(person: Person) -> dict:
    return {
        "id": person.id,
        "employee_no": person.employee_no,
        "name": person.name,
        "department": person.department,
        "status": person.status,
        "sample_count": len([s for s in person.samples if s.enabled]),
        "created_at": person.created_at.isoformat() if person.created_at else None,
        "updated_at": person.updated_at.isoformat() if person.updated_at else None,
    }


def _sample_dict(sample: FaceSample) -> dict:
    return {
        "id": sample.id,
        "person_id": sample.person_id,
        "image_url": f"/media/{sample.image_path.replace(chr(92), '/')}",
        "quality_score": sample.quality_score,
        "bbox_json": sample.bbox_json,
        "enabled": sample.enabled,
        "created_at": sample.created_at.isoformat() if sample.created_at else None,
    }


@router.get("/people")
def list_people(
    q: str = "",
    status: str = "",
    db: Session = Depends(get_db),
) -> dict:
    """人员列表，支持姓名/工号模糊搜索与状态过滤。"""
    stmt = select(Person).options(selectinload(Person.samples)).order_by(Person.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Person.name.like(like)) | (Person.employee_no.like(like)))
    if status in ("active", "disabled"):
        stmt = stmt.where(Person.status == status)
    people = db.scalars(stmt).all()
    return {"items": [_person_dict(p) for p in people]}


@router.post("/people")
def create_person(body: PersonCreate, db: Session = Depends(get_db)) -> dict:
    exists = db.scalar(select(Person).where(Person.employee_no == body.employee_no.strip()))
    if exists:
        raise HTTPException(status_code=400, detail="工号已存在")
    person = Person(
        employee_no=body.employee_no.strip(),
        name=body.name.strip(),
        department=(body.department or "").strip(),
        status="active",
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    person.samples = []
    return _person_dict(person)


@router.get("/people/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    data = _person_dict(person)
    data["samples"] = [_sample_dict(s) for s in sorted(person.samples, key=lambda x: x.id)]
    return data


@router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonUpdate, db: Session = Depends(get_db)) -> dict:
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    if body.name is not None:
        person.name = body.name.strip()
    if body.department is not None:
        person.department = body.department.strip()
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="status 只能是 active 或 disabled")
        person.status = body.status
        # 同步内存索引：停用剔除，启用重新载入样本
        gallery_index.set_person_active(person.id, person.status == "active", db)
    person.updated_at = utcnow()
    db.commit()
    db.refresh(person)
    return _person_dict(person)


@router.delete("/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    """删除人员：级联删样本记录、磁盘原图，并更新内存索引。"""
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    paths = [s.image_path for s in person.samples]
    gallery_index.remove_person(person.id)
    db.delete(person)
    db.commit()
    for rel in paths:
        path = UPLOAD_DIR / rel
        if path.is_file():
            path.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/people/{person_id}/faces")
async def upload_face(
    person_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """上传一张人脸：质量校验 → 查重 → 落盘 → 写库 → 更新索引。"""
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")

    enabled_count = sum(1 for s in person.samples if s.enabled)
    if enabled_count >= MAX_SAMPLES_PER_PERSON:
        raise HTTPException(status_code=400, detail=f"每人最多 {MAX_SAMPLES_PER_PERSON} 张启用样本")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")

    try:
        image = face_engine.decode_image(raw)
        feature = face_engine.extract_for_enroll(image)
    except FaceEngineError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    # 与库中其他人比对，防止把 A 的脸录到 B 名下
    hit, _ = gallery_index.search(
        feature.embedding,
        threshold=MATCH_THRESHOLD,
        exclude_person_id=person.id,
    )
    if hit is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "duplicate_face",
                "message": f"疑似与已有人员重复: {hit.employee_no} {hit.name} (score={hit.score:.3f})",
            },
        )

    rel_dir = Path("persons") / str(person.id)
    dest_dir = UPLOAD_DIR / rel_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "face.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        suffix = ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    rel_path = (rel_dir / filename).as_posix()
    dest_path = UPLOAD_DIR / rel_path
    dest_path.write_bytes(raw)

    sample = FaceSample(
        person_id=person.id,
        image_path=rel_path,
        embedding=embedding_to_bytes(feature.embedding),
        quality_score=feature.quality_score,
        bbox_json=bbox_to_json(feature.bbox),
        enabled=True,
    )
    db.add(sample)
    person.updated_at = utcnow()
    db.commit()
    db.refresh(sample)

    gallery_index.upsert_sample(
        sample_id=sample.id,
        person_id=person.id,
        employee_no=person.employee_no,
        name=person.name,
        embedding=feature.embedding,
        person_active=person.status == "active",
        sample_enabled=True,
    )
    return _sample_dict(sample)


@router.delete("/faces/{sample_id}")
def delete_face(sample_id: int, db: Session = Depends(get_db)) -> dict:
    sample = db.get(FaceSample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="样本不存在")
    rel = sample.image_path
    gallery_index.remove_sample(sample.id)
    db.delete(sample)
    db.commit()
    path = UPLOAD_DIR / rel
    if path.is_file():
        path.unlink(missing_ok=True)
    return {"ok": True}


@router.get("/logs")
def list_logs(
    matched: str = "",
    employee_no: str = "",
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(RecognitionLog).order_by(RecognitionLog.id.desc()).limit(limit)
    if matched == "true":
        stmt = stmt.where(RecognitionLog.matched.is_(True))
    elif matched == "false":
        stmt = stmt.where(RecognitionLog.matched.is_(False))
    if employee_no:
        stmt = stmt.where(RecognitionLog.employee_no == employee_no)
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "device_label": r.device_label,
                "matched": r.matched,
                "employee_no": r.employee_no,
                "person_name": r.person_name,
                "score": r.score,
                "second_score": r.second_score,
                "threshold": r.threshold,
                "error_code": r.error_code,
            }
            for r in rows
        ]
    }


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    person_count = db.scalar(select(func.count()).select_from(Person)) or 0
    sample_count = db.scalar(select(func.count()).select_from(FaceSample)) or 0
    return {
        "person_count": person_count,
        "sample_count": sample_count,
        "index_size": gallery_index.size,
        "match_threshold": MATCH_THRESHOLD,
    }
