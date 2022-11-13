import json
from typing import Dict, Literal, Any

from zonis import Packet, UnknownClient, RequestFailed, BaseZonisException
from zonis.packet import RequestPacket


class Server:
    def __init__(self, *, using_fastapi_websockets: bool = False):
        self._connections = {}
        self.using_fastapi_websockets: bool = using_fastapi_websockets

    def disconnect(self, identifier: str):
        self._connections.pop(identifier, None)

    async def _send(self, content: str, conn):
        if self.using_fastapi_websockets:
            await conn.send_text(content)
        else:
            await conn.send(content)

    async def _recv(self, conn) -> str:
        if self.using_fastapi_websockets:
            from starlette.websockets import WebSocketDisconnect

            try:
                return await conn.receive_text()
            except WebSocketDisconnect:
                raise RequestFailed("Websocket disconnected while waiting for receive.")

        return await conn.recv()

    async def request(
        self, route: str, *, client_identifier: str = "DEFAULT", **kwargs
    ):
        conn = self._connections.get(client_identifier)
        if not conn:
            raise UnknownClient

        await self._send(
            json.dumps(
                Packet(
                    identifier=client_identifier,
                    type="REQUEST",
                    data=RequestPacket(route=route, arguments=kwargs),
                )
            ),
            conn,
        )
        d = await self._recv(conn)
        packet: Packet = json.loads(d)
        if packet["type"] == "FAILURE_RESPONSE":
            raise RequestFailed(packet["data"])

        return packet["data"]

    async def request_all(self, route: str, **kwargs) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        for i, conn in self._connections.items():
            await self._send(
                json.dumps(
                    Packet(
                        identifier=i,
                        type="REQUEST",
                        data=RequestPacket(route=route, arguments=kwargs),
                    )
                ),
                conn,
            )
            d = await self._recv(conn)
            packet: Packet = json.loads(d)
            if packet["type"] == "FAILURE_RESPONSE":
                results[i] = RequestFailed(packet["data"])

            results[i] = packet["data"]

        return results

    async def parse_identify(self, packet: Packet, websocket) -> str:
        identifier: str = packet["identifier"]
        ws_type: Literal["IDENTIFY"] = packet["type"]
        if ws_type != "IDENTIFY":
            await websocket.close(
                code=3001, reason=f"Expected IDENTIFY, received {ws_type}"
            )
            raise BaseZonisException("Identify failed.")

        if identifier in self._connections:
            await websocket.close(code=3000, reason="Duplicate identifier on IDENTIFY")
            raise BaseZonisException("Identify failed.")

        self._connections[identifier] = websocket
        await self._send(
            json.dumps(Packet(identifier=identifier, type="IDENTIFY", data=None)),
            websocket,
        )
        return identifier
