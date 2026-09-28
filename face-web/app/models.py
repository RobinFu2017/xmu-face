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
    """身份档案：一人可对应多张人脸样本。业务唯一键为手机号。"""

    __tablename__ = "person"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 手机号，业务唯一键
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    # 姓名
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 所在城市
    city: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 学院
    college: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 学历
    education: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # 入学年份（字符串，兼容空/非纯数字）
    enroll_year: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # 票种
    ticket_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 报名状态（导入表「服务状态」）
    signup_status: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # 身份识别照片原始 URL
    photo_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    # 人脸状态：ok=正常 / missing=无照片 / failed=录脸失败 / none=未处理
    face_status: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    # 人脸失败原因摘要（如未检测到人脸）
    face_message: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # 启用状态：active=可参与比对；disabled=保留数据但不进内存索引
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    # 创建时间（UTC）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # 最后更新时间（UTC）
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # 关联的人脸样本列表
    samples: Mapped[list[FaceSample]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class FaceSample(Base):
    """单张录入人脸：磁盘原图 + 512 维特征。"""

    __tablename__ = "face_sample"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属人员 ID
    person_id: Mapped[int] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # 原图路径（相对 data/uploads/）
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # ArcFace 512 维 float32 特征原始字节（L2 归一化）
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # 质量分（检测置信度等）
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 检测框 JSON，如 [x1,y1,x2,y2]
    bbox_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # 是否参与 1:N 比对索引
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 录入时间（UTC）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # 所属人员
    person: Mapped[Person] = relationship(back_populates="samples")


class RecognitionLog(Base):
    """一次识别请求的结果摘要，供后台排查。"""

    __tablename__ = "recognition_log"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 识别时间（UTC）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # 平板/设备备注
    device_label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 是否命中人员
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 命中人员 ID（未命中或人员已删可为 NULL）
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id", ondelete="SET NULL"), nullable=True)
    # 命中人员手机号（冗余快照）
    phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # 命中人员姓名（冗余快照）
    person_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # 最高相似度分数
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 次高相似度分数
    second_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 当时使用的判定阈值
    threshold: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # 错误码（如 no_face、low_score 等；成功为空）
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # 查询图保存路径（可选）
    query_image_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
