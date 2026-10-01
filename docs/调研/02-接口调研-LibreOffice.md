# 02 · 接口调研：LibreOffice（Gotenberg）

> 调研对象：LibreOffice 转换能力的**容器化 HTTP 封装方案**
> 推荐方案：**Gotenberg**（内置 LibreOffice 模块）
> 调研日期：2026-09-26
> 接入方式：容器 + `POST /forms/libreoffice/convert`

## 1. 为什么需要这一层

由 [01](01-接口调研-MinerU.md) 的结论推导而来：MinerU 对 Office 系列**只提供 `flash` 档且无页面几何**（整文档解析、无页码、reflow、文字块无法导出影像）。而本系统的溯源能力完全依赖"页 + 块 + bbox"这套几何。

因此必须在解析前增加一个**格式归一化阶段**，把所有非 PDF 输入转成 PDF。转换后：

- 所有文档进入 MinerU 的**四档全支持**通道，可用 `standard` 档。
- 获得一致的 `page_size` 与块级 bbox。
- 前端只需要一种渲染器（PDF.js），无需为 Office 单独开发预览。

## 2. 方案横向对比

| 方案 | 形态 | 接口 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **Gotenberg** | 官方 Docker 镜像 | **REST**：`POST /forms/libreoffice/convert`，multipart，返回 PDF 字节 | 无状态、HTTP 原生、覆盖 Office/Chromium/PDF 三类；附带 merge/rotate/watermark/PDF-A/metadata 等 PDF 引擎能力；有健康检查与 Prometheus 指标 | 冷启动首次请求较慢（需预热） | **采用** |
| unoserver | Python 包 + 社区镜像（libreofficedocker/libreoffice-unoserver） | 镜像直接给 **REST**：`POST /request`（multipart，`convert-to` 指定目标格式）；原包本身是 Socket 协议 | 常驻 LibreOffice 实例，单次转换快；镜像自带 HTTP 层，能直接当服务跑；超时与内存都是显式环境变量（实测见 `投标skill/LibreOffice安装.md`） | 只覆盖格式转换：没有 Gotenberg 的 PDF 引擎能力、健康检查与 Prometheus 指标；要并行只能多副本，而它发布固定宿主端口，`--scale` 大于 1 会因端口冲突起不来 | 备选 |
| JODConverter | Java 库 / 可容器化 | 需自行包一层 HTTP | 成熟稳定，UNO 连接池管理好 | 无官方 HTTP 服务，需自研封装与维护 | 备选 |
| Collabora Online / LibreOffice Online | 完整在线办公套件 | WOPI | 支持在线编辑 | 体量极大，为"编辑"设计，转换只是副作用 | 不采用 |
| kkFileView | Java 服务 | REST | 国内常见，内置多种格式预览 | 定位是**在线预览**而非精确转换接口；无法保证版式与页码稳定，且不能提供坐标 | 不采用 |
| 本机 `soffice` 命令行 | 进程调用 | 无 | 零依赖 | 无隔离、并发差、崩溃影响主进程、无法横向扩容 | 不采用 |

**选 Gotenberg 的核心理由**：HTTP 服务这两家都能提供（unoserver 靠社区镜像补），差别在 Gotenberg 是官方的无状态设计，把"容器 + HTTP + 无状态 + 可水平扩容"四件事一起满足了，还捎带 PDF 引擎能力与 Prometheus 指标，且不要求我们自研封装。转换是本系统的**关键路径前置步骤**，把它的可用性外包给成熟项目比自己维护 UNO 连接池划算。

## 3. Gotenberg 接口规范

### 3.1 转换路由

```
POST /forms/libreoffice/convert
Content-Type: multipart/form-data
```

**表单字段**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `files` | file[] | **是** | 待转换文件，可上传多个；**多个输入文件时响应为 ZIP 包**（注意！） |

**请求头**

| 头 | 说明 |
| --- | --- |
| `Gotenberg-Output-Filename` | 输出文件名（Gotenberg 自动追加扩展名），默认随机 UUID |
| `Gotenberg-Trace` | 自定义请求 ID，用于日志关联；**我们必须传自己的 `job_id`** |

**最小示例**

```bash
curl --request POST http://gotenberg:3000/forms/libreoffice/convert \
  --header 'Gotenberg-Output-Filename: tender' \
  --header 'Gotenberg-Trace: job_01HXYZ' \
  --form files=@/data/tender.docx \
  -o tender.pdf
```

### 3.2 常用转换参数

全部以 form 字段传递（字符串 `true`/`false`）：

| 字段 | 默认 | 我们的取值 | 理由 |
| --- | --- | --- | --- |
| `exportBookmarks` | `true` | `true` | 保留 Word 大纲 → 转成 PDF 书签，可用于章节树交叉校验 |
| `exportBookmarksToPdfDestination` | `false` | `true` | 导出为命名目标，便于前端按标题跳转 |
| `exportFormFields` | `true` | `false` | 关闭交互式表单控件，**转成静态内容**。避免控件框用 fallback 字体测量导致的裁切；同时避免 PDF.js 中出现可编辑控件 |
| `updateIndexes` | `true` | `true` | 更新目录页码。注意官方提示**可能导致链接丢失**，若出现链接缺失再关闭 |
| `exportNotes` | `false` | `false` | 标书不需要批注 |
| `exportHiddenSlides` | `false` | — | 仅 Impress |
| `metadata` | 无 | 可选 | JSON 字符串，写入 XMP 元数据（如 `RequestId`、`DocumentVersion`），**注意写入元数据通常会破坏 PDF/A 合规** |
| `nativePageRanges` | 全部 | 不使用 | 我们需要全量页 |
| `landscape`、`singlePageSheets` | — | Excel 附件时评估 | 工程量清单类 Excel 常需横向 + 单页表 |

> **注意**：转换路由可在**同一请求内**叠加 PDF 引擎能力（合并、旋转、水印、加密、PDF/A、扁平化、元数据写入）。这为我们后续"生成带水印的对外版本"提供了现成能力，无需自研。
> **实现**：`apps/api/src/tender/adapters/gotenberg.py`（含行为测试 `tests/unit/adapters/test_gotenberg.py`）。两处实现细节值得记一笔：
> ① **先取版本再转换**，`/version` 结果在进程内缓存——`converter_version` 是 `document_version` 的必填项，拿不到版本就没有可信的溯源记录，宁可让这次转换直接可重试失败；
> ② `Gotenberg-Output-Filename` 会被压成 ASCII（HTTP 头只认 ASCII 字节，中文文件名会直接抛 `UnicodeEncodeError`），原始文件名仍完整放在 multipart 里。

### 3.3 响应与重试语义（重要）

| 状态码 | 含义 | 是否重试 |
| --- | --- | --- |
| **200** | 返回 PDF（多文件时为 ZIP） | — |
| **400** | 表单字段非法，或 LibreOffice 明确拒绝该文档（如 `nativePageRanges` 格式错、密码错误、文档损坏不可读） | **不重试**，重试结果相同 |
| **500** | LibreOffice 失败但请求本身无法解释原因（**大文档内存压力常落在此处**） | **可重试**，建议指数退避 |
| **503** | 超过配置的最大处理时长 | 可重试，但需先评估是否调大超时 |

响应头包含 `Content-Disposition`、`Gotenberg-Trace`，**必须校验 `Gotenberg-Trace` 与请求一致**，防止串包。

### 3.3.1 调用方式与并发控制

Gotenberg 的转换路由是**同步 HTTP 请求**：请求保持到转换完成，响应体返回 PDF。我们的业务任务仍以异步任务方式运行；worker 在发起 HTTP 请求前获取 `convert.max_inflight` 分布式信号量，请求结束（无论成功或失败）后释放。

- 并发配置由页面动态修改，调度器每 5 秒重新读取；调低上限时停止派发新转换，已在途请求完成后自然降到新上限。
- 当前采用同步调用 + 信号量。webhook 异步模式放在后续阶段；当转换 P95 持续超过 2 分钟时再评估是否启用。
- 每个请求继续传入并核对 `Gotenberg-Trace`，以便把同步响应与系统任务关联。

### 3.4 运维路由

| 路由 | 用途 |
| --- | --- |
| `GET /health` | 健康检查（含依赖模块状态） |
| `GET /version` | 版本信息，**必须记录进 `document_version.converter_version`** |
| `GET /debug` | 运行时配置导出，排障用 |
| Prometheus 指标 | 接入监控：转换耗时、失败率、队列深度 |

## 4. 保真度与字体（最大风险点）

> 官方原文提示：**"LibreOffice 依赖已安装字体来计算分页与版面。缺失字体是版面问题与页码漂移最常见的原因。"**

这一点直接决定溯源质量：**字体缺失 → 分页漂移 → 我们的 page/bbox 与用户看到的原件不一致 → 溯源失效**。

**必须做**：

1. 基于官方镜像构建**自有镜像**，用 Dockerfile 安装全部中文字体：
   - 基础：宋体（SimSun）、仿宋（FangSong）、黑体（SimHei）、楷体（KaiTi）、微软雅黑（Microsoft YaHei）
   - 公文常用：方正小标宋、方正仿宋、方正黑体、方正楷体
   - 西文：Times New Roman、Arial
2. 字体文件**随镜像固化**，不从运行时挂载（避免环境漂移）。
3. 建立"字体覆盖清单"文档，新字体入库走变更流程。
4. 转换后做**分页一致性校验**（见第 6 节）。

**其他已知行为**：

- 宏（`.docm`/`.xlsm`/`.pptm`）**默认禁用**：文件仍会转换，但宏生成的内容不会出现。标书一般无宏，但需在预处理阶段告警提示。
- **链接内容会被丢弃**（自 8.34.0 起）：OOXML 的 `TargetMode="External"` 图片、RTF `INCLUDEPICTURE`、ODT 链接图片都不会被解析，**转换仍返回 200 但内容缺失**。→ 预处理阶段应检测并提示业务方改用嵌入图片。
- 外发请求受出站 URL 过滤（与 Chromium 共用固定代理与允许/拒绝名单）。
- LibreOffice **不是** MS Office 的 1:1 克隆，复杂样式、SmartArt、特殊格式可能渲染略有差异——这是选型时已知并接受的风险。

## 5. 部署形态

> **可执行编排在 [`docker/gotenberg/docker-compose.yml`](../../docker/gotenberg/docker-compose.yml)**（含同目录 Dockerfile、字体目录与 `.env.example`；它依赖 [`docker/gotenberg-lb/nginx.conf`](../../docker/gotenberg-lb/nginx.conf)，**两个目录要一起拷**），支持 `docker compose up -d --scale gotenberg=3` 动态扩缩副本。
> **它不在仓库根的 `docker-compose.yml` 里**：那份只编排除 Gotenberg 以外的依赖与本体（默认 `up` 起 postgres / redis / minio / minio-init / mineru，加 `--profile app` 才起 api / worker / beat / migrate / web）。api / worker 用 `GOTENBERG_URL` 指向这侧的副本入口：同机部署写 `http://host.docker.internal:3000`（compose 已加 host-gateway 映射），分机部署写 `http://<主机>:3000`。
> 下面这段是结构摘录，讲的是取舍。

```yaml
# docker-compose 片段（详见 07-部署与实施计划.md）
gotenberg:
  build:
    context: ./docker/gotenberg        # 基于官方镜像 + 中文字体
    dockerfile: Dockerfile
  # 不发布宿主端口：加副本后第二个副本会 Bind 同一个宿主端口失败，对外统一走下面的 gotenberg-lb
  environment:
    - GOTENBERG_API_BASIC_AUTH_USERNAME=${GOTENBERG_USER}
    - GOTENBERG_API_BASIC_AUTH_PASSWORD=${GOTENBERG_PASS}
    - API_TIMEOUT=${GOTENBERG_API_TIMEOUT:-1800s}   # 容器里用参数名本身，没有 GOTENBERG_ 前缀
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s            # 首次启动需要初始化 LibreOffice，必须留足
  deploy:
    resources:
      limits:
        memory: 2g               # 大文档内存压力会在 500 暴露，需按实测算

# 副本入口：调用方只认一个 URL，副本又不能各自占宿主端口，所以前面放一层 nginx
gotenberg-lb:
  image: nginx:1.27-alpine
  volumes: [./docker/gotenberg-lb/nginx.conf:/etc/nginx/nginx.conf:ro]
  ports: ["127.0.0.1:3000:3000"]
```

**要点**

- 服务**无状态**，可水平扩容：`docker compose up -d --scale gotenberg=3`。副本不能各自发布宿主端口（第二个副本 Bind `127.0.0.1:3000` 直接失败），所以入口是 `gotenberg-lb`（配置见 `docker/gotenberg-lb/nginx.conf`）：它用 Docker 内嵌 DNS 解析服务名，**副本增删 5 秒内生效**，客户端 URL 始终不变（同一份编排内的容器用 `http://gotenberg-lb:3000`，宿主与其他编排用 `http://<主机>:3000`）。
- 只加副本、不提并发上限等于没加：配置中心的 `convert.max_inflight` 要跟着调到副本数（它限的是同时在途的请求数），内存按 `副本数 × GOTENBERG_MEMORY` 估。
- **超时是三层，要按同一量级配**：客户端 `GOTENBERG_TIMEOUT_SECONDS`（默认 1800s）≥ 服务端 `API_TIMEOUT`（默认 1800s，实际硬超时再多 5s）＜ LB 的 `proxy_read_timeout`（3600s）。哪一层更短，都会表现成「转了一半被放弃」。
- **一个容器同一时刻只转一份**：Gotenberg 里 LibreOffice 的并发度写死为 1（`NewProcessSupervisor(..., 1, ...)`，v8.37 源码），官方参数说明也写着「Does not apply to LibreOffice: scale Gotenberg containers instead」。所以**副本数就是并行度**，单容器内其余请求只能排队（`LIBREOFFICE_MAX_QUEUE_SIZE` 默认 0，即不设上限）。
- 变量名规则：容器里的环境变量 = 参数名去前缀、大写、连字符转下划线（`--api-timeout` → `API_TIMEOUT`）；只有 Basic Auth 那两个是 `GOTENBERG_` 前缀的特例。
- 必须设置 `start_period`：LibreOffice 首次启动初始化耗时较长，健康检查过早会误判。
- 内存上限需实测：大文档（>100 MB 的 PPT/带大量图片的 DOCX）在内存压力下会返回 500，此时应**扩容或重试**而非放弃。
- 鉴权：以 Basic Auth 启动，内网部署时通过反向代理再加一层网络隔离。

**大文档量级（实测参考）**

下表来自 `投标skill/LibreOffice安装.md` 记录的一组真实标书转换（同为 LibreOffice 内核，可以直接当量级参考）：

| 场景 | 结果 |
| --- | --- |
| 600 MB `.doc`（上传 1.6 GB、输出 1 GB） | 6 GB 内存约 **12 分 30 秒**；4 GB 内存**跑不完**；10 GB 内存也会被吃满 |
| 用 tmpfs 当临时盘 | 反而更慢（10:07 → 11:25），不要开 |
| 宿主机直接跑 soffice（旧版本） | 1 小时 15 分钟仍未完成 |

两条结论直接决定部署参数：**（1）单份超大文档拼的是内存与超时预算，不是 CPU 核数**——LibreOffice 解析阶段吃单核，只有最后打包才用多核；**（2）提高吞吐只能靠多副本**，也就是上面的 `--scale gotenberg=N` + LB。

## 6. 我们封装的契约

适配器 `OfficeConverter`（内部实现可替换为 unoserver 等）：

```python
class OfficeConverter(Protocol):
    async def to_pdf(
        self,
        src: BinaryIO,
        *,
        filename: str,             # 用于 Gotenberg-Output-Filename
        trace_id: str,             # 用于 Gotenberg-Trace，必须回传校验
    ) -> ConvertResult: ...
```

```python
@dataclass(frozen=True)
class ConvertResult:
    pdf_bytes: bytes
    converter: str            # "gotenberg"
    converter_version: str    # GET /version 的结果，写入 document_version
    trace_id: str
    elapsed_ms: int
```

**约定**

1. **一次只上传一个文件**：避免多文件时响应变成 ZIP，使得处理逻辑分叉。
2. **必传 `Gotenberg-Trace`**（用我们的 `job_id`），并校验响应头回传一致。
3. **400 不重试、500 退避重试**（最多 3 次，指数退避），503 先记录再评估超时配置。
4. 转换前先校验文件是否本身已是 PDF——**PDF 绝不经过此环节**，避免不必要的失真。
5. 转换后与原件一并归档（见 [03](../设计/03-数据模型与溯源设计.md) 的对象布局），并记录血缘关系。
6. 转换产物必须做**分页一致性抽检**：对比转换前后页数是否在合理范围；若业务方提供了原件页数（如 Word 中标注的"第 X 页 共 Y 页"），做抽样比对并在偏差超阈值时告警。

## 7. 选型结论

采用 **Gotenberg 容器 + 自有字体镜像**，作为唯一的 Office→PDF 转换通道：

1. 仅处理非 PDF 输入；PDF 直通。
2. 固定转换参数（见 3.2），参数变更需走评审，因为它会改变分页。
3. 镜像内固化中文字体，字体清单纳入版本管理。
4. 服务无状态：`docker compose --scale gotenberg=3` 即可扩容，入口是 `gotenberg-lb`（客户端 URL 不变，见第 5 节）；属于关键路径，需要独立监控与告警。
5. 转换结果的 `converter_version` 必须落库——**未来任何一次溯源争议，都要能回答"当时是用哪个版本转的"**。
6. **调用形态：同步 HTTP + 在途上限**。用 `convert.max_inflight` 限制同时在途的转换请求数，不依赖 Gotenberg 的 webhook 异步模式。
7. **升级到 webhook 的触发条件**：转换 P95 持续超过 **2 分钟**，或同步调用导致 worker 槽长期被占满。届时再评估异步回调，不提前引入这条复杂度。
