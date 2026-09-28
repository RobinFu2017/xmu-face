"""SQLAlchemy 引擎与会话工厂。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DB_PATH


class Base(DeclarativeBase):
    """ORM 基类。"""


def _sqlite_url() -> str:
    return f"sqlite:///{DB_PATH.as_posix()}"


# check_same_thread=False：FastAPI 多请求线程共用同一引擎时 SQLite 需要此选项。
engine = create_engine(
    _sqlite_url(),
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
    """打开外键约束，保证删除人员时级联删样本。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求结束时关闭会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建表结构（若不存在）。"""
    from app import models  # noqa: F401

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
