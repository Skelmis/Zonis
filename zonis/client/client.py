import asyncio
import json
import logging
from typing import Optional, Literal, Callable, Dict, Any

import websockets
from websockets.exceptions import WebSocketException, ConnectionClosed

from zonis import Packet, DuplicateRoute
from zonis.packet import (
    custom_close_codes,
    RequestPacket,
    IdentifyDataPacket,
    IdentifyPacket,
)

log = logging.getLogger(__name__)

deferred_routes = {}


def route(route_name: Optional[str] = None):
    def decorator(func: Callable):
        name = route_name or func.__name__
        if name in deferred_routes:
            raise DuplicateRoute

        deferred_routes[name] = func
        return func

    return decorator


class Client:
    def __init__(
        self,
        *,
        url: str = "ws://localhost",
        port: Optional[int] = None,
        identifier: str = "DEFAULT",
        secret_key: str = "",
        override_key: Optional[str] = None,
    ):
        url = f"{url}:{port}" if port else url
        url = (
            f"ws://{url}"
            if not url.startswith("ws://") and not url.startswith("wss://")
            else url
        )
        self._url: str = url
        self.identifier: Optional[str] = identifier
        self._connection_future: asyncio.Future = asyncio.Future()

        self._secret_key: str = secret_key
        self._override_key: str = override_key
        self._routes: Dict[str, Callable] = {}
        self.__is_open: bool = True
        self.__current_ws = None
        self.__task: Optional[asyncio.Task] = None
        self._instance_mapping: Dict[str, Any] = {}

    def register_class_instance_for_routes(self, instance, *routes):
        for r in routes:
            self._instance_mapping[r] = instance

    def route(self, route_name: Optional[str] = None):
        def decorator(func: Callable):
            name = route_name or func.__name__
            if name in self._routes:
                raise DuplicateRoute

            self._routes[name] = func
            return func

        return decorator

    async def start(self):
        for k, v in deferred_routes.items():
            if k in self._routes:
                raise DuplicateRoute

            self._routes[k] = v

        self.__task = asyncio.create_task(self._connect())
        await self._connection_future
        log.info(
            "Successfully connected to the server with identifier %s",
            self.identifier,
        )

    async def close(self):
        if self.__current_ws:
            try:
                await self.__current_ws.close()
            except:
                pass

        if self.__task:
            try:
                self.__task.cancel()
            except:
                pass

        self._connection_future = asyncio.Future()
        log.info("Successfully closed the client")

    async def _connect(self):
        # Try reconnect up to 5 times in the process lifetime per startup
        for _ in range(5):
            try:
                async with websockets.connect(self._url) as websocket:
                    self.__current_ws = websocket
                    idp = IdentifyDataPacket(
                        secret_key=self._secret_key, override_key=self._override_key
                    )
                    await websocket.send(
                        json.dumps(
                            IdentifyPacket(
                                identifier=self.identifier, type="IDENTIFY", data=idp
                            )
                        )
                    )

                    while self.__is_open:
                        d = await websocket.recv()
                        packet: Packet = json.loads(d)
                        ws_type: Literal["IDENTIFY", "REQUEST"] = packet["type"]

                        log.debug("Received %s event", ws_type)
                        if ws_type == "IDENTIFY":
                            # We have successfully connected
                            self._connection_future.set_result(None)

                        elif ws_type == "REQUEST":
                            data: RequestPacket = packet["data"]
                            route_name = data["route"]
                            if route_name not in self._routes:
                                await websocket.send(
                                    json.dumps(
                                        Packet(
                                            identifier=self.identifier,
                                            type="FAILURE_RESPONSE",
                                            data=f"{route_name} is not a valid route name.",
                                        )
                                    )
                                )
                                continue

                            try:
                                if route_name in self._instance_mapping:
                                    result = await self._routes[route_name](
                                        self._instance_mapping[route_name],
                                        **data["arguments"],
                                    )
                                else:
                                    result = await self._routes[route_name](
                                        **data["arguments"]
                                    )
                                await websocket.send(
                                    json.dumps(
                                        Packet(
                                            identifier=self.identifier,
                                            type="SUCCESS_RESPONSE",
                                            data=result,
                                        )
                                    )
                                )
                            except Exception as e:
                                await websocket.send(
                                    json.dumps(
                                        Packet(
                                            identifier=self.identifier,
                                            type="FAILURE_RESPONSE",
                                            data=str(e),
                                        )
                                    )
                                )
                                log.error("%s", e)

                        else:
                            log.warning("Received unhandled event %s", ws_type)
            except ConnectionClosed as e:
                code: int = e.code
                if code in custom_close_codes:
                    raise custom_close_codes[code] from e

                raise e
            except WebSocketException:
                raise
            finally:
                self._connection_future = asyncio.Future()

        # We are closing
        self._connection_future = asyncio.Future()
