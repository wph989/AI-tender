# 官方 Gotenberg + 中文字体。
# 为什么必须自建：LibreOffice 依赖已装字体计算分页，缺字体 → 分页漂移 →
# page/bbox 与用户看到的原件对不上 → 溯源直接失效（见 docs/调研/02 第 4 节）。
ARG GOTENBERG_IMAGE=gotenberg/gotenberg:8
FROM ${GOTENBERG_IMAGE}

USER root

# curl 供 compose 健康检查；Noto CJK 覆盖黑体/宋体的常见变体，wqy 补常用中文字形。
# 公文常用的宋体/仿宋/楷体/方正系列与西文版权字体不随镜像分发，放 fonts/ 目录自带（见该目录 README）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 自有字体随镜像固化，不从运行时挂载：挂载会让同一份文档在不同机器上转出不同分页
COPY fonts/ /usr/share/fonts/truetype/tender/
RUN fc-cache -f

# 回到官方镜像的非 root 用户（官方 Dockerfile 里固定为 gotenberg / uid 1001）
USER gotenberg

EXPOSE 3000