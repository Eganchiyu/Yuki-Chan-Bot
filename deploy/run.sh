#!/usr/bin/env bash
# 启动生产容器。
#
# 关键约束（安全边界，勿随意放宽）：
#   - 代码树 /app 只读挂载：容器内任何进程都改不坏生产代码，改动只能由宿主 supervisor 施加
#   - 数据目录单独读写挂载：data/logs/memory/yuki_memory/skills/configs/maid_venv/staging
#   - staging 是小女仆唯一能写代码的地方，由 supervisor 审核后才应用
#   - --network host：容器内 127.0.0.1:3001 直连宿主 NapCat，无需额外网络配置
set -euo pipefail

ROOT="${YUKI_ROOT:-/home/asumi/Yuki}"
IMAGE="${YUKI_IMAGE:-yuki:base}"
NAME="${YUKI_CONTAINER:-yuki}"

RW_DIRS=(
  data logs memory yuki_memory skills workspace tasks temp
  configs maid_venv output temp_images staging
)

docker rm -f "$NAME" >/dev/null 2>&1 || true

# 以宿主 uid 运行：容器内写出的 staging/、logs/ 属主就是 asumi，
# 宿主 supervisor 才能回写 result.json 并管理这些文件。
mkdir -p "$ROOT/data/home"

# 容器内路径与宿主完全一致（挂到同一个绝对路径）。
# 原因：NapCat 在宿主机，Yuki 用 `file:///<绝对路径>` 发图片/文件/语音，
# 路径一旦不同（例如容器内 /app），NapCat 就找不到文件，表情包会静默发不出去。
args=(
  run -d --name "$NAME"
  --restart unless-stopped
  --network host
  --user "$(id -u):$(id -g)"
  -e HOME="$ROOT/data/home"
  --label yuki.role=production
  -v "$ROOT:$ROOT:ro"
  -v "$ROOT/models:$ROOT/models:ro"
)

for d in "${RW_DIRS[@]}"; do
  mkdir -p "$ROOT/$d"
  args+=(-v "$ROOT/$d:$ROOT/$d")
done

args+=(
  -w "$ROOT"
  -e YUKI_HEALTH_PORT=8778
  -e YUKI_DESKTOP_PET=0
  "$IMAGE"
)

docker "${args[@]}" >/dev/null
echo "$NAME"
