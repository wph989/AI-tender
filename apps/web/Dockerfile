# 前端镜像（Next.js standalone 产物）。
# 构建上下文是仓库根：pnpm workspace 的锁文件与依赖实体都在根，
# 用 apps/web 当上下文会拿不到 pnpm-lock.yaml（见 compose 里的 context/dockerfile）。

FROM node:24-alpine AS builder

# pnpm 版本对齐仓库（唯一事实源是开发机与 CI 用的同一版本），避免锁文件被重写
RUN corepack enable && corepack prepare pnpm@11.5.2 --activate

WORKDIR /repo

# 先只拷清单文件：依赖层能复用缓存，改业务代码不会重装依赖
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/contract ./packages/contract
# 内网离线环境把 registry 换成内部镜像源（或在基础镜像里预置 pnpm store）
# 若私服拦下生命周期脚本导致原生依赖缺二进制（Tailwind oxide / sharp），
# 在下一行之后补：RUN pnpm rebuild @tailwindcss/oxide sharp
RUN pnpm install --frozen-lockfile

COPY apps/web ./apps/web

# Next 的 rewrites 在构建期求值：容器里必须指向 compose 网络中的服务名，
# 运行时再改环境变量是无效的，所以这里必须是构建参数。
ARG API_PROXY_TARGET=http://api:8000
ENV API_PROXY_TARGET=${API_PROXY_TARGET}
# 构建脚本会把 pdfjs 的 worker / cMaps 复制进 public/pdfjs/，随镜像固化
RUN pnpm --filter @ai-tender/web build


FROM node:24-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# standalone 已包含 server.js 与裁剪后的 node_modules（依赖实体在 .pnpm 下），整棵树拷过来即可；
# .next/static 与 public 不在 standalone 里，必须单独拷，否则页面白屏 / pdfjs 资源 404。
COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /repo/apps/web/public ./apps/web/public

EXPOSE 3000
CMD ["node", "apps/web/server.js"]