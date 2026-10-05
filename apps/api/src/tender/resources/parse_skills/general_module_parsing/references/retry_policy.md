# 重试策略

> TODO: 从 v1 的 RetryConfig 迁移。

## 参数（参考）
- `max_retries`：最大重试次数。
- `initial_delay` / `max_delay`：退避起止延迟（秒）。
- `exponential_base`：指数底数。
- `jitter`：是否加抖动。

## 规则
- 仅对可重试异常（超时/限流/网络）重试；业务错误不重试。
- 遇限流 `[1302]`：延时 5 秒后重试，最多 3 次；仍失败则停止并上报。
