"""人脸引擎：buffalo_l 检测/提特征、录脸质量校验。

向量已 L2 归一化时，点积等于余弦相似度；不要把分数当成概率百分比展示。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import (
    MATCH_THRESHOLD,
    MIN_DET_SCORE,
    MIN_FACE_BRIGHTNESS,
    MIN_FACE_SHORT_SIDE,
)


class FaceEngineError(Exception):
    """可映射到 API 错误码的业务异常。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FaceFeature:
    """单张可用人脸的特征与元数据。"""

    embedding: np.ndarray  # shape (512,) float32，L2 归一化
    bbox: list[float]  # [x1, y1, x2, y2]
    det_score: float
    quality_score: float
    brightness: float


class FaceEngine:
    """封装 InsightFace FaceAnalysis，进程内单例使用。"""

    def __init__(self) -> None:
        self._app = None

    def load(self) -> None:
        """加载 buffalo_l（CPU / ONNX Runtime）。首次可能下载约 326MB 模型。"""
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        # ctx_id=-1 强制 CPU，与 face-demo 一致
        app.prepare(ctx_id=-1, det_size=(640, 640))
        self._app = app

    @property
    def ready(self) -> bool:
        return self._app is not None

    def decode_image(self, data: bytes) -> np.ndarray:
        """把上传字节解码为 BGR 图。"""
        arr = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise FaceEngineError("bad_image", "无法解码图片")
        return image

    def extract_for_enroll(self, image: np.ndarray) -> FaceFeature:
        """录入用：必须恰好一张脸，并通过质量门槛。"""
        faces = self._detect(image)
        if not faces:
            raise FaceEngineError("no_face", "未检测到人脸")
        if len(faces) > 1:
            # 录入拒绝多脸，避免录错人；识别侧可改为取最大脸
            raise FaceEngineError("multi_face", f"检测到 {len(faces)} 张脸，请保证单人入镜")
        return self._to_feature(image, faces[0], require_quality=True)

    def extract_for_recognize(self, image: np.ndarray) -> FaceFeature:
        """识别用：无人脸报错；多张脸取面积最大的一张。"""
        faces = self._detect(image)
        if not faces:
            raise FaceEngineError("no_face", "未检测到人脸")
        face = max(
            faces,
            key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])),
        )
        return self._to_feature(image, face, require_quality=False)

    def _detect(self, image: np.ndarray) -> list:
        if self._app is None:
            raise RuntimeError("FaceEngine 尚未 load()")
        return list(self._app.get(image))

    def _to_feature(self, image: np.ndarray, face, *, require_quality: bool) -> FaceFeature:
        embedding = np.asarray(face.normed_embedding, dtype=np.float32)
        if embedding.shape != (512,):
            raise FaceEngineError("bad_embedding", f"特征维度异常: {embedding.shape}")

        bbox = [float(x) for x in face.bbox.tolist()]
        det_score = float(getattr(face, "det_score", 0.0) or 0.0)
        short_side = min(bbox[2] - bbox[0], bbox[3] - bbox[1])
        brightness = self._face_brightness(image, bbox)
        # 质量分用检测置信度即可满足演示；后续可加权短边/亮度
        quality_score = det_score

        if require_quality:
            if det_score < MIN_DET_SCORE:
                raise FaceEngineError("low_confidence", f"检测置信度过低: {det_score:.3f}")
            if short_side < MIN_FACE_SHORT_SIDE:
                raise FaceEngineError("face_too_small", f"人脸过小（短边 {short_side:.0f}px）")
            if brightness < MIN_FACE_BRIGHTNESS:
                raise FaceEngineError("too_dark", f"人脸区域过暗（亮度 {brightness:.1f}）")

        return FaceFeature(
            embedding=embedding,
            bbox=bbox,
            det_score=det_score,
            quality_score=quality_score,
            brightness=brightness,
        )

    @staticmethod
    def _face_brightness(image: np.ndarray, bbox: list[float]) -> float:
        """人脸框内灰度均值，用于拒绝过暗录入图。"""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        crop = image[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    return np.asarray(embedding, dtype=np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).copy()


def bbox_to_json(bbox: list[float]) -> str:
    return json.dumps(bbox)


def json_to_bbox(text: str) -> list[float]:
    return [float(x) for x in json.loads(text or "[]")]


# 模块级单例，由 main lifespan 加载
face_engine = FaceEngine()
