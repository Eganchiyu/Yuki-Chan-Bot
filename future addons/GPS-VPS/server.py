import asyncio
import json
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed

HOST = "0.0.0.0"
PORT = 8765

clients = set()
latest_location_message = None
latest_location_received_at = None


def is_location_message(message):
    try:
        data = json.loads(message)
    except ValueError:
        return False
    return isinstance(data, dict) and "longitude" in data and "latitude" in data


def record_latest_location(message):
    global latest_location_message, latest_location_received_at
    if not is_location_message(message):
        return False
    latest_location_message = message
    latest_location_received_at = datetime.now(timezone.utc).isoformat()
    return True


async def send_latest_location(websocket):
    if latest_location_message is None:
        return
    await websocket.send(latest_location_message)
    print(
        "[CACHE] sent latest location to {0}, cached_at={1}".format(
            websocket.remote_address,
            latest_location_received_at,
        )
    )


async def broadcast(sender, message):
    targets = [client for client in clients if client is not sender]
    if not targets:
        print("[FORWARD] no other clients, message cached only")
        return

    print("[FORWARD] forwarding to {0} clients: {1}".format(len(targets), message))
    results = await asyncio.gather(
        *(client.send(message) for client in targets),
        return_exceptions=True,
    )

    for client, result in zip(targets, results):
        if isinstance(result, Exception):
            print("[ERROR] forward failed, remove client {0}: {1}".format(
                client.remote_address,
                result,
            ))
            clients.discard(client)


async def handler(websocket, path=None):
    clients.add(websocket)
    print("[CONNECT] client connected: {0}, clients={1}".format(
        websocket.remote_address,
        len(clients),
    ))

    try:
        await send_latest_location(websocket)
        async for message in websocket:
            cached = record_latest_location(message)
            print("[RECEIVE] from {0}: {1}, cached={2}".format(
                websocket.remote_address,
                message,
                cached,
            ))
            await broadcast(websocket, message)
    except ConnectionClosed as exc:
        print("[DISCONNECT] client disconnected: {0}, code={1}, reason={2}".format(
            websocket.remote_address,
            exc.code,
            exc.reason,
        ))
    except Exception as exc:
        print("[ERROR] client handler failed: {0}: {1}".format(
            websocket.remote_address,
            exc,
        ))
    finally:
        clients.discard(websocket)
        print("[CLEANUP] client removed: {0}, clients={1}".format(
            websocket.remote_address,
            len(clients),
        ))


async def main():
    print("[START] GPS-VPS WebSocket relay started ws://{0}:{1}".format(HOST, PORT))
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[STOP] server stopped")
