# 项目协作规则

- 开始任何任务前，必须使用 UTF-8 读取项目根目录的 HANDOOFF.md（如果存在），并结合其中的交接信息继续工作。
- 修改后端前，阅读 [后端文件树与放置规则](docs/工程/21-后端文件树与放置规则.md)。`service`、`crud`、`agent` 是职责定义：业务与 Agent 编排归入 `application/`，数据库操作归入 `adapters/pg/repositories/`，接口归入 `ports/`；禁止再创建并列的同义目录。
- 用例通过构造参数接收端口，具体实现统一在 `core/di.py` 装配；不得为迁就错误目录而放宽分层检查。
- Worker 的数据库访问与锁也通过端口和 `core/di.py` 接入，SQL/事务放在既有 PostgreSQL 业务仓储中，不直接导入 ORM 或配置持久化实现。后端统一离线验证入口为 `scripts/check-backend.ps1`，包含协议与真实装配的 mypy 检查；不得用 `follow_imports = "skip"` 绕过实现兼容检查。
- 各业务层按已确定的业务模块组织：`projects`、`documents`、`knowledge`、`analysis`、`llm`、`configuration`、`jobs`。即使当前只有一个文件也归入对应业务目录；不为未出现的业务创建空目录。通用代码放 `shared/`，`core/`、配置基础设施、数据库连接与 ORM 表定义按技术职责组织，不机械套业务层级。
