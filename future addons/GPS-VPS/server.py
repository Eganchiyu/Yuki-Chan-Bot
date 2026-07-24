import asyncio
import websockets
from websockets.exceptions import ConnectionClosed

HOST = "0.0.0.0"
PORT = 8765

clients = set()


async def broadcast(sender, message):
    targets = [client for client in clients if client is not sender]
    if not targets:
        print("[FORWARD] 当前没有其他客户端，消息未转发")
        return

    print(f"[FORWARD] 向 {len(targets)} 个客户端转发消息: {message}")
    results = await asyncio.gather(
        *(client.send(message) for client in targets),
        return_exceptions=True,
    )

    for client, result in zip(targets, results):
        if isinstance(result, Exception):
            print(f"[ERROR] 转发失败，移除客户端 {client.remote_address}: {result}")
            clients.discard(client)


async def handler(websocket, path=None):
    clients.add(websocket)
    print(f"[CONNECT] 客户端已连接: {websocket.remote_address}，当前连接数: {len(clients)}")

    try:
        async for message in websocket:
            print(f"[RECEIVE] 来自 {websocket.remote_address}: {message}")
            await broadcast(websocket, message)
    except ConnectionClosed as exc:
        print(f"[DISCONNECT] 客户端异常断开: {websocket.remote_address}，code={exc.code}, reason={exc.reason}")
    except Exception as exc:
        print(f"[ERROR] 客户端处理异常: {websocket.remote_address}: {exc}")
    finally:
        clients.discard(websocket)
        print(f"[CLEANUP] 客户端已移除: {websocket.remote_address}，当前连接数: {len(clients)}")


async def main():
    print(f"[START] WebSocket 中转服务器启动 ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[STOP] 服务器已停止")
