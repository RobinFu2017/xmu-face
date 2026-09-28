"""识别 API：接收平板上传的 JPEG，做 1:N 比对并写日志。无鉴权。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import MATCH_THRESHOLD, QUERY_DIR
from app.db import get_db
from app.face_engine import FaceEngineError, face_engine
from app.gallery_index import gallery_index
from app.models import RecognitionLog

router = APIRouter(prefix="/api", tags=["recognize"])


@router.post("/recognize")
async def recognize(
    image: UploadFile = File(...),
    device_label: str = Form(""),
    save_query: str = Form("0"),
    db: Session = Depends(get_db),
) -> dict:
    """1:N 识别。

    返回 matched / person / score / threshold / second_score / error_code。
    error_code: 空字符串表示流程正常（可能 below_threshold）；另有 no_face 等。
    """
    raw = await image.read()
    label = (device_label or "").strip()[:128]
    query_rel = ""

    if save_query in ("1", "true", "yes"):
        QUERY_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        name = f"{day}_{uuid.uuid4().hex}.jpg"
        path = QUERY_DIR / name
        path.write_bytes(raw)
        query_rel = f"queries/{name}"

    try:
        bgr = face_engine.decode_image(raw)
        feature = face_engine.extract_for_recognize(bgr)
    except FaceEngineError as exc:
        log = RecognitionLog(
            device_label=label,
            matched=False,
            score=0.0,
            second_score=0.0,
            threshold=MATCH_THRESHOLD,
            error_code=exc.code,
            query_image_path=query_rel,
        )
        db.add(log)
        db.commit()
        return {
            "matched": False,
            "person": None,
            "score": 0.0,
            "second_score": 0.0,
            "threshold": MATCH_THRESHOLD,
            "error_code": exc.code,
            "message": exc.message,
        }

    hit, second = gallery_index.search(feature.embedding, threshold=MATCH_THRESHOLD)
    if hit is None:
        # 未达阈值：把最高分写进 score 便于调参（search 在未命中时 second 可能是 top 或第二名）
        # 重新取原始 top 分数用于日志：再搜一次阈值极低
        soft_hit, soft_second = gallery_index.search(feature.embedding, threshold=-1.0)
        top_score = soft_hit.score if soft_hit else 0.0
        second_score = soft_second if soft_hit else 0.0
        log = RecognitionLog(
            device_label=label,
            matched=False,
            person_id=None,
            employee_no="",
            person_name="",
            score=top_score,
            second_score=second_score,
            threshold=MATCH_THRESHOLD,
            error_code="below_threshold",
            query_image_path=query_rel,
        )
        db.add(log)
        db.commit()
        return {
            "matched": False,
            "person": None,
            "score": top_score,
            "second_score": second_score,
            "threshold": MATCH_THRESHOLD,
            "error_code": "below_threshold",
            "message": "未匹配到人员",
        }

    log = RecognitionLog(
        device_label=label,
        matched=True,
        person_id=hit.person_id,
        employee_no=hit.employee_no,
        person_name=hit.name,
        score=hit.score,
        second_score=second,
        threshold=MATCH_THRESHOLD,
        error_code="",
        query_image_path=query_rel,
    )
    db.add(log)
    db.commit()
    return {
        "matched": True,
        "person": {"id": hit.person_id, "employee_no": hit.employee_no, "name": hit.name},
        "score": hit.score,
        "second_score": second,
        "threshold": MATCH_THRESHOLD,
        "error_code": "",
        "message": "ok",
    }
