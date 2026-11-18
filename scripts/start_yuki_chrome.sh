#!/usr/bin/env bash
# 在宿主机检查或拉起带 CDP 调试端口（9222）的 Chrome，供 Yuki 浏览器聚焦模式连接。
# 注意：绝不会杀掉正在运行的 Chrome 进程；默认复用用户已有登录态 Profile。
set -euo pipefail

PORT="${YUKI_CHROME_CDP_PORT:-9222}"
USER_CHROME_DIR="$HOME/.config/google-chrome"
DEFAULT_WRAPPER_DIR="$HOME/.cache/yuki-chrome-profile"
PROFILE_DIR="${YUKI_CHROME_PROFILE:-}"

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "[OK] Chrome CDP 已在 127.0.0.1:${PORT} 就绪："
  curl -fsS "http://127.0.0.1:${PORT}/json/version"
  exit 0
fi

CHROME_BIN="${YUKI_CHROME_BIN:-$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || true)}"
if [[ -z "$CHROME_BIN" ]]; then
  echo "[ERR] 未找到 google-chrome / chromium 可执行文件" >&2
  exit 1
fi

if pgrep -x chrome >/dev/null 2>&1 || pgrep -f 'google-chrome' >/dev/null 2>&1; then
  echo "[WARN] 检测到 Chrome 已在运行，但未开启 --remote-debugging-port=${PORT}。"
  echo "       为避免干扰你的日常窗口，本脚本不会关闭现有 Chrome。"
  echo "       若需直接使用你的 Profile 保留登录态，请先手动关闭现有 Chrome 窗口后重新运行本脚本。"
  exit 2
fi

if [[ -z "$PROFILE_DIR" ]]; then
  # Chrome 136+ 拒绝在默认目录 ~/.config/google-chrome 上开 9222 调试口；
  # 通过独立包装目录软链用户的 Default 与 Local State，即可零拷贝保留全部登录态。
  mkdir -p "$DEFAULT_WRAPPER_DIR"
  if [[ -d "$USER_CHROME_DIR/Default" && ! -e "$DEFAULT_WRAPPER_DIR/Default" ]]; then
    ln -sfn "$USER_CHROME_DIR/Default" "$DEFAULT_WRAPPER_DIR/Default"
  fi
  if [[ -f "$USER_CHROME_DIR/Local State" && ! -e "$DEFAULT_WRAPPER_DIR/Local State" ]]; then
    ln -sfn "$USER_CHROME_DIR/Local State" "$DEFAULT_WRAPPER_DIR/Local State"
  fi
  PROFILE_DIR="$DEFAULT_WRAPPER_DIR"
fi

echo "[INFO] 正在启动 Chrome (port=${PORT}, user-data-dir=${PROFILE_DIR})..."
if command -v systemd-run >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
  systemctl --user reset-failed yuki-chrome >/dev/null 2>&1 || true
  systemd-run --user --unit=yuki-chrome \
    --description="Yuki Browser Focus Chrome CDP (${PORT})" \
    --setenv=DISPLAY="${DISPLAY:-:0}" \
    --collect \
    "$CHROME_BIN" \
    --remote-debugging-port="${PORT}" \
    --remote-allow-origins="*" \
    --user-data-dir="${PROFILE_DIR}" \
    --no-first-run >/dev/null
else
  nohup "$CHROME_BIN" \
    --remote-debugging-port="${PORT}" \
    --remote-allow-origins="*" \
    --user-data-dir="${PROFILE_DIR}" \
    --no-first-run \
    >/tmp/yuki-chrome.log 2>&1 &
fi

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    echo "[OK] Chrome CDP 已就绪: http://127.0.0.1:${PORT}"
    exit 0
  fi
  sleep 0.3
done

echo "[ERR] Chrome 启动后未检测到 127.0.0.1:${PORT} 监听，请查看 /tmp/yuki-chrome.log" >&2
exit 1
