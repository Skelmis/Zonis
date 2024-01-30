from __future__ import annotations

import asyncio
import json
import logging
import secrets
import traceback
import typing as t
from functools import partial

import websockets.client
from websockets.legacy.client import WebSocketClientProtocol

from zonis import (
    UnknownPacket,
    MissingReceiveHandler,
    util,
    WebsocketProtocol,
    Websockets,
)
from zonis.packet import IdentifyPacket, IdentifyDataPacket

log = logging.getLogger(__name__)


class PacketT(t.TypedDict):
    packet_id: str
    type: t.Literal["request", "response"]
    data: dict


class Router:
    """A router class for enabling two-way communication down a single pipe.

    This is built on the architecture ideals that if you want to send
    something down the pipe, then this class can return you the response
    just fine. However, if you wish to receive content for this class
    then you need to register an async method to handle that incoming data
    as this class doesn't have the context required to handle it.
    """

    _EXIT_LITERAL: t.Final = "CLOSE_FUTURE"

    def __init__(
        self,
        identifier: str,
        websocket_connection: WebsocketProtocol | None,
        *,
        retry_on_exception: bool = True,
        max_retries: int = 3,
        default_client_websocket_factory: t.Type[WebsocketProtocol] = Websockets
    ):
        """

        Parameters
        ----------
        identifier: str
            How this connection identifies itself.
        websocket_connection: WebsocketProtocol
            An implementation of the websocket protocol.

            At this stage this only affects the Server,
            Client's will always use Websockets
        retry_on_exception: bool
            On failure, give it another go
        max_retries: int
            Max times to retry on exception

        Warnings
        --------
        websocket_connection should **only ever** be
        None when called from Client. If you ever use this,
        ensure it is passed or set before first usage.
        """
        self._websocket_connection: WebsocketProtocol | None = websocket_connection
        self._default_client_websocket_factory: t.Type[
            WebsocketProtocol
        ] = default_client_websocket_factory
        self._retry_on_exception: bool = retry_on_exception
        self._max_retries: int = max_retries
        self._attempted_connection_count: int = 0
        self.__url: str | None = None
        self.__is_open: bool = True
        self._ws_task: asyncio.Task | None = None
        self._receive_handler = None
        self.identifier: str = identifier
        self._router_id: str = secrets.token_bytes(32).hex()
        self._futures: dict[str, asyncio.Future] = {}
        self._item_queue: asyncio.Queue[
            tuple[t.Literal["SEND_THEN_RECEIVE_RESPONSE"], dict]
            | tuple[t.Literal["SEND_RESPONSE"], dict]
            | tuple[t.Literal["CLOSE_FUTURE"]],
        ] = asyncio.Queue()
        self._connection_future: asyncio.Future | None = None
        self._block_future: asyncio.Future = asyncio.Future()
        self._receive_from_queue_task: asyncio.Task | None = None
        self._receive_from_ws_task: asyncio.Task | None = None

    async def block_until_closed(self):
        """A blocking call which releases when the WS closes.

        Notes
        -----
        This will block even if the
        underlying WS has yet to connect.
        """
        await self._block_future

    async def connect_client(self, url: str, idp: IdentifyDataPacket) -> None:
        """A blocking call which connects the underlying WS."""
        log.debug("Initiating connection to %s with identity %s", url, idp)
        self._connection_future = asyncio.Future()
        self.__url = url
        self._ws_task = util.create_task(
            self._handle_ws(url, idp), router_id=self._router_id
        )

        await self._connection_future

    async def connect_server(self) -> None:
        self._ws_task = util.create_task(self._handle_pipe(), router_id=self._router_id)

    async def close(self) -> None:
        """Close the underlying WS"""
        log.debug("Closing WS connection to %s", self.__url)
        self._item_queue.put_nowait((self._EXIT_LITERAL,))  # type: ignore
        self._check_for_congestion()

        # Let the event loop close the task by giving
        # back control for a no-op. Not sure if this
        # actually then kills the task or not but whatever
        await asyncio.sleep(0)

    async def send(self, data: dict) -> asyncio.Future:
        """Send data down the pipe and receive a response.

        Parameters
        ----------
        data: dict
            The packet to send down the pipe

        Returns
        -------
        asyncio.Future
            This future will contain the returned data
            once it becomes available
        """
        packet_id = secrets.token_bytes(16).hex()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._futures[packet_id] = future
        self._item_queue.put_nowait(
            (
                "SEND_THEN_RECEIVE_RESPONSE",
                {"packet_id": packet_id, "type": "request", "data": data},
            )
        )
        self._check_for_congestion()
        log.debug("Queued item to send as a request for packet %s", packet_id)
        return future

    async def send_response(self, *, packet_id: str, data: dict | None = None):
        """Sends a response to a received request without waiting anything.

        Parameters
        ----------
        packet_id: str
            The packet ID to respond to
        data: dict
            The data being responded with
        """
        if data is None:
            data = {}

        packet: PacketT = {"type": "response", "packet_id": packet_id, "data": data}
        self._item_queue.put_nowait(("SEND_RESPONSE", packet))
        self._check_for_congestion()
        log.debug("Queued item to send as a response for packet %s", packet_id)

    def register_receiver(self, callback) -> Router:
        """Register the provided callback to handle packets
        with the request type.

        Parameters
        ----------
        callback
            The callback to call with the packet data.
        """
        if self._receive_handler is not None:
            log.debug("Router overriding existing receive handler")

        self._receive_handler = callback
        return self

    async def _handle_client_identify(self, idp):
        future = await self.send(
            IdentifyPacket(identifier=self.identifier, type="IDENTIFY", data=idp)
        )
        await future
        self._connection_future.set_result(None)

    async def _handle_ws(self, url, idp):
        """Handles the underlying websocket and distributed callouts.

        This method is called from clients.
        """
        async for websocket in websockets.client.connect(
            url,
            ping_timeout=100000,
        ):
            try:
                websocket = t.cast(WebSocketClientProtocol, websocket)
                self._websocket_connection = self._default_client_websocket_factory(
                    websocket
                )
                # This is a task because sending is done within _handle_pipe
                util.create_task(
                    self._handle_client_identify(idp), router_id=self._router_id
                )
                log.debug("Websocket opened to %s", url)

                result = await self._handle_pipe()
                if result is not None and result == self._EXIT_LITERAL:
                    break

            except Exception as error:
                log.critical("%s", "".join(traceback.format_exception(error)))
            finally:
                self._attempted_connection_count += 1
                if (
                    self._retry_on_exception
                    and self._max_retries < self._attempted_connection_count
                ):
                    log.critical("Exceeded maximum websocket reconnections, exiting...")
                    break

        self._block_future.set_result(None)

    def _ensure_tasks_exist(self):
        if self._receive_from_ws_task is None:
            self._receive_from_ws_task = util.create_task(
                self._websocket_connection.receive(), router_id=self._router_id
            )

        if self._receive_from_queue_task is None:
            self._receive_from_queue_task = util.create_task(
                self._item_queue.get(), router_id=self._router_id
            )

    async def _handle_pipe(self):
        try:
            while self.__is_open:
                self._ensure_tasks_exist()

                done, pending = await asyncio.wait(  # noqa
                    [self._receive_from_ws_task, self._receive_from_queue_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                result = done.pop().result()
                if not isinstance(result, tuple):
                    log.debug("< Processing incoming websocket message")
                    # This has been received from the WS
                    self._receive_from_ws_task = None
                    await self._resolve_future(result)
                    continue

                self._receive_from_queue_task = None
                if result[0] == self._EXIT_LITERAL:
                    # Kill the ws connection
                    self._receive_from_ws_task = None

                    self.__is_open = False
                    log.debug("Closing WS connection to %s", self.__url)
                    return self._EXIT_LITERAL

                elif result[0] == "SEND_RESPONSE":
                    log.debug("> Sending response to existing request")
                    await self._dispatch_future(result[1])

                elif result[0] == "SEND_THEN_RECEIVE_RESPONSE":
                    log.debug("> Sending request pending future response")
                    await self._dispatch_future(result[1])

                else:
                    log.critical("Unhandled result: %s", result)
        except Exception as error:
            log.critical("%s", "".join(traceback.format_exception(error)))

    async def _dispatch_future(self, data: dict):
        """Given a future from the queue, send it down the pipe"""
        if "packet_id" not in data:
            log.debug("Failed to resolve send packet as it was missing an id: %s", data)
            raise UnknownPacket

        packet_id = data["packet_id"]
        log.debug("> Sending packet %s", packet_id)
        await self._websocket_connection.send(json.dumps(data))

    async def _resolve_future(self, raw_packet: str | bytes | dict):
        """Given a packet received on the pipe, resolve it's associated future"""
        if isinstance(raw_packet, dict):
            packet: PacketT = raw_packet
        else:
            packet: PacketT = json.loads(raw_packet)

        if "type" not in packet:
            log.debug("Failed to resolve packet type for %s", packet)
            raise UnknownPacket

        if "data" not in packet:
            log.debug(
                "Failed to resolve packet as it was missing the 'data' field: %s",
                packet,
            )
            raise UnknownPacket

        if "packet_id" not in packet:
            log.debug("Failed to resolve packet as it was missing an id: %s", packet)
            raise UnknownPacket

        packet_id = packet["packet_id"]
        packet_data = packet["data"]

        if packet["type"] == "response":
            matching_future: asyncio.Future | None = self._futures.pop(packet_id, None)
            if matching_future is None:
                raise UnknownPacket

            matching_future.set_result(packet_data)

        else:
            # This is a request to propagate up to
            # the incoming request handler method
            if self._receive_handler is None:
                raise MissingReceiveHandler

            # Give the callee the incoming data
            # and function to call to return a response
            util.create_task(
                self._receive_handler(
                    packet_data,
                    partial(self.send_response, packet_id=packet["packet_id"]),
                ),
                router_id=self._router_id,
            )

    def _check_for_congestion(self):
        """Checks if the queue appears congested and alerts"""
        # 50 is an arb number I picked out of thin air
        # Would love feedback on this size if it affects you a lot
        if self._item_queue.qsize() > 50:
            log.warning("Router queue size is over 50, possible congestion detected")
