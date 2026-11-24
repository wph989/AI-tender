# MinerU 独立部署

本目录是 MinerU 解析服务的独立编排，用于把 MinerU 单独部署在一台 GPU 机器上，供
AI-Tender 的 API / Worker 通过 HTTP 调用。接口协议、能力矩阵和已知坑见
[接口调研](../../docs/调研/01-接口调研-MinerU.md)；整体部署位置见
[部署与实施计划](../../docs/工程/07-部署与实施计划.md)。

它负责把 PDF（以及经 Gotenberg 转成 PDF 的 Office 文件）解析成 `middle_json`，产出页面、
元素与 bbox。**没有 MinerU，PDF 与 docx 等文档都无法完成解析。**

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `docker-compose.yml` | 官方 4.x 编排（`docker/compose.yaml`），含 `api` / `openai-server` / `router` / `webui` 四个 profile；镜像已换成可直接拉取的社区预构建镜像 |
| `README.md` | 本文件 |

本目录不再放 Dockerfile 和 `.env`：官方编排直接引用本地镜像 `mineru:4`，没有需要插值的变量。

## 镜像从哪来

**官方没有发布可直接 `docker pull` 的 4.x 镜像，也没有提供镜像 tar。**
官方文档 [Docker 部署](https://opendatalab.github.io/MinerU/zh/quick_start/docker_deployment/)
只给出构建命令，`docker/compose.yaml` 里的 `image: mineru:4` 是构建后得到的**本地标签**；
GitHub release 附件只有一个 `mineru-4.0.7-py3-none-any.whl`，不是镜像。

因此本目录的编排把镜像换成了可直接拉取的社区预构建镜像：

```yaml
image: ${MINERU_IMAGE:-mustangxu/mineru:4.0.12}
```

`docker compose --profile api up -d` 会自动拉取。已核对该镜像的构建记录：

- 基础镜像为官方同款 vLLM（CUDA 13.0）；
- 安装 `mineru[torch]==4.0.12`，并从 Hugging Face 预下载 `standard` 档模型；
- entrypoint 与官方 Dockerfile 一致（`MINERU_MODEL_SOURCE=local`）；
- 压缩后约 12 GB，首次启动前需要预留磁盘与下载时间。

> **注意**：`mustangxu/mineru:4.0.12` 不是官方发布，来源无法审计。处理标书等敏感文档时，
> 优先使用自己按官方 Dockerfile 构建的镜像，或从已经部署成功的可信机器导出。确需使用社区
> 镜像请自行评估供应链风险。

版本说明：本项目调研基准是 `4.0.7`，该镜像是 `4.0.12`，二者都属于 `>=4.0,<5`，使用同一套
`/v1` 协议；如必须严格 4.0.7，只能按下面的官方方式自行构建。

### 切回官方方式

把各服务的 `image` 改回 `mineru:4`，并先在目标机器准备好该镜像：

```bash
# 从已经部署成功的机器搬过来
docker save mineru:4 | gzip > mineru-4.tar.gz   # 源机器
docker load -i mineru-4.tar.gz                  # GPU 机器

# 或按官方 Dockerfile 构建一次
git clone --depth 1 --branch mineru-4.0.7-released https://github.com/opendatalab/MinerU.git
cd MinerU
docker build -t mineru:4 -f docker/china/Dockerfile .   # 国内
# docker build -t mineru:4 -f docker/global/Dockerfile . # 海外
```

官方 Dockerfile 安装的是 `mineru[torch]>=4.0,<5`，标签不锁定具体 4.x 版本；需要严格 4.0.7 时把
安装行改成 `mineru[torch]==4.0.7` 再构建。构建后可核对版本：

```bash
docker run --rm mineru:4 python3 -c 'from mineru.version import __version__; print(__version__)'
```

## 前置条件

- NVIDIA GPU 与驱动。`standard` 档按 8 GB 显存起步规划，本项目实测机器为 16 GB 显存。
- Docker Engine 24+ 与 Compose v2。
- NVIDIA Container Toolkit（让容器能用 GPU）。
- 能拉取 `mustangxu/mineru:4.0.12` 的网络（首次约 12 GB；见上一节）。

安装 GPU 容器支持（Ubuntu / Debian 宿主机，WSL 内同样执行）：

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's|^deb |deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] |' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

验证容器能看到 GPU：

```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

## 选哪个 profile

官方编排有四个 profile，本项目只用 `api`：

| profile | 容器 | 端口 | 用途 |
| --- | --- | --- | --- |
| **api** | `mineru-api` | 8000 | **本项目对接的 `/v1/uploads`、`/v1/parse/jobs`、`/v1/files`** |
| openai-server | `mineru-openai-server` | 30000 | OpenAI 兼容的推理接口（`/v1/chat/completions`），不做文档解析 |
| router | `mineru-router` | 8002 | 多 GPU / 多实例汇总，单机不需要 |
| webui | `mineru-webui` | 7860 | 给人操作的 Gradio 页面 |

启动命令：

```bash
cd docker/mineru
docker compose --profile api up -d
```

从仓库根目录：

```bash
docker compose -f docker/mineru/docker-compose.yml --profile api up -d
```

不要同时启动多个 profile：四个服务都申请 GPU（`device_ids: ["0"]`），会互相抢显存。

## 已配置的启动参数

`docker-compose.yml` 的 `mineru-api` 已按本项目要求启动：

```yaml
command:
  - api-server
  - --host
  - 0.0.0.0
  - --port
  - "8000"
  - --tier
  - standard
  - --api-key
  - ${MINERU_API_KEY:-123456}
```

- `--tier standard`：固定解析档位，与生产要求一致；`advanced` 只用于人工对单文档触发。
- `--api-key`：启用鉴权，请求需带 `Authorization: Bearer <key>`；默认值 `123456` 与
  `apps/api/.env` 的 `MINERU_API_KEY` 保持一致。要换密钥时，在本目录创建 `.env` 写
  `MINERU_API_KEY=<新值>`（或启动前导出同名环境变量），并同步修改 `apps/api/.env`，
  然后 `docker compose --profile api up -d` 重建容器。
- 不写 `--api-key` 时服务无鉴权，应用侧发来的 `Authorization` 会被忽略；端口暴露到网络时
  必须启用。

端口与宿主机冲突时改映射：同机运行 uvicorn（默认占 8000）时改成：

```yaml
ports:
  - "8100:8000"
```

之后 `apps/api/.env` 的 `MINERU_URL` 用 `http://localhost:8100`。

## 启动与验证

```bash
docker compose --profile api up -d
docker compose ps
docker compose logs -f mineru-api
```

首次启动会先拉取镜像（约 12 GB），下载完成前 `docker compose ps` 看不到容器属于正常现象。

健康检查（`/v1/health` 不需要鉴权）：

```bash
curl http://<主机>:<端口>/v1/health
```

正常返回 `status: ok` 和 `version`。若返回 503，说明模型预加载失败或显存不足。

验证鉴权与档位（加了 `--api-key` 时）：

```bash
curl -H "Authorization: Bearer <MINERU_API_KEY>" http://<主机>:<端口>/v1/tiers
```

停止 / 重启：

```bash
docker compose --profile api down
docker compose --profile api up -d
```

## 接入 AI-Tender

修改 `apps/api/.env`：

```ini
MINERU_URL=http://<主机>:<端口>
MINERU_API_KEY=<与容器启动参数一致；未启用鉴权时留空>
MINERU_BBOX_ORIGIN=top_left
MINERU_BBOX_ROTATION=visual
```

- API / Worker 在宿主机直接跑时，`<主机>` 填本机可用 `localhost`；跨机部署填 GPU 机器的内网地址。
- 改完后重启后端：

  ```powershell
  .\scripts\start-backend.ps1 -Force
  ```

- 提交一份 PDF 验证解析链路；docx 等 Office 文件还需要先部署 Gotenberg，
  见 [`docker/gotenberg/`](../gotenberg/)。

## 运维注意

- **重启会丢失服务端任务索引**：MinerU 的 upload / file / job 索引是进程内状态，容器重启后
  旧 `job_id` 全部失效。应用侧会按 `sha256` 重新提交；但官方编排没有挂载卷，上传文件落在容器
  临时目录，重建容器后也无法复用。需要跨重启复用时，给 `mineru-api` 加：

  ```yaml
  command: [..., "--upload-dir", "/data/uploads"]
  volumes:
    - minerudata:/data
  ```

  并在文件末尾声明 `volumes: { minerudata: {} }`。
- **档位**：生产固定 `standard`；`advanced` 只在人工对单文档触发时使用。服务实际支持范围以
  `GET /v1/tiers` 为准。
- **健康检查**：`/v1/health` 非 200 即视为不健康；基础镜像没有 `curl` 时删掉编排里的
  `healthcheck` 即可，应用只按 `MINERU_URL` 调用，不依赖容器健康状态。
- **日志**：`docker compose --profile api logs`；应用侧的解析任务日志在 `logs/worker/`。
- **资源**：转换与解析是重资源任务；GPU 显存不足通常表现为健康检查 503 或任务失败。

## 故障排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `403 Forbidden` 拉取失败 | 镜像名写错或镜像不存在，镜像加速器去上游查不到 | 确认 `image` 是 `mustangxu/mineru:4.0.12`；不存在官方 `mineru:4` 可拉 |
| `No such image` | `image` 被改成了本地标签 `mineru:4`，但本机没有 | 改回 `mustangxu/mineru:4.0.12`，或先把 `mineru:4` 导入/构建好 |
| `Connection refused` | 端口未发布、防火墙、容器未启动 | 检查 `docker compose ps`、端口映射与防火墙 |
| `port is already allocated` | 宿主机 uvicorn 或其他服务占用 8000 | 改成 `"8100:8000"`，并同步 `MINERU_URL` |
| 容器反复重启，日志报 GPU 错误 | 未安装 NVIDIA Container Toolkit 或驱动不匹配 | 按前置条件安装并 `nvidia-smi` 验证 |
| `/v1/health` 返回 503 | 模型预加载失败、显存不足 | 看 `docker compose logs mineru-api`，确认镜像版本与显存 |
| 应用侧 401 | `--api-key` 与 `MINERU_API_KEY` 不一致 | 两边改成同一个值后重启容器与后端 |
| `/v1/uploads` 返回 404 | 起的是 `openai-server` / `webui`，不是 `api` | 改用 `--profile api` |
| docx 在转换阶段就失败 | 缺 Gotenberg，尚未进入 MinerU | 部署 [`docker/gotenberg/`](../gotenberg/) |
| 解析任务卡住 | 服务重启导致 job 失效 | 协议细节见[接口调研](../../docs/调研/01-接口调研-MinerU.md) |

## 没有 GPU 时

不要在无 GPU 机器上启动本编排。改用一台独立的 GPU 机器部署 MinerU 并配置
`MINERU_URL`；若使用仓库根 Compose 的一体化起法，用 `docker compose up -d --scale mineru=0`
跳过内置 MinerU，或者在能拉取镜像的机器上先准备好同一镜像。
