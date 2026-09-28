# buffalo_l 特征与比对 Demo

用 InsightFace 的 `buffalo_l`（ArcFace，512 维）经 ONNX Runtime 从人脸照片抽出特征向量，并与 `gallery/` 里的预制照片做余弦相似度比对。

Python 调用 InsightFace 2.0 的 `FaceAnalysis(name="buffalo_l")`，库内部用 ONNX Runtime 加载检测模型 `det_10g.onnx` 和识别模型 `w600k_r50.onnx`（ArcFace，512 维）。强制 `CPUExecutionProvider`，不依赖 GPU。

预训练模型仅限非商业研究用途。本目录按本地试验使用。

## 环境

- Python 3.10+
- CPU 即可，不依赖 GPU

## 运行方式

在 `face-demo/` 里执行：

```text
cd face-demo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python match_face.py path\to\query.jpg
```

首次运行会把约 326MB 的 `buffalo_l` 下载到 `%USERPROFILE%\.insightface\models\buffalo_l\`。自动下载失败时，从 [model-zoo release](https://github.com/deepinsight/insightface/releases/tag/model-zoo) 获取 `buffalo_l.zip`，手动解压到该目录后再跑（目录内应有 `det_10g.onnx`、`w600k_r50.onnx` 等文件）。

`face-demo/gallery/` 里放若干张人脸照片（文件名当作身份名，例如 `zhangsan.jpg`）。脚本对查询图和每张预制图各提一次特征，用已归一化向量的点积作为余弦相似度，按分数从高到低打印，并标出是否达到演示阈值 `0.40`。

无人脸、多张脸时取面积最大的一张并打印提示。查询向量完整打印，同时写到 `face-demo/output/<查询文件名>.json`（512 个浮点数、检测框、与各预制脸的分数）。

另加 `python match_face.py --self-test`：用 InsightFace 自带样例图只检查能否得到形状 `(512,)` 的向量，方便在还没放 gallery 照片时确认环境。

## 放入预制人脸

把几张单人正脸照片放到 `gallery/`，文件名当作身份名，例如：

```text
gallery/zhangsan.jpg
gallery/lisi.png
```

## 命令

自检（不需要 gallery，确认能输出 512 维向量）：

```text
python match_face.py --self-test
```

比对查询图：

```text
python match_face.py path\to\query.jpg
```

演示阈值默认为 `0.40`，可用 `--threshold 0.45` 修改。

## 示例输出

```text
[self-test] embedding shape=(512,) dtype=float32
[self-test] OK

query: query.jpg
embedding dim: 512
bbox: [102.3, 88.1, 310.5, 340.2]

matches (threshold=0.40):
  zhangsan.jpg    0.672  MATCH
  lisi.png        0.213
```

## 文件说明

- `requirements.txt`：`insightface`、`onnxruntime`、`opencv-python`、`numpy`
- `match_face.py`：加载模型时 `allowed_modules=["detection", "recognition"]`，跳过性别年龄和 106 点关键点；`prepare(ctx_id=-1)` 固定 CPU
- `gallery/`：预制人脸照片（不提交真实人脸）
- `output/`：查询向量与比对结果 JSON（已加入 `.gitignore`）
- `.gitignore`：忽略虚拟环境、`output/` 和缓存

比对逻辑只有向量点积，不引入数据库或向量检索库。
