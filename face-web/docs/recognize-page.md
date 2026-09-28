# 识别页配置

路径：`/recognize`

## 抓拍模式

| 参数 | 取值 | 说明 |
|---|---|---|
| `capture_mode` | `manual` / `auto` | 人工点按钮，或按间隔自动抓拍 |
| `capture_interval_ms` | 整数毫秒 | 自动间隔，默认 `1500`，最小 `500` |

示例：

```text
/recognize?capture_mode=auto&capture_interval_ms=2000
```

优先级：URL 查询参数 → `localStorage` → 默认值。页面上修改后会写入 `localStorage`。

## 行为约束

- 上一次 `POST /api/recognize` 未返回前，自动模式不会再发请求。
- 页面隐藏（切后台）时暂停定时器，回到前台再恢复。
- 离开页面清除定时器。

## 摄像头

- 需要 HTTPS 或 localhost；局域网 HTTP 默认无法调用摄像头。
- 优先请求后置摄像头（`facingMode: environment`），失败则回退默认设备。
- 建议安卓系统 Chrome；部分 App 内置 WebView 可能禁摄像头。

### Chrome 临时放开非安全源（仅试验）

平板用 `http://局域网IP:端口` 访问时，可临时：

1. 打开 `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. **Insecure origins treated as secure** → **Enabled**
3. 填入源地址，例如 `http://192.168.1.100:8000`
4. **Relaunch** 后重试 `/recognize`

正式环境仍应使用 HTTPS，不要依赖该 flag。

## 设备备注

页面「设备备注」随识别请求以 `device_label` 写入日志，便于区分多台平板，**不是**访问令牌。
