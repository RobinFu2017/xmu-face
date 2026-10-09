# 识别页配置

路径：`/recognize`（调试页，含按钮与下拉）以及 `/recognize/stage`（正式展示页，无按钮）。

## 抓拍与摄像头参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `capture_mode` | `manual` / `auto` | 人工点按钮，或按间隔自动抓拍 |
| `capture_interval_ms` | 整数毫秒 | 自动间隔，默认 `1500`，最小 `500` |
| `facing` | `environment` / `user` | 后置 / 前置，默认 `environment` |

示例：

```text
/recognize?capture_mode=auto&capture_interval_ms=2000&facing=user
```

优先级：URL 查询参数 → `localStorage` → 默认值。页面上修改后会写入 `localStorage`。

页面「摄像头」下拉可随时切换前后摄；若摄像头已打开，切换后会停掉旧流并按新朝向重新打开。单摄或不支持 `facingMode` 时回退默认摄像头并提示。

## 行为约束

- 上一次 `POST /api/recognize` 未返回前，自动模式不会再发请求。
- 页面隐藏（切后台）时暂停定时器，回到前台再恢复。
- 离开页面清除定时器。

## 摄像头

- 需要 HTTPS 或 localhost；局域网 HTTP 默认无法调用摄像头。
- 默认请求后置（`facingMode: environment`），可在页面或 URL 切到前置（`user`）；失败则回退默认设备。
- 建议安卓系统 Chrome；部分 App 内置 WebView 可能禁摄像头。

### Chrome 临时放开非安全源（仅试验）

平板用 `http://局域网IP:端口` 访问时，可在平板 Chrome 打开指引页（把 IP/端口换成实际值）：

```text
http://192.168.1.100:8000/guide/camera
```

页面会自动显示当前源并支持复制。步骤摘要：

1. 打开 `chrome://flags/#unsafely-treat-insecure-origin-as-secure`（须在地址栏手动输入）
2. **Insecure origins treated as secure** → **Enabled**
3. 填入源地址，例如 `http://192.168.1.100:8000`
4. **Relaunch** 后重试 `/recognize`

正式环境仍应使用 HTTPS，不要依赖该 flag。

## 设备备注

页面「设备备注」随识别请求以 `device_label` 写入日志，便于区分多台平板，**不是**访问令牌。

## 正式展示页 `/recognize/stage`

全屏切图界面，进页自动开摄像头并按间隔识别。**没有按钮**，配置只读 URL，不读写 `localStorage`。

| 参数 | 取值 | 说明 |
|---|---|---|
| `capture_interval_ms` | 整数毫秒 | 自动间隔，默认 `1500`，最小 `500` |
| `facing` | `environment` / `user` | 后置 / 前置，默认 `environment` |
| `device_label` | 字符串 | 写入识别日志，页面不展示 |

示例：

```text
/recognize/stage?capture_interval_ms=2000&facing=user
```

- 前置预览镜像，上传 JPEG 仍用原始画面。
- 上一次 `POST /api/recognize` 未返回前不会再发请求。
- 页面隐藏时暂停定时器。
- 识别成功时在人脸框右下角弹出气泡（姓名、打码手机、学院、入学年份），约 3 秒无新命中后收起。
- 摄像头打不开时只显示一行提示。
