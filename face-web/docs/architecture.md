# 架构说明

## 组件

- **浏览器管理页**（`/admin*`）：录入人员与人脸、停用/删除、查日志。
- **平板识别页**（`/recognize`）：摄像头抓拍，POST 图片到服务端。
- **FastAPI**：业务 API + 页面渲染；无鉴权。
- **InsightFace buffalo_l**：检测 + ArcFace 512 维特征（ONNX Runtime CPU）。
- **内存索引**（`gallery_index`）：`N×512` 矩阵，精确点积 1:N。
- **SQLite**：人员、样本、日志的权威存储；原图在 `data/uploads/`。

## 录入流程

1. 管理页创建 `person`。
2. 上传图片 → `FaceEngine.extract_for_enroll`：
   - 必须恰好一张脸；
   - 检测置信度、脸大小、亮度门槛；
   - 与索引中**其他人**比对，过高则判录重。
3. 原图写入 `data/uploads/persons/{id}/`，向量写入 `face_sample.embedding`。
4. `gallery_index.upsert_sample` 热更新内存矩阵。

## 识别流程

1. 平板抓拍 JPEG → `POST /api/recognize`。
2. `extract_for_recognize`：无人脸报错；多脸取面积最大。
3. `gallery_index.search`：矩阵点积 → 按人取最高分 → 与 `MATCH_THRESHOLD` 比较。
4. 写 `recognition_log`，返回姓名或未识别。

## 为何点积等于余弦

`normed_embedding` 已 L2 归一化，故 `cos(a,b) = a·b`。分数不是概率，界面不要显示成百分比。

## 规模

5000 人 × 约 5 张样本 ≈ 2.5 万行 × 512 float32，内存约几十 MB；全量精确检索在 CPU 上通常远小于一次推理耗时。
