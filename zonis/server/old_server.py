import asyncio
import json
from typing import Dict, Literal, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.legacy.server import WebSocketServerProtocol

from zonis import Packet, UnknownClient, RequestFailed
from zonis.packet import custom_close_codes, RequestPacket


class Server:
    def __init__(self, *, url: str = "localhost", port: int = 5678):
        self._url: str = url
        self._port: int = port
        self._connections: Dict[str, WebSocketServerProtocol] = {}

    async def request(
        self, route: str, *, client_identifier: str = "DEFAULT", **kwargs
    ):
        conn: Optional[WebSocketServerProtocol] = self._connections.get(route)
        if not conn:
            raise UnknownClient

        await conn.send(
            json.dumps(
                Packet(
                    identifier=client_identifier,
                    type="REQUEST",
                    data=RequestPacket(route=route, arguments=kwargs),
                )
            )
        )
        d = await conn.recv()
        packet: Packet = json.loads(d)
        if packet["type"] == "FAILURE_RESPONSE":
            raise RequestFailed(packet["data"])

        return packet["data"]

    async def start(self):
        asyncio.create_task(self._start())
        # await self._start()

    async def _start(self):
        try:
            async with websockets.serve(self._run_connection, self._url, self._port):
                await asyncio.Future()
        except Exception as e:
            print(e)

    async def _run_connection(self, websocket: WebSocketServerProtocol):
        identifier: Optional[str] = None
        try:
            d = await websocket.recv()
            packet: Packet = json.loads(d)
            identifier: str = packet["identifier"]
            ws_type: Literal["IDENTIFY"] = packet["type"]
            if ws_type != "IDENTIFY":
                await websocket.close(
                    code=3001, reason=f"Expected IDENTIFY, received {ws_type}"
                )
                return

            if identifier in self._connections:
                await websocket.close(
                    code=3000, reason="Duplicate identifier on IDENTIFY"
                )
                return

            await websocket.send(
                json.dumps(Packet(identifier=identifier, type="IDENTIFY", data=None))
            )
            await websocket.wait_closed()
        except ConnectionClosed as e:
            self._connections.pop(identifier, None)
            code: int = e.code
            if code in custom_close_codes:
                raise custom_close_codes[code] from e

            raise e
        except WebSocketException:
            raise
