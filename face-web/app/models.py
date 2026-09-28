"""ORM 数据模型：人员、人脸样本、识别日志。字段含义见 docs/data-model.md。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    """身份档案：一人可对应多张人脸样本。"""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 工号/学号，业务唯一键
    employee_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    department: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # active=参与比对；disabled=保留数据但不进内存索引
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    samples: Mapped[list[FaceSample]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class FaceSample(Base):
    """单张录入人脸：磁盘原图 + 512 维特征。"""

    __tablename__ = "face_sample"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # 相对 face-web/data/uploads 的路径，例如 persons/12/abc.jpg
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # ArcFace 512 维 L2 归一化向量的 float32 原始字节（512*4）
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # 综合质量分（例如检测置信度），便于日后筛选
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 检测框 [x1,y1,x2,y2]，JSON 文本存储
    bbox_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # False 时不参与 1:N，可保留坏图记录而不删人
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    person: Mapped[Person] = relationship(back_populates="samples")


class RecognitionLog(Base):
    """一次识别请求的结果摘要，供后台排查。"""

    __tablename__ = "recognition_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # 平板页可选备注，非鉴权字段
    device_label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True)
    employee_no: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    person_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    second_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # no_face / multi_face / below_threshold / ok 等
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    query_image_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
