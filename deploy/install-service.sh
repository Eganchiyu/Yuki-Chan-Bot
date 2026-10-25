#!/usr/bin/env bash
# 安装常驻服务：自进化守护进程（systemd）+ 每日存储保留（cron）
#
# 需要 sudo。幂等，可重复执行。
# 卸载：
#   sudo systemctl disable --now yuki-supervisor yuki-maid-runner
#   sudo rm /etc/systemd/system/yuki-supervisor.service /etc/systemd/system/yuki-maid-runner.service /etc/cron.d/yuki-retention
#   sudo systemctl daemon-reload
set -euo pipefail

ROOT="${YUKI_ROOT:-/home/asumi/Yuki}"
USER_NAME="${YUKI_USER:-asumi}"

echo "[1/5] 安装 systemd 服务（自进化守护 + 小女仆执行器）"
sudo sed -e "s|/home/asumi/Yuki|$ROOT|g" -e "s|^User=.*|User=$USER_NAME|" \
    "$ROOT/deploy/yuki-supervisor.service" > /tmp/yuki-supervisor.service
sudo install -m 644 /tmp/yuki-supervisor.service /etc/systemd/system/yuki-supervisor.service
rm -f /tmp/yuki-supervisor.service

sudo sed -e "s|/home/asumi/Yuki|$ROOT|g" -e "s|^User=.*|User=$USER_NAME|" -e "s|^Group=.*|Group=$USER_NAME|" \
    "$ROOT/deploy/yuki-maid-runner.service" > /tmp/yuki-maid-runner.service
sudo install -m 644 /tmp/yuki-maid-runner.service /etc/systemd/system/yuki-maid-runner.service
rm -f /tmp/yuki-maid-runner.service

echo "[2/5] 安装每日保留策略 cron"
printf '# Yuki 存储保留策略：trace 归档 / 日志截断 / staging 清理\n0 4 * * * %s /usr/bin/python3 %s/deploy/retention.py >> %s/logs/retention.log 2>&1\n' \
    "$USER_NAME" "$ROOT" "$ROOT" | sudo tee /etc/cron.d/yuki-retention >/dev/null
sudo chmod 644 /etc/cron.d/yuki-retention

echo "[3/5] 重载并启动"
sudo systemctl daemon-reload
sudo systemctl enable yuki-supervisor yuki-maid-runner
sudo systemctl restart yuki-supervisor
# 执行器单独重启：它只是拉起 harness 子进程，不碰代码树
sudo systemctl restart yuki-maid-runner

echo "[4/5] 状态"
sleep 2
systemctl --no-pager --lines=5 status yuki-supervisor || true
systemctl --no-pager --lines=5 status yuki-maid-runner || true

echo "[5/5] 自检"
/usr/bin/python3 "$ROOT/deploy/maid_runner.py" --print-env || true

echo "完成。日志：$ROOT/logs/supervisor.log / $ROOT/logs/maid_runner.log"
