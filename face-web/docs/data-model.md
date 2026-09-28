# 数据模型

数据库文件：`data/app.db`（SQLite）。

## person

| 字段 | 说明 |
|---|---|
| id | 主键 |
| employee_no | 工号/学号，唯一 |
| name | 姓名 |
| department | 部门 |
| status | `active` 参与比对；`disabled` 保留数据但不进内存索引 |
| created_at / updated_at | UTC 时间 |

## face_sample

一张录入人脸。

| 字段 | 说明 |
|---|---|
| id | 主键 |
| person_id | 所属人员 |
| image_path | 相对 `data/uploads/` 的路径，如 `persons/12/xxx.jpg` |
| embedding | ArcFace 512 维 float32 原始字节（2048 bytes），L2 归一化 |
| quality_score | 质量分（当前用检测置信度） |
| bbox_json | 检测框 `[x1,y1,x2,y2]` 的 JSON |
| enabled | 是否参与 1:N；关样本可不删人 |
| created_at | 录入时间 |

每人启用样本上限见配置 `MAX_SAMPLES_PER_PERSON`（默认 5）。

## recognition_log

| 字段 | 说明 |
|---|---|
| id | 主键 |
| created_at | 识别时间 |
| device_label | 平板页可选备注（非鉴权） |
| matched | 是否命中 |
| person_id / employee_no / person_name | 命中人员（未命中可为空） |
| score | 最高分（命中或未达阈值时的 top1） |
| second_score | 第二名分数，便于发现混淆 |
| threshold | 当时使用的阈值 |
| error_code | `no_face` / `multi_face` / `below_threshold` / 空 |
| query_image_path | 可选查询图相对路径 |
