"""业务库持久化适配层（docs/工程/10 第 4.2 节目的目录约定 adapters/pg）。

- session.py：引擎与会话工厂，全项目唯一的引擎构造入口；
- models/：SQLAlchemy 2.0 typed declarative 表映射（≠ 领域模型）；
- repositories/：下一步放 ports 仓储接口的实现，application 只依赖 Protocol。
"""
