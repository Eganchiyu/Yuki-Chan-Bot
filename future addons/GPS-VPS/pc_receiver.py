import asyncio
import json
import websockets
from websockets.exceptions import ConnectionClosed

SERVER_URL = "ws://8.217.41.28:8765"
RECONNECT_DELAY = 5


async def receive_locations() -> None:
    while True:
        try:
            print(f"[CONNECT] 正在连接服务器: {SERVER_URL}")
            async with websockets.connect(SERVER_URL) as websocket:
                print("[CONNECTED] 已连接服务器，开始监听位置数据")

                async for message in websocket:
                    try:
                        data = json.loads(message)
                        longitude = data.get("longitude")
                        latitude = data.get("latitude")
                        timestamp = data.get("timestamp")

                        print("[LOCATION] "
                              f"longitude={longitude}, "
                              f"latitude={latitude}, "
                              f"timestamp={timestamp}")
                    except json.JSONDecodeError:
                        print(f"[WARN] 收到非 JSON 消息: {message}")
                    except Exception as exc:
                        print(f"[ERROR] 解析消息失败: {exc}，原始消息: {message}")
        except ConnectionClosed as exc:
            print(f"[DISCONNECTED] 连接断开，code={exc.code}, reason={exc.reason}")
        except OSError as exc:
            print(f"[ERROR] 无法连接服务器: {exc}")
        except Exception as exc:
            print(f"[ERROR] 接收端异常: {exc}")

        print(f"[RECONNECT] {RECONNECT_DELAY} 秒后重连")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(receive_locations())
    except KeyboardInterrupt:
        print("\n[STOP] 接收端已停止")
