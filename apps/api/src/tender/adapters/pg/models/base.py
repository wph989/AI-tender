"""声明式基类与模型通用约定。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """全部表映射模型的基类。

    约定（与 docs/工程/10 第 4.2 节「三个容易走样的地方」配套）：

    - 这些类只是「表 ↔ 对象」映射，不是领域模型；业务语义在 domain/ 与 application/。
    - 不复制默认值、索引、约束、外键行级行为：这些的权威是设计文档 + 迁移 DDL，
      在模型里再写一份等于制造第二事实源，两边都能自洽地漂移，反而没有测试抓得住。
      写入时未赋值的列不进 INSERT，由数据库默认值补齐。
    - 不声明 relationship()：仓储层写显式 join，避免隐式 IO 与 N+1。

    一致性的最后一道闸是 tests/contract/test_orm_models_match_ddl.py：
    表名、列名、可空性、列类型必须与全部迁移执行后的库完全一致。
    """
