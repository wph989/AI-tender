# 官方 Gotenberg + 中文字体。
# 为什么必须自建：LibreOffice 依赖已装字体计算分页，缺字体 → 分页漂移 →
# page/bbox 与用户看到的原件对不上 → 溯源直接失效（见 docs/调研/02 第 4 节）。
ARG GOTENBERG_IMAGE=gotenberg/gotenberg:8
FROM ${GOTENBERG_IMAGE}

USER root

# apt 源替换（默认不动，保持与官方源一致的构建结果）。
# 内网 / 跨境网络下载 deb.debian.org 会慢到卡住构建（实测 134MB 的包十几分钟没动），
# 这时传 --build-arg DEBIAN_MIRROR=mirrors.aliyun.com 之类把源换掉。
ARG DEBIAN_MIRROR=

# 是否补装可选的 CJK 字体包（默认不装）。
# 基础镜像里已经有 curl 与 fonts-noto-cjk：实测 apt 只会额外装 fonts-noto-cjk-extra(134MB)
# 与 fonts-wqy-zenhei(8MB)，合计 142MB——慢网络下这是构建卡死的主因，而我们的自有字体
# （本目录 fonts/，公文常用的宋体/仿宋/楷体/黑体等）已经覆盖了标书真正会用到的字形。
# 需要更全的生僻字覆盖时再加 --build-arg INSTALL_EXTRA_FONTS=1。
# 做成开关而不是直接删：换基础镜像后如果自带字体被移除，这里还能补回来。
ARG INSTALL_EXTRA_FONTS=0

# 自有字体随镜像固化，不从运行时挂载：挂载会让同一份文档在不同机器上转出不同分页。
# 放在 apt 之前是刻意的：字体文件不依赖 apt，先拷进来，慢网络下 apt 那层挂了也不影响这一层
# 已经进缓存，重试时不用重传 167MB。
COPY fonts/ /usr/share/fonts/truetype/tender/

RUN set -eux; \
    if [ -n "${DEBIAN_MIRROR}" ] && [ "${DEBIAN_MIRROR}" != "deb.debian.org" ]; then \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
        fi; \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list; \
        fi; \
    fi; \
    if [ "${INSTALL_EXTRA_FONTS}" = "1" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends fonts-noto-cjk-extra fonts-wqy-zenhei; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    if ! command -v curl >/dev/null 2>&1; then \
        apt-get update; \
        apt-get install -y --no-install-recommends curl; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    fc-cache -f

# 回到官方镜像的非 root 用户（官方 Dockerfile 里固定为 gotenberg / uid 1001）
USER gotenberg

EXPOSE 3000