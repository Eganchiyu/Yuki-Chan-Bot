import asyncio
import json
import random
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed

SERVER_URL = "ws://8.217.41.28:8765"
SEND_INTERVAL = 3
BASE_LONGITUDE = 114.1694
BASE_LATITUDE = 22.3193


def generate_location() -> dict:
    longitude = BASE_LONGITUDE + random.uniform(-0.01, 0.01)
    latitude = BASE_LATITUDE + random.uniform(-0.01, 0.01)

    return {
        "longitude": round(longitude, 6),
        "latitude": round(latitude, 6),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def send_locations() -> None:
    while True:
        try:
            print(f"[CONNECT] 正在连接服务器: {SERVER_URL}")
            async with websockets.connect(SERVER_URL) as websocket:
                print("[CONNECTED] 已连接服务器，开始发送模拟 GPS 数据")

                while True:
                    location = generate_location()
                    message = json.dumps(location, ensure_ascii=False)
                    await websocket.send(message)
                    print(f"[SEND] {message}")
                    await asyncio.sleep(SEND_INTERVAL)
        except ConnectionClosed as exc:
            print(f"[DISCONNECTED] 连接断开，code={exc.code}, reason={exc.reason}")
        except OSError as exc:
            print(f"[ERROR] 无法连接服务器: {exc}")
        except Exception as exc:
            print(f"[ERROR] 发送端异常: {exc}")

        print("[RECONNECT] 5 秒后重连")
        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(send_locations())
    except KeyboardInterrupt:
        print("\n[STOP] 模拟发送端已停止")
