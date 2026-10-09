# face-web 人脸识别 Web 系统

FastAPI + 原生 HTML/JS。管理后台录人脸，平板浏览器拍照，服务端 InsightFace `buffalo_l` 做 1:N 比对。目标库容约 1000–5000 人。

**管理端需要登录**，密码为环境变量 `FACE_WEB_ADMIN_PWD`。未设置时无法登录。平板识别页 `/recognize`、正式展示页 `/recognize/stage`、识别接口，以及摄像头指引 `/guide/camera` 不需要登录。

预训练模型 `buffalo_l` 仅限非商业研究用途，详见 InsightFace 模型许可。

## 快速启动

启动前设置管理密码。Windows：

```text
cd face-web
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:FACE_WEB_ADMIN_PWD = "你的密码"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ubuntu：

```text
cd face-web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FACE_WEB_ADMIN_PWD=你的密码
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开：

| 路径 | 说明 |
|---|---|
| http://127.0.0.1:8000/ | 首页 |
| http://127.0.0.1:8000/admin | 人员管理 |
| http://127.0.0.1:8000/admin/logs | 识别日志 |
| http://127.0.0.1:8000/recognize | 平板识别页 |
| http://127.0.0.1:8000/recognize/stage | 正式识别展示页（无按钮，URL 控制间隔与镜头） |
| http://127.0.0.1:8000/guide/camera | 摄像头开通指引（安卓可打开） |

首次启动会加载 `buffalo_l`（约 326MB，已下载则直接用 `%USERPROFILE%\.insightface\models\buffalo_l\`）。

## 人员与 Excel 导入

人员以**手机号**为唯一键，字段含姓名、所在城市、学院、学历、入学年份、票种、报名状态、身份识别照片 URL 等。

在 `/admin` 可点击「导入 Excel」，上传互动吧导出的 **`.xlsx`**（不支持 `.xls`，请另存为 xlsx）。导入时会：

- 按手机号新建或更新；
- 下载「身份识别照片」URL 并自动录脸；
- 无照片或人脸不合格仍建档，列表用标签标出「无照片 / 人脸不合格」。

**数据库不做迁移**：本版字段变更后请删除 `data/app.db` 再启动（旧试验数据不保留）。

在 `/admin` 可「全量导出」下载 zip（`app.db` 快照 + `uploads` 照片），并在另一台用「全量导入」整库覆盖。导入会替换当前人员和照片。

## 摄像头与 HTTPS

浏览器 `getUserMedia` 需要安全上下文：`https://` 或 `http://localhost`。

安卓平板用局域网 IP 的 HTTP **通常打不开摄像头**。正式环境请用 Nginx 反代 HTTPS；开发时可在电脑 localhost 调试。

### Chrome 临时放开（仅试验）

内网用 `http://192.168.x.x:8000` 这类非安全源时，可用 Chrome 临时把该地址当作安全源。

**安卓平板可直接打开页面指引**（把 IP 换成你的服务器）：

```text
http://192.168.1.100:8000/guide/camera
```

页面会显示当前源地址并支持一键复制，按步骤操作即可。摘要如下：

1. 地址栏打开：`chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. 将 **Insecure origins treated as secure** 设为 **Enabled**
3. 在文本框填入完整源地址，例如：`http://192.168.1.100:8000`（可多个，逗号分隔）
4. 右下角 **Relaunch** 重启浏览器后再打开 `/recognize`

此为临时调试手段，升级 Chrome 或清 flags 后可能失效；不要当作生产方案。

识别页抓拍配置见 [docs/recognize-page.md](docs/recognize-page.md)。

## 默认阈值

余弦相似度阈值默认 `0.40`（`app/config.py` 的 `MATCH_THRESHOLD`）。上线前用真实照片标定。

## 更多文档

- [docs/architecture.md](docs/architecture.md) — 架构与流程
- [docs/data-model.md](docs/data-model.md) — 数据表字段
- [docs/recognize-page.md](docs/recognize-page.md) — 识别页参数

## 目录

- `app/` — FastAPI 应用、人脸引擎、内存索引
- `templates/` / `static/` — 管理页与识别页
- `data/` — SQLite 与上传原图（默认 gitignore）
