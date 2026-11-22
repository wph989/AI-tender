"""端口实现层：可替换、可 mock 的具体技术。

MinerU / Gotenberg / S3 / Postgres / LLM 都落在这里，第三方错误码也在这一层翻译成
domain/errors.py 的领域错误——上层不该知道 413 和 400 的区别（docs/工程/10-技术选型与工程结构.md）。
"""
