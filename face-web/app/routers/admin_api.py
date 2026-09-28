"""管理 API：人员 CRUD、Excel 导入、人脸上传、日志查询。无鉴权。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import MATCH_THRESHOLD, UPLOAD_DIR
from app.db import get_db
from app.face_engine import FaceEngineError
from app.gallery_index import gallery_index
from app.import_excel import enroll_face_bytes, import_people_from_xlsx
from app.models import FaceSample, Person, RecognitionLog, utcnow

router = APIRouter(prefix="/api", tags=["admin"])


class PersonCreate(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    city: str = ""
    college: str = ""
    education: str = ""
    enroll_year: str = ""
    ticket_type: str = ""
    signup_status: str = ""
    photo_url: str = ""


class PersonUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    college: str | None = None
    education: str | None = None
    enroll_year: str | None = None
    ticket_type: str | None = None
    signup_status: str | None = None
    photo_url: str | None = None
    status: str | None = None  # active | disabled


def _person_dict(person: Person) -> dict:
    return {
        "id": person.id,
        "phone": person.phone,
        "name": person.name,
        "city": person.city,
        "college": person.college,
        "education": person.education,
        "enroll_year": person.enroll_year,
        "ticket_type": person.ticket_type,
        "signup_status": person.signup_status,
        "photo_url": person.photo_url,
        "face_status": person.face_status,
        "face_message": person.face_message,
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


FACE_STATUS_LABEL = {
    "ok": "人脸正常",
    "missing": "无照片",
    "failed": "人脸不合格",
    "none": "未录入",
}


@router.get("/people")
def list_people(
    q: str = "",
    status: str = "",
    face_status: str = "",
    db: Session = Depends(get_db),
) -> dict:
    """人员列表，支持姓名/手机模糊搜索。"""
    stmt = select(Person).options(selectinload(Person.samples)).order_by(Person.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Person.name.like(like)) | (Person.phone.like(like)))
    if status in ("active", "disabled"):
        stmt = stmt.where(Person.status == status)
    if face_status in ("ok", "missing", "failed", "none"):
        stmt = stmt.where(Person.face_status == face_status)
    people = db.scalars(stmt).all()
    items = []
    for p in people:
        d = _person_dict(p)
        d["face_status_label"] = FACE_STATUS_LABEL.get(p.face_status, p.face_status)
        items.append(d)
    return {"items": items}


@router.post("/people")
def create_person(body: PersonCreate, db: Session = Depends(get_db)) -> dict:
    phone = body.phone.strip().replace(" ", "")
    exists = db.scalar(select(Person).where(Person.phone == phone))
    if exists:
        raise HTTPException(status_code=400, detail="手机号已存在")
    photo_url = (body.photo_url or "").strip()
    person = Person(
        phone=phone,
        name=body.name.strip(),
        city=(body.city or "").strip(),
        college=(body.college or "").strip(),
        education=(body.education or "").strip(),
        enroll_year=(body.enroll_year or "").strip(),
        ticket_type=(body.ticket_type or "").strip(),
        signup_status=(body.signup_status or "").strip(),
        photo_url=photo_url,
        face_status="missing" if not photo_url else "none",
        face_message="无身份识别照片" if not photo_url else "",
        status="active",
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    person.samples = []
    return _person_dict(person)


@router.post("/people/import")
def import_people(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    """上传互动吧导出的 .xlsx，按手机号 upsert，并尝试下载身份识别照片录脸。

    使用同步 def，由 FastAPI 放入线程池，避免长时间录脸阻塞事件循环导致全站不可访问。
    须声明在 /people/{person_id} 之前，避免 path 参数把 import 当成 id。
    """
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx，请用 Excel 另存为 xlsx 后再导入")
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    try:
        result = import_people_from_xlsx(raw, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"解析失败: {exc}") from exc
    return {
        "created": result.created,
        "updated": result.updated,
        "face_ok": result.face_ok,
        "face_failed": result.face_failed,
        "skipped": result.skipped,
    }


@router.get("/people/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    data = _person_dict(person)
    data["face_status_label"] = FACE_STATUS_LABEL.get(person.face_status, person.face_status)
    data["samples"] = [_sample_dict(s) for s in sorted(person.samples, key=lambda x: x.id)]
    return data


@router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonUpdate, db: Session = Depends(get_db)) -> dict:
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    for field in (
        "name",
        "city",
        "college",
        "education",
        "enroll_year",
        "ticket_type",
        "signup_status",
        "photo_url",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(person, field, val.strip())
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="status 只能是 active 或 disabled")
        person.status = body.status
        gallery_index.set_person_active(person.id, person.status == "active", db)
    person.updated_at = utcnow()
    db.commit()
    db.refresh(person)
    return _person_dict(person)


@router.delete("/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)) -> dict:
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
    """本地上传人脸；成功后 face_status=ok。"""
    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")

    try:
        enroll_face_bytes(person, raw, db)
        person.updated_at = utcnow()
        db.commit()
    except FaceEngineError as exc:
        person.face_status = "failed"
        person.face_message = exc.message[:500]
        db.commit()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    db.refresh(person)
    samples = db.scalars(
        select(FaceSample).where(FaceSample.person_id == person.id).order_by(FaceSample.id.desc())
    ).all()
    return _sample_dict(samples[0]) if samples else {"ok": True}


@router.delete("/faces/{sample_id}")
def delete_face(sample_id: int, db: Session = Depends(get_db)) -> dict:
    sample = db.get(FaceSample, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="样本不存在")
    person_id = sample.person_id
    rel = sample.image_path
    gallery_index.remove_sample(sample.id)
    db.delete(sample)
    db.commit()
    path = UPLOAD_DIR / rel
    if path.is_file():
        path.unlink(missing_ok=True)

    person = db.scalar(
        select(Person).options(selectinload(Person.samples)).where(Person.id == person_id)
    )
    if person and not any(s.enabled for s in person.samples):
        if person.photo_url:
            person.face_status = "failed"
            person.face_message = "已无启用人脸样本"
        else:
            person.face_status = "missing"
            person.face_message = "无身份识别照片"
        db.commit()
    return {"ok": True}


@router.get("/logs")
def list_logs(
    matched: str = "",
    phone: str = "",
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(RecognitionLog).order_by(RecognitionLog.id.desc()).limit(limit)
    if matched == "true":
        stmt = stmt.where(RecognitionLog.matched.is_(True))
    elif matched == "false":
        stmt = stmt.where(RecognitionLog.matched.is_(False))
    if phone:
        stmt = stmt.where(RecognitionLog.phone == phone)
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "device_label": r.device_label,
                "matched": r.matched,
                "phone": r.phone,
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
    face_failed = (
        db.scalar(select(func.count()).select_from(Person).where(Person.face_status == "failed")) or 0
    )
    face_missing = (
        db.scalar(select(func.count()).select_from(Person).where(Person.face_status == "missing")) or 0
    )
    return {
        "person_count": person_count,
        "sample_count": sample_count,
        "index_size": gallery_index.size,
        "match_threshold": MATCH_THRESHOLD,
        "face_failed": face_failed,
        "face_missing": face_missing,
    }
