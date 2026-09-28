"""内存人脸索引：精确 1:N 余弦相似度检索。

SQLite 是权威存储；本矩阵是可随时从库重建的投影。
一人多张样本时，该人得分取其所有样本的最高相似度。
向量已 L2 归一化，故 scores = matrix @ query 即为余弦相似度。
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MATCH_THRESHOLD
from app.face_engine import bytes_to_embedding
from app.models import FaceSample, Person


@dataclass
class SearchHit:
    """按人聚合后的命中结果。"""

    person_id: int
    phone: str
    name: str
    score: float


class GalleryIndex:
    """进程内精确索引：N×512 矩阵 + 行元数据。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._matrix = np.zeros((0, 512), dtype=np.float32)
        self._sample_ids: list[int] = []
        self._person_ids: list[int] = []
        self._phones: list[str] = []
        self._names: list[str] = []

    @property
    def size(self) -> int:
        return len(self._sample_ids)

    def load_from_db(self, db: Session) -> None:
        """启动时全量加载：仅 active 人员 + enabled 样本。"""
        rows = db.execute(
            select(FaceSample, Person)
            .join(Person, FaceSample.person_id == Person.id)
            .where(Person.status == "active", FaceSample.enabled.is_(True))
        ).all()

        embeddings: list[np.ndarray] = []
        sample_ids: list[int] = []
        person_ids: list[int] = []
        phones: list[str] = []
        names: list[str] = []

        for sample, person in rows:
            embeddings.append(bytes_to_embedding(sample.embedding))
            sample_ids.append(sample.id)
            person_ids.append(person.id)
            phones.append(person.phone)
            names.append(person.name)

        with self._lock:
            if embeddings:
                self._matrix = np.stack(embeddings, axis=0).astype(np.float32)
            else:
                self._matrix = np.zeros((0, 512), dtype=np.float32)
            self._sample_ids = sample_ids
            self._person_ids = person_ids
            self._phones = phones
            self._names = names

    def upsert_sample(
        self,
        *,
        sample_id: int,
        person_id: int,
        phone: str,
        name: str,
        embedding: np.ndarray,
        person_active: bool,
        sample_enabled: bool,
    ) -> None:
        """新增或替换一行；人员停用或样本关闭则从索引移除。"""
        with self._lock:
            self._remove_sample_unlocked(sample_id)
            if not person_active or not sample_enabled:
                return
            vec = np.asarray(embedding, dtype=np.float32).reshape(1, 512)
            if self._matrix.shape[0] == 0:
                self._matrix = vec
            else:
                self._matrix = np.vstack([self._matrix, vec])
            self._sample_ids.append(sample_id)
            self._person_ids.append(person_id)
            self._phones.append(phone)
            self._names.append(name)

    def remove_sample(self, sample_id: int) -> None:
        with self._lock:
            self._remove_sample_unlocked(sample_id)

    def remove_person(self, person_id: int) -> None:
        with self._lock:
            keep = [i for i, pid in enumerate(self._person_ids) if pid != person_id]
            self._rebuild_from_indices(keep)

    def set_person_active(self, person_id: int, active: bool, db: Session) -> None:
        """停用：从索引剔除；启用：把该人启用样本重新载入。"""
        if not active:
            self.remove_person(person_id)
            return
        rows = db.execute(
            select(FaceSample, Person)
            .join(Person, FaceSample.person_id == Person.id)
            .where(
                Person.id == person_id,
                Person.status == "active",
                FaceSample.enabled.is_(True),
            )
        ).all()
        for sample, person in rows:
            self.upsert_sample(
                sample_id=sample.id,
                person_id=person.id,
                phone=person.phone,
                name=person.name,
                embedding=bytes_to_embedding(sample.embedding),
                person_active=True,
                sample_enabled=True,
            )

    def search(
        self,
        query: np.ndarray,
        *,
        threshold: float | None = None,
        exclude_person_id: int | None = None,
    ) -> tuple[SearchHit | None, float]:
        """1:N 搜索。返回 (最佳命中或 None, 第二名分数)。"""
        thr = MATCH_THRESHOLD if threshold is None else threshold
        q = np.asarray(query, dtype=np.float32).reshape(512)

        with self._lock:
            if self._matrix.shape[0] == 0:
                return None, 0.0
            scores = self._matrix @ q

            best_by_person: dict[int, tuple[float, int]] = {}
            for i, score in enumerate(scores.tolist()):
                pid = self._person_ids[i]
                if exclude_person_id is not None and pid == exclude_person_id:
                    continue
                prev = best_by_person.get(pid)
                if prev is None or score > prev[0]:
                    best_by_person[pid] = (score, i)

            if not best_by_person:
                return None, 0.0

            ranked = sorted(best_by_person.items(), key=lambda kv: kv[1][0], reverse=True)
            top_pid, (top_score, top_idx) = ranked[0]
            second = ranked[1][1][0] if len(ranked) > 1 else 0.0

            if top_score < thr:
                return None, second if len(ranked) > 1 else top_score

            hit = SearchHit(
                person_id=top_pid,
                phone=self._phones[top_idx],
                name=self._names[top_idx],
                score=float(top_score),
            )
            return hit, float(second)

    def _remove_sample_unlocked(self, sample_id: int) -> None:
        if sample_id not in self._sample_ids:
            return
        idx = self._sample_ids.index(sample_id)
        keep = [i for i in range(len(self._sample_ids)) if i != idx]
        self._rebuild_from_indices(keep)

    def _rebuild_from_indices(self, keep: list[int]) -> None:
        if not keep:
            self._matrix = np.zeros((0, 512), dtype=np.float32)
            self._sample_ids = []
            self._person_ids = []
            self._phones = []
            self._names = []
            return
        self._matrix = self._matrix[keep]
        self._sample_ids = [self._sample_ids[i] for i in keep]
        self._person_ids = [self._person_ids[i] for i in keep]
        self._phones = [self._phones[i] for i in keep]
        self._names = [self._names[i] for i in keep]


gallery_index = GalleryIndex()
