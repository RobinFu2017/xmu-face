"""应用配置：路径、识别阈值与录脸质量门槛。

阈值含义见 docs/architecture.md；改阈值后无需重建库，但建议用真实样本重新标定。
"""

from __future__ import annotations

from pathlib import Path

# face-web 根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

# ArcFace 余弦相似度阈值（已 L2 归一化向量的点积）。演示默认 0.40，上线前务必用本单位照片标定。
MATCH_THRESHOLD = 0.40

# 每人最多保留的启用样本数；过多收益有限，还会拉长比对与存储。
MAX_SAMPLES_PER_PERSON = 5

# 录脸质量：bbox 短边像素过小则拒绝（脸太远/太糊）。
MIN_FACE_SHORT_SIDE = 80

# 检测置信度过低则拒绝。
MIN_DET_SCORE = 0.5

# 人脸区域平均亮度（0–255）过暗则拒绝。
MIN_FACE_BRIGHTNESS = 40.0

# 录入正立判定：两眼连线倾角绝对值超过此度数视为横躺/倾斜，触发试转。
MAX_EYE_TILT_DEG = 45.0

# 查询图可选落盘目录（识别日志排查用）
QUERY_DIR = DATA_DIR / "queries"
