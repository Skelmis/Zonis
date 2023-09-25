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

from zonis import UnknownPacket, MissingReceiveHandler, util
from zonis.packet import IdentifyPacket, IdentifyDataPacket

log = logging.getLogger(__name__)


class PacketT(t.TypedDict):
    packet_id: str
    type: t.Literal["request", "response"]
    data: dict


# TODO Consider back pressure via queue limits to avoid/alert on congestion?
# TODO Make program clean exit on Ctrl + C
class Router:
    """A router class for enabling two-way communication down a single pipe.

    This is built on the architecture ideals that if you want to send
    something down the pipe, then this class can return you the response
    just fine. However, if you wish to receive content for this class
    then you need to register an async method to handle that incoming data
    as this class doesn't have the context required to handle it.
    """

    def __init__(self, identifier: str, *, using_fastapi_websockets: bool = False):
        self.__is_open: bool = True
        self._ws_task: asyncio.Task | None = None
        self._receive_handler = None
        self.identifier: str = identifier
        self._futures: dict[str, asyncio.Future] = {}
        # TODO These queues can all likely become one and just use
        #      a dict to store relevant metadata? Or named tuple
        self._response_queue: asyncio.Queue[tuple[None, dict]] = asyncio.Queue()
        self._send_queue: asyncio.Queue[tuple[asyncio.Future, dict]] = asyncio.Queue()
        self._connection_future: asyncio.Future | None = None
        self._close_future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._using_fastapi_websockets: bool = using_fastapi_websockets

    async def connect_client(self, url: str, idp: IdentifyDataPacket) -> None:
        """A non-blocking call which connects the underlying WS."""
        self._connection_future = asyncio.Future()
        self._ws_task = util.create_task(self._handle_ws(url, idp))

        # TODO Handle IDENTIFY packets coming in
        #      and ensure this method doesnt return
        #      until the underlying ws is ready
        await self._connection_future

    async def connect_server(self, websocket) -> None:
        self._ws_task = util.create_task(self._handle_pipe(websocket))

    async def close(self) -> None:
        """Close the underlying WS"""
        self._close_future.set_result("CLOSE_FUTURE")

        # Let the event loop close the task by giving
        # back control for a no-op
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
        packet_id = secrets.token_bytes(32).hex()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._futures[packet_id] = future
        self._send_queue.put_nowait(
            (
                future,
                {"packet_id": packet_id, "type": "request", "data": data},
            )
        )
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
        self._response_queue.put_nowait((None, packet))
        log.debug("Queued item to send as a response for packet %s", packet_id)

    def register_receiver(self, callback) -> Router:
        """Register the provided callback to handle packets
        with the request type.

        Parameters
        ----------
        callback
            The callback to call with the packet data.
        """
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
            # ping_timeout=10000,
        ):
            try:
                websocket = t.cast(WebSocketClientProtocol, websocket)
                util.create_task(self._handle_client_identify(idp))
                log.debug("Websocket opened to %s", url)

                # This method seemingly doesn't block as a result
                # of it's implementation and thus we require
                # the following in order to maintain the websocket
                await self._handle_pipe(websocket)

                await self._close_future
            except Exception as error:
                log.critical("%s", "".join(traceback.format_exception(error)))
            finally:
                await self._wait_for_close()
                log.error("Doing stuff")

        log.critical("Closing IDK")

    async def _wait_for_close(self):
        """An awaitable that blocks until the connection should be closed.

        Used over directly awaiting a Future as it can't be a
        coro using in create_task...

        Even better, if you cancel this task which
        is waiting for this then the whole thing fucking
        falls apart and breaks and I don't know why
        """
        # TODO Figure out how to make closing WS work
        #      / exiting on close. Thinking special queue item?
        await self._close_future

    async def _handle_pipe(self, websocket):
        try:
            while self.__is_open:
                if self._using_fastapi_websockets:
                    receive_task = util.create_task(websocket.receive_text())
                else:
                    receive_task = util.create_task(websocket.recv())
                queue_task = util.create_task(self._send_queue.get())
                response_task = util.create_task(self._response_queue.get())
                # close_task = util.create_task(self._wait_for_close())

                done, pending = await asyncio.wait(
                    [
                        receive_task,
                        queue_task,
                        response_task,
                        # close_task,
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                result = done.pop().result()
                for future in pending:
                    log.info("About to cancel %s", future)
                    future.cancel()

                if result == "CLOSE_FUTURE":
                    # Kill the connection
                    self.__is_open = False
                    log.debug("Closing WS connection")
                    continue

                if isinstance(result, tuple):
                    log.debug("> Sending request down the pipe")
                    await self._dispatch_future(websocket, result[1])
                else:
                    log.debug("< Handling response from up stream")
                    await self._resolve_future(result)
        except Exception as error:
            log.critical("%s", "".join(traceback.format_exception(error)))

        print("Pipe closing")

    async def _dispatch_future(self, websocket: WebSocketClientProtocol, data: dict):
        """Given a future from the queue, send it down the pipe"""
        if self._using_fastapi_websockets:
            await websocket.send_text(json.dumps(data))
        else:
            await websocket.send(json.dumps(data))

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
            matching_future: asyncio.Future | None = self._futures.get(packet_id, None)
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
                )
            )
