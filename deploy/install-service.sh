#!/usr/bin/env bash
# 安装常驻服务：自进化守护进程（systemd）+ 每日存储保留（cron）
#
# 需要 sudo。幂等，可重复执行。
# 卸载：
#   sudo systemctl disable --now yuki-supervisor
#   sudo rm /etc/systemd/system/yuki-supervisor.service /etc/cron.d/yuki-retention
#   sudo systemctl daemon-reload
set -euo pipefail

ROOT="${YUKI_ROOT:-/home/asumi/Yuki}"
USER_NAME="${YUKI_USER:-asumi}"

echo "[1/4] 安装 systemd 服务"
sudo sed -e "s|/home/asumi/Yuki|$ROOT|g" -e "s|^User=.*|User=$USER_NAME|" \
    "$ROOT/deploy/yuki-supervisor.service" > /tmp/yuki-supervisor.service
sudo install -m 644 /tmp/yuki-supervisor.service /etc/systemd/system/yuki-supervisor.service
rm -f /tmp/yuki-supervisor.service

echo "[2/4] 安装每日保留策略 cron"
printf '# Yuki 存储保留策略：trace 归档 / 日志截断 / staging 清理\n0 4 * * * %s /usr/bin/python3 %s/deploy/retention.py >> %s/logs/retention.log 2>&1\n' \
    "$USER_NAME" "$ROOT" "$ROOT" | sudo tee /etc/cron.d/yuki-retention >/dev/null
sudo chmod 644 /etc/cron.d/yuki-retention

echo "[3/4] 重载并启动"
sudo systemctl daemon-reload
sudo systemctl enable yuki-supervisor
sudo systemctl restart yuki-supervisor

echo "[4/4] 状态"
sleep 2
systemctl --no-pager --lines=5 status yuki-supervisor || true

echo "完成。日志：$ROOT/logs/supervisor.log"
