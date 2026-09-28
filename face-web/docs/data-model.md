# 数据模型

数据库文件：`data/app.db`（SQLite）。**无自动迁移**：字段变更后请删除该文件重启服务以重建表。

## person

| 字段 | 说明 |
|---|---|
| id | 主键 |
| phone | 手机号，业务唯一键 |
| name | 姓名 |
| city | 所在城市 |
| college | 学院 |
| education | 学历 |
| enroll_year | 入学年份 |
| ticket_type | 票种 |
| signup_status | 报名状态（导入表「服务状态」） |
| photo_url | 身份识别照片原始 URL |
| face_status | `ok` / `missing` / `failed` / `none` |
| face_message | 人脸失败原因摘要 |
| status | `active` 参与比对；`disabled` 不进内存索引 |
| created_at / updated_at | UTC 时间 |

## face_sample

| 字段 | 说明 |
|---|---|
| id | 主键 |
| person_id | 所属人员 |
| image_path | 相对 `data/uploads/` 的路径 |
| embedding | ArcFace 512 维 float32 原始字节，L2 归一化 |
| quality_score | 质量分 |
| bbox_json | 检测框 JSON |
| enabled | 是否参与 1:N |
| created_at | 录入时间 |

## recognition_log

| 字段 | 说明 |
|---|---|
| id | 主键 |
| created_at | 识别时间 |
| device_label | 平板备注 |
| matched | 是否命中 |
| person_id / phone / person_name | 命中人员 |
| score / second_score / threshold | 分数 |
| error_code | 错误码 |
| query_image_path | 可选查询图路径 |
