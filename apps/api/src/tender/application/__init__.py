"""用例编排层：只依赖 domain 与 ports。

这一层写业务动作（上传、解析、检索与分析），不写 SQL、不发 HTTP。
依赖方向被 import-linter 强制：一旦在这里 import 了 adapters，CI 立刻变红。
"""
