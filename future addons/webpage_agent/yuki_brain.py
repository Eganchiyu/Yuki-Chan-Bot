"""
Yuki Desktop Agent - Brain v0.5
HTTP POST + 轮询模式。最简单最稳。

用法：
    conda activate ai_env
    python yuki_brain.py
"""

import json
import sys
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from collections import deque

# ==================== 配置 ====================

HOST = '127.0.0.1'
PORT = 8766

BANNER = r"""
  ╔══════════════════════════════════════════════╗
  ║     🍙 Yuki Desktop Agent - Brain v0.5     ║
  ║     http://127.0.0.1:8766                  ║
  ╚══════════════════════════════════════════════╝
"""

# ==================== 状态 ====================

current_elements = []
current_url = ''
current_title = ''
command_queue = deque()  # 待下发的指令


# ==================== 页面展示 ====================

def print_page_state(snapshot):
    global current_elements, current_url, current_title

    current_url = snapshot.get('url', '')
    current_title = snapshot.get('title', '')
    current_elements = snapshot.get('elements', [])

    ts = datetime.now().strftime('%H:%M:%S')
    trigger = snapshot.get('trigger', '?')

    print(f"\n{'─' * 60}")
    print(f"  📄 [{ts}] {current_title}")
    print(f"  🔗 {current_url}")
    print(f"  📊 {len(current_elements)} elements (trigger: {trigger})")
    print(f"{'─' * 60}")

    if not current_elements:
        print("  (no interactive elements)")
        print(f"{'─' * 60}\n")
        return

    for el in current_elements:
        icon = get_icon(el)
        state = ''
        if el.get('state'):
            state = f" [{', '.join(el['state'])}]"
        # 显示上下文（如果有）
        ctx = el.get('context', '')
        if ctx:
            if len(ctx) > 50:
                ctx = ctx[:47] + '...'
            ctx = f"  \033[90m({ctx})\033[0m"
        text = el.get('text', '') or el.get('placeholder', '') or el.get('href', '') or ''
        if not text:
            text = f"<{el.get('tag', '?')}>"
        if len(text) > 50:
            text = text[:47] + '...'
        tag_extra = el.get('type') or ''
        if tag_extra:
            tag_extra = f":{tag_extra}"
        else:
            tag_extra = ''
        print(f"  {el['id']:>3}  {icon}  {el['tag']}{tag_extra:8s}  {text}{state}{ctx}")

    print(f"{'─' * 60}")
    print(f"  click <id> | type <id> <text> | scroll | scan | open <url> | list | quit")
    print()


def get_icon(el):
    tag, t = el.get('tag', ''), el.get('type', '')
    if tag == 'button': return '🔘'
    if tag == 'a':       return '🔗'
    if tag == 'input':
        if t == 'password': return '🔒'
        if t in ('checkbox', 'radio'): return '☑️'
        return '📝'
    if tag == 'select':  return '📋'
    if tag == 'textarea': return '📄'
    return '▪️'


# ==================== HTTP 服务 ====================

class BrainHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # 静默

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json_response(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except:
            self._json_response(400, {'error': 'bad json'})
            return

        if self.path == '/scan':
            print_page_state(data)
            self._json_response(200, {'ok': True})

        elif self.path == '/action_result':
            status = '✅' if data.get('ok') else '❌'
            error = f" - {data.get('error')}" if data.get('error') else ''
            print(f"  {status} {data.get('action', '?')}{error}")
            self._json_response(200, {'ok': True})

        else:
            self._json_response(404, {'error': 'not found'})

    def do_GET(self):
        """插件轮询此端点获取指令"""
        if self.path == '/poll':
            if command_queue:
                cmd = command_queue.popleft()
                self._json_response(200, cmd)
            else:
                self._json_response(200, {'type': 'noop'})

        elif self.path == '/status':
            self._json_response(200, {
                'elements': len(current_elements),
                'url': current_url,
                'title': current_title,
                'pending_commands': len(command_queue),
            })
        else:
            self._json_response(404, {'error': 'not found'})


# ==================== 用户输入 ====================

def find_element(eid):
    for el in current_elements:
        if el.get('id') == eid:
            return el
    return None


def user_input_loop():
    while True:
        try:
            line = input('> ')
        except (EOFError, KeyboardInterrupt):
            print('\n👋 Bye!')
            return

        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ('quit', 'exit'):
            print('👋 Bye!')
            return

        elif cmd == 'scan':
            command_queue.append({'type': 'scan'})
            print('  📡 Scan requested')

        elif cmd == 'list':
            if current_elements:
                print_page_state({'url': current_url, 'title': current_title,
                                  'elements': current_elements, 'trigger': 'list'})
            else:
                print('  (no elements)')

        elif cmd == 'click' and len(parts) >= 2:
            try:
                eid = int(parts[1])
                el = find_element(eid)
                if el:
                    print(f'  🖱️  Clicking: {el.get("text", el.get("tag"))}')
                    command_queue.append({
                        'type': 'action',
                        'action': {'action': 'click', 'target': el['selector']}
                    })
                else:
                    print(f'  ❌ #{eid} not found')
            except ValueError:
                print('  Usage: click <id>')

        elif cmd == 'type' and len(parts) >= 3:
            try:
                eid = int(parts[1])
                text = ' '.join(parts[2:])
                el = find_element(eid)
                if el:
                    print(f'  ⌨️  Typing "{text}"')
                    command_queue.append({
                        'type': 'action',
                        'action': {'action': 'type', 'target': el['selector'], 'text': text}
                    })
                else:
                    print(f'  ❌ #{eid} not found')
            except ValueError:
                print('  Usage: type <id> <text>')

        elif cmd == 'scroll':
            direction = parts[1] if len(parts) >= 2 else 'down'
            amount = int(parts[2]) if len(parts) >= 3 else 500
            if direction == 'up':
                amount = -amount
            command_queue.append({
                'type': 'action',
                'action': {'action': 'scroll', 'target': 'window', 'amount': amount}
            })
            print(f'  📜 Scroll {direction} {abs(amount)}px')

        elif cmd == 'open' and len(parts) >= 2:
            url = parts[1]
            if not url.startswith('http'):
                url = 'https://' + url
            command_queue.append({
                'type': 'action',
                'action': {'action': 'navigate', 'url': url}
            })
            print(f'  🌐 Opening: {url}')

        else:
            print(f'  ❓ click <id> | type <id> <text> | scroll | scan | open <url> | list | quit')


# ==================== 入口 ====================

def main():
    print(BANNER)

    server = HTTPServer((HOST, PORT), BrainHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"  🌐 Server on http://{HOST}:{PORT}")
    print(f"     POST /scan          ← 插件上报页面数据")
    print(f"     POST /action_result ← 插件上报动作结果")
    print(f"     GET  /poll          ← 插件轮询获取指令")
    print()

    try:
        user_input_loop()
    except KeyboardInterrupt:
        print('\n👋 Bye!')

    server.shutdown()


if __name__ == '__main__':
    main()
