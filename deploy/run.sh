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

args=(
  run -d --name "$NAME"
  --restart unless-stopped
  --network host
  --label yuki.role=production
  -v "$ROOT:/app:ro"
  -v "$ROOT/models:/app/models:ro"
)

for d in "${RW_DIRS[@]}"; do
  mkdir -p "$ROOT/$d"
  args+=(-v "$ROOT/$d:/app/$d")
done

args+=(
  -e YUKI_HEALTH_PORT=8778
  -e YUKI_DESKTOP_PET=0
  "$IMAGE"
)

docker "${args[@]}" >/dev/null
echo "$NAME"
