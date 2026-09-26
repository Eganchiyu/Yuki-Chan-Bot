# Cloudflare Tunnel (cloudflared) 安装与配置指南

生成时间：2026-09-16 20:22
主机：Arch Linux x86_64 (asumi)

## 一、安装结果
- 安装方式：官方静态二进制（因无 sudo 密码，未走 pacman）
- 安装路径：/home/asumi/.local/bin/cloudflared
- 版本：cloudflared version 2026.9.1 (built 2026-09-11-13:35 UTC)
- 该目录已在 PATH 中，可直接使用 `cloudflared` 命令
- 网络：通过本机 clash 代理 127.0.0.1:7890 下载

## 二、待主人操作：授权登录（关键步骤）
登录进程已在后台运行，正在等待授权。请点击以下链接，在浏览器中登录 Cloudflare 账号并选择要绑定的域名授权：

https://dash.cloudflare.com/argotunnel?aud=&callback=https%3A%2F%2Flogin.cloudflareaccess.org%2FsiBmh5puynJgzyQs9QlIBQ28wqknDvq7d_IyKGQxLQI%3D

授权成功后，本机会自动生成证书文件：~/.cloudflared/cert.pem
（注意：此授权链接为一次性 token，过期后需重新执行 cloudflared tunnel login）

## 三、授权完成后的执行命令清单
将下面命令中的 <TUNNEL_NAME> 和 <你的域名> 替换为实际值。

# 1. 创建隧道（生成隧道 ID）
cloudflared tunnel create <TUNNEL_NAME>

# 2. 查看隧道列表，记录隧道 ID
cloudflared tunnel list

# 3. 创建配置文件 ~/.cloudflared/config.yml
# 示例内容（将 <TUNNEL_ID> <你的域名> <SSH用户名> 替换）：
# tunnel: <TUNNEL_ID>
# credentials-file: /home/asumi/.cloudflared/<TUNNEL_ID>.json
# ingress:
#   - hostname: app.<你的域名>
#     service: http://localhost:8080
#   - service: http_status:404

# 4. 把域名 CNAME 指向隧道（DNS 路由）
cloudflared tunnel route dns <TUNNEL_NAME> app.<你的域名>

# 5. 前台运行测试
cloudflared tunnel --config /home/asumi/.cloudflared/config.yml run <TUNNEL_NAME>

# 6.（可选）安装为系统服务开机自启（需要 sudo）
sudo cloudflared service install

## 四、需要主人提供的信息
1. Cloudflare 账号（用于点击授权链接登录）。
2. 一个已托管在 Cloudflare 的域名（NS 已指向 Cloudflare），以及想要暴露的子域名（如 app.example.com）。
3. 要穿透的本地服务地址与端口（如 http://localhost:8080）。
4. 若希望安装为系统服务（开机自启），需要本机 sudo 密码。

## 五、当前状态
- 授权链接已生成，等待主人点击授权。
- 授权进程 pid: 2033097
- 授权日志: /tmp/cf_login.log
- 由于尚未获得 Cloudflare 账号授权，无法自动继续创建 tunnel 与绑定域名。
