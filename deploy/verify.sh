#!/usr/bin/env bash
# 自进化校验门：在临时容器里按顺序跑 5 道门，任一门失败立即返回非 0。
#
# 设计要点：
#   - 绝不碰生产容器，也不碰生产数据（data/yuki_memory/memory 全部 tmpfs）
#   - 用 --network none 断网，防止校验代码意外调用外部 API 花钱或改动线上
#   - 失败时把日志尾部按 GATE 标记打出来，直接可回灌给小女仆当反馈
#
# 用法: deploy/verify.sh [--quiet]
set -uo pipefail

ROOT="${YUKI_ROOT:-/home/asumi/Yuki}"
IMAGE="${YUKI_IMAGE:-yuki:base}"
QUIET="${1:-}"

say() { [[ "$QUIET" == "--quiet" ]] || echo "$@"; }
fail() {
  echo "GATE_FAILED: $1"
  [[ -n "${2:-}" ]] && echo "$2" | tail -40
  exit 1
}

run_gate() {
  # $1=门名  $2=容器内命令
  local name="$1" cmd="$2" out rc
  say "=== 门[$name] ==="
  out=$(docker run --rm --network none \
        -v "$ROOT:$ROOT:ro" \
        -v "$ROOT/models:$ROOT/models:ro" \
        -v "$ROOT/configs:$ROOT/configs:ro" \
        --tmpfs "$ROOT/data":rw,size=256m \
        --tmpfs "$ROOT/yuki_memory":rw,size=256m \
        --tmpfs "$ROOT/memory":rw,size=64m \
        --tmpfs "$ROOT/logs":rw,size=64m \
        --tmpfs /tmp:rw,size=256m \
        -e PYTHONPYCACHEPREFIX=/tmp/pycache \
        -e YUKI_DRY_RUN=1 \
        -w "$ROOT" -e YUKI_ROOT="$ROOT" "$IMAGE" bash -lc "$cmd" 2>&1)
  rc=$?
  if [[ $rc -ne 0 ]]; then
    fail "$name" "$out"
  fi
  say "$out" | tail -5
  return 0
}

# 1. 静态编译
run_gate compileall \
  "python -m compileall -q -x 'reference|node_modules' core utils modules network main.py config.py init.py || exit 1"

# 2. 关键模块导入（能抓出循环导入、缺失依赖、语法之外的问题）
run_gate import \
  "python -c 'import main, config, core.brain, core.session_pipeline, core.maid.maid, core.maid.maid_charter, utils.health_server; print(\"import ok\")' || exit 1"

# 3. 单元测试：与基线对比，只对「新增失败」报警（既有环境性失败已在基线里）
run_gate tests \
  "python deploy/test_gate.py || exit 1"

# 4. 试启动：初始化全流程但跳过 NapCat 接管
run_gate dry_run \
  "timeout 300 python main.py 2>&1 | tail -30; exit \${PIPESTATUS[0]}"

# 5. 探针自检：确认 /health 契约没被改坏
run_gate health \
  "python -c '
from utils.health_server import _snapshot, set_ready
import json
set_ready(True, mode=\"verify\")
s = _snapshot()
assert s[\"ready\"] is True and s[\"status\"] == \"ok\", s
print(\"health ok\", json.dumps(s))
' || exit 1"

say "ALL_GATES_PASSED"
exit 0
