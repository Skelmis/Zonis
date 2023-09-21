import asyncio
import json
import logging
import secrets
import typing as t

import websockets
from websockets.legacy.client import WebSocketClientProtocol

from zonis import UnknownPacket, MissingReceiveHandler

log = logging.getLogger(__name__)
background_tasks: set[asyncio.Task] = set()


# TODO Consider back pressure via queue limits to avoid/alert on congestion?
class Router:
    """A router class for enabling two-way communication down a single pipe.

    This is built on the architecture ideals that if you want to send
    something down the pipe, then this class can return you the response
    just fine. However, if you wish to receive content for this class
    then you need to register an async method to handle that incoming data.
    """

    def __init__(self, url: str):
        self.__is_open: bool = True
        self._url: str = url
        self._ws_task: asyncio.Task | None = None
        self._receive_handler = None
        self._futures: dict[str, asyncio.Future] = {}
        self._send_queue: asyncio.Queue[tuple[asyncio.Future, dict]] = asyncio.Queue()

    async def connect(self) -> None:
        """A non-blocking call which connects the underlying WS."""
        self._ws_task = asyncio.create_task(self._handle_ws())
        background_tasks.add(self._ws_task)
        self._ws_task.add_done_callback(background_tasks.discard)

    async def send(self, data: dict) -> asyncio.Future:
        """Send data down the pipe.

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
        return future

    async def register_receiver(self, callback) -> None:
        """Register the provided callback to handle packets
        with the request type.

        Parameters
        ----------
        callback
            The callback to call with the packet data.
        """
        self._receive_handler = callback

    async def _handle_ws(self):
        """Handles the underlying websocket and distributed callouts."""
        async with websockets.connect(self._url) as websocket:
            websocket = t.cast(WebSocketClientProtocol, websocket)
            while self.__is_open:
                receive_task = asyncio.create_task(websocket.recv())
                queue_task = asyncio.create_task(self._send_queue.get())
                background_tasks.add(receive_task)
                background_tasks.add(queue_task)
                receive_task.add_done_callback(background_tasks.discard)
                queue_task.add_done_callback(background_tasks.discard)

                done, pending = await asyncio.wait(
                    [
                        receive_task,
                        queue_task,
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                result = done.pop().result()
                for future in pending:
                    future.cancel()

                if isinstance(result, tuple):
                    await self._dispatch_future(websocket, result[1])
                else:
                    await self._resolve_future(result)

    async def _dispatch_future(self, websocket: WebSocketClientProtocol, data: dict):
        """Given a future from the queue, send it down the pipe"""
        await websocket.send(data)

    async def _resolve_future(self, raw_packet: str | bytes):
        """Given a packet received on the pipe, resolve it's associated future"""
        packet: dict = json.loads(raw_packet)
        if "type" not in packet:
            log.debug("Failed to resolve packet type for %s", packet)
            raise UnknownPacket

        if "data" not in packet:
            log.debug(
                "Failed to resolve packet as it was missing the 'data' field: %s",
                packet,
            )
            raise UnknownPacket

        if packet["type"] == "response":
            if "packet_id" not in packet:
                raise UnknownPacket

            matching_future: asyncio.Future | None = self._futures.get(
                packet["packet_id"], None
            )
            if matching_future is None:
                raise UnknownPacket

            matching_future.set_result(packet["data"])

        else:
            # This is a request to propagate up to
            # the incoming request handler method
            if self._receive_handler is None:
                raise MissingReceiveHandler

            task = asyncio.create_task(self._receive_handler(packet["data"]))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
