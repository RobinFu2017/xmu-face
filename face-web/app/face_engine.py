"""人脸引擎：buffalo_l 检测/提特征、录脸质量校验。

向量已 L2 归一化时，点积等于余弦相似度；不要把分数当成概率百分比展示。

录入时用五官关键点判断是否正立；不正立或检不出脸时自动试转 90°/270°。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import atan2, degrees

import cv2
import numpy as np

from app.config import (
    MAX_EYE_TILT_DEG,
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

    def extract_for_enroll(self, image: np.ndarray) -> tuple[FaceFeature, np.ndarray]:
        """录入用：恰好一张正立脸，并通过质量门槛。

        原图多脸立即拒绝。无人脸或不正立/质量未过时，依次旋转 90°、270° 再检。
        返回 (特征, 实际用于提特征的 BGR 图)，调用方应保存后者以免缩略图仍是横图。
        """
        # 原图：多脸直接失败，不试转
        faces0 = self._detect(image)
        if len(faces0) > 1:
            raise FaceEngineError("multi_face", f"检测到 {len(faces0)} 张脸，请保证单人入镜")

        tried = self._try_enroll_on_image(image)
        if tried is not None:
            return tried

        # 无人脸 / 不正立 / 质量未过 → 试转（OpenCV：CLOCKWISE_90 = 顺时针 90°）
        for flag in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            rotated = cv2.rotate(image, flag)
            tried = self._try_enroll_on_image(rotated)
            if tried is not None:
                return tried

        raise FaceEngineError(
            "face_not_upright",
            "未得到正立人脸，请上传正向单人照（系统已尝试自动旋转）",
        )

    def extract_for_recognize(self, image: np.ndarray) -> FaceFeature:
        """识别用：无人脸报错；多张脸取面积最大的一张。不做朝向试转。"""
        faces = self._detect(image)
        if not faces:
            raise FaceEngineError("no_face", "未检测到人脸")
        face = max(
            faces,
            key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])),
        )
        return self._to_feature(image, face, require_quality=False)

    def _try_enroll_on_image(self, image: np.ndarray) -> tuple[FaceFeature, np.ndarray] | None:
        """对单张图尝试录入。多脸返回 None（由上层在原图已处理多脸）；失败返回 None。"""
        faces = self._detect(image)
        if not faces:
            return None
        if len(faces) > 1:
            # 旋转后万一出现多脸，跳过该朝向
            return None
        face = faces[0]
        if not self._is_face_upright(face):
            return None
        try:
            feature = self._to_feature(image, face, require_quality=True)
        except FaceEngineError:
            return None
        return feature, image

    @staticmethod
    def _is_face_upright(face) -> bool:
        """用五官关键点判断是否大致正立。

        kps: 左眼、右眼、鼻、左嘴角、右嘴角。
        - 两眼连线倾角过大 → 横躺；
        - 鼻子应在两眼中点下方（图像 y 向下增大）。
        """
        kps = getattr(face, "kps", None)
        if kps is None:
            return False
        pts = np.asarray(kps, dtype=np.float64)
        if pts.shape != (5, 2):
            return False

        left_eye, right_eye, nose = pts[0], pts[1], pts[2]
        dx = float(right_eye[0] - left_eye[0])
        dy = float(right_eye[1] - left_eye[1])
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return False

        tilt_deg = abs(degrees(atan2(dy, dx)))
        # atan2 得到 -180..180；横躺时接近 90
        if tilt_deg > 90:
            tilt_deg = 180 - tilt_deg
        if tilt_deg > MAX_EYE_TILT_DEG:
            return False

        eye_mid_y = (left_eye[1] + right_eye[1]) / 2.0
        if float(nose[1]) <= eye_mid_y:
            # 鼻子不在眼睛下方 → 可能倒立
            return False
        return True

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


def encode_image_jpeg(image: np.ndarray, quality: int = 90) -> bytes:
    """将 BGR 图编码为 JPEG 字节，用于保存转正后的录入图。"""
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise FaceEngineError("bad_image", "无法编码入库图片")
    return buf.tobytes()


# 模块级单例，由 main lifespan 加载
face_engine = FaceEngine()
