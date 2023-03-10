import json
import logging
import secrets
import traceback
from typing import Dict, Literal, Any, cast, Optional

from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from zonis import (
    Packet,
    UnknownClient,
    RequestFailed,
    BaseZonisException,
    DuplicateConnection,
)
from zonis.packet import RequestPacket, IdentifyPacket

log = logging.getLogger(__name__)


class Server:
    """
    Parameters
    ----------
    using_fastapi_websockets: :class:`bool`
        Defaults to ``False``.
    override_key: Optional[:class:`str`]
    secret_key: :class:`str`
        Defaults to an emptry string.
    """

    def __init__(
        self,
        *,
        using_fastapi_websockets: bool = False,
        override_key: Optional[str] = None,
        secret_key: str = "",
    ) -> None:
        self._connections = {}
        self._secret_key: str = secret_key
        self._override_key: Optional[str] = (
            override_key if override_key is not None else secrets.token_hex(64)
        )
        self.using_fastapi_websockets: bool = using_fastapi_websockets

    def disconnect(self, identifier: str) -> None:
        """Disconnect a client connection.

        Parameters
        ----------
        identifier: str
            The client identifier to disconnect

        Notes
        -----
        This doesn't yet tell the client to stop
        gracefully, this just removes it from our store.

        Warnings
        --------
        This doesn't yet actually close the WS.
        """
        self._connections.pop(identifier, None)

    async def _send(self, content: str, conn) -> None:
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
    ) -> Any:
        """Make a request to the provided IPC client.

        Parameters
        ----------
        route: str
            The IPC route to call.
        client_identifier: Optional[str]
            The client to make a request to.

            This only applies in many to one setups
            or if you changed the default identifier.
        kwargs
            All the arguments you wish to invoke the IPC route with.

        Returns
        -------
        Any
            The data the IPC route returned.

        Raises
        ------
        RequestFailed
            The IPC request failed.
        """
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
        """Issue a request to connected IPC clients.

        Parameters
        ----------
        route: str
            The IPC route to call.
        kwargs
            All the arguments you wish to invoke the IPC route with.

        Returns
        -------
        Dict[str, Any]
            A dictionary where the keys are the client
            identifiers and the values are the returned data.

            The data could also be an instance of :py:class:RequestFailed:
        """
        results: Dict[str, Any] = {}

        for i, conn in self._connections.items():
            try:
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
                else:
                    results[i] = packet["data"]
            except ConnectionClosedOK as e:
                results[i] = RequestFailed("Connection Closed")
                log.error(
                    "request_all connection closed: %s, %s",
                    i,
                    "".join(traceback.format_exception(e)),
                )
            except ConnectionClosedError as e:
                results[i] = RequestFailed(
                    f"Connection closed with error: {e.code}|{e.reason}"
                )
                log.error(
                    "request_all connection closed with error: %s, %s",
                    i,
                    "".join(traceback.format_exception(e)),
                )
            except Exception as e:
                results[i] = RequestFailed("Request failed.")
                log.error(
                    "request_all connection threw: %s, %s",
                    i,
                    "".join(traceback.format_exception(e)),
                )

        return results

    async def parse_identify(self, packet: Packet, websocket) -> str:
        """Parse a packet to establish a new valid client connection.

        Parameters
        ----------
        packet: Packet
            The packet to read
        websocket
            The websocket this connection is using

        Returns
        -------
        str
            The established clients identifier

        Raises
        ------
        BaseZonisException
            Unexpected WS issue
        DuplicateConnection
            Duplicate connection without override keys
        """
        try:
            identifier: str = packet.get("identifier")
            ws_type: Literal["IDENTIFY"] = packet["type"]
            if ws_type != "IDENTIFY":
                await websocket.close(
                    code=4101, reason=f"Expected IDENTIFY, received {ws_type}"
                )
                raise BaseZonisException(
                    f"Unexpected ws response type, expected IDENTIFY, received {ws_type}"
                )

            packet: IdentifyPacket = cast(IdentifyPacket, packet)
            secret_key = packet["data"]["secret_key"]
            if secret_key != self._secret_key:
                await websocket.close(code=4100, reason=f"Invalid secret key.")
                raise BaseZonisException(
                    f"Client attempted to connect with an incorrect secret key."
                )

            override_key = packet["data"].get("override_key")
            if identifier in self._connections and (
                not override_key or override_key != self._override_key
            ):
                await websocket.close(
                    code=4102, reason="Duplicate identifier on IDENTIFY"
                )
                raise DuplicateConnection("Identify failed.")

            self._connections[identifier] = websocket
            await self._send(
                json.dumps(Packet(identifier=identifier, type="IDENTIFY", data=None)),
                websocket,
            )
            return identifier
        except Exception as e:
            raise BaseZonisException("Identify failed") from e
