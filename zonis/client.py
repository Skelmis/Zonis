import asyncio
import json
import logging
from typing import Optional, Literal, Callable, Dict, Any

import websockets
from websockets.exceptions import WebSocketException, ConnectionClosed

from zonis import Packet, DuplicateRoute, Router
from zonis.packet import (
    custom_close_codes,
    RequestPacket,
    IdentifyDataPacket,
    IdentifyPacket,
    ClientToServerPacket,
)

log = logging.getLogger(__name__)
deferred_routes = {}


# Modified from https://stackoverflow.com/a/55185488
async def exception_aware_scheduler(
    callee,
    *args,
    retry_count: int = 1,
    **kwargs,
):
    for _ in range(retry_count):
        done, pending = await asyncio.wait(
            [asyncio.create_task(callee(*args, **kwargs))],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in done:
            if task.exception() is not None:
                log.error("Task exited with exception:")
                task.print_stack()


def route(route_name: Optional[str] = None):
    """Turn an async function into a valid IPC route.

    Parameters
    ----------
    route_name: Optional[str]
        An optional name for this IPC route,
        defaults to the name of the function.

    Raises
    ------
    DuplicateRoute
        A route with this name already exists
    """

    def decorator(func: Callable):
        name = route_name or func.__name__
        if name in deferred_routes:
            raise DuplicateRoute

        deferred_routes[name] = func
        return func

    return decorator


class Client:
    """
    Parameters
    ----------
    reconnect_attempt_count: :class:`int`
        The number of times that the :class:`Client` should
        attempt to reconnect.
    url: :class:`str`
        Defaults to ``ws://localhost``.
    port: Optional[:class:`int`]
        The port that the :class:`Client` should use.
    """

    def __init__(
        self,
        *,
        reconnect_attempt_count: int = 1,
        url: str = "ws://localhost",
        port: Optional[int] = None,
        identifier: str = "DEFAULT",
        secret_key: str = "",
        override_key: Optional[str] = None,
    ) -> None:
        url = f"{url}:{port}" if port else url
        url = (
            f"ws://{url}"
            if not url.startswith("ws://") and not url.startswith("wss://")
            else url
        )
        self._url: str = url
        self.identifier: str = identifier
        self._reconnect_attempt_count: int = reconnect_attempt_count
        self._connection_future: asyncio.Future = asyncio.Future()

        self._secret_key: str = secret_key
        self._override_key: str = override_key
        self._routes: Dict[str, Callable] = {}
        self.__is_open: bool = True
        self.__current_ws = None
        self.__task: Optional[asyncio.Task] = None
        self._instance_mapping: Dict[str, Any] = {}

        self.router: Router = Router(self.identifier).register_receiver(
            self._request_handler
        )

    def register_class_instance_for_routes(self, instance, *routes) -> None:
        """Register a class instance for the given route.

        When you turn a method on a class into an IPC route,
        you need to call this method with the instance of the class
        to use as well as the names of the routes for registration to work correctly.

        Parameters
        ----------
        instance
            The class instance the methods live on
        routes
            A list of strings representing the names
            of the IPC routes for this class.
        """
        for r in routes:
            self._instance_mapping[r] = instance

    def route(self, route_name: Optional[str] = None):
        """Turn an async function into a valid IPC route.

        Parameters
        ----------
        route_name: Optional[str]
            An optional name for this IPC route,
            defaults to the name of the function.

        Raises
        ------
        DuplicateRoute
            A route with this name already exists

        Notes
        -----
        If this is a method on a class, you will also
        need to use the ``register_class_instance_for_routes``
        method for this to work as an IPC route.
        """

        def decorator(func: Callable):
            name = route_name or func.__name__
            if name in self._routes:
                raise DuplicateRoute

            self._routes[name] = func
            return func

        return decorator

    def load_routes(self) -> None:
        """Loads all decorated routes."""
        global deferred_routes
        for k, v in deferred_routes.items():
            if k in self._routes:
                raise DuplicateRoute

            self._routes[k] = v
        deferred_routes = {}

    async def start(self) -> None:
        """Start the IPC client."""
        self.load_routes()
        await self.router.connect_client(
            self._url,
            idp=IdentifyDataPacket(
                secret_key=self._secret_key, override_key=self._override_key
            ),
        )
        log.info(
            "Successfully connected to the server with identifier %s",
            self.identifier,
        )

    async def close(self) -> None:
        """Stop the IPC client."""
        await self.router.close()
        log.info("Successfully closed the client")

    async def _request_handler(self, packet_data, resolution_handler):
        data: RequestPacket = packet_data["data"]
        route_name = data["route"]
        if route_name not in self._routes:
            await resolution_handler(
                data=Packet(
                    identifier=self.identifier,
                    type="FAILURE_RESPONSE",
                    data=f"{route_name} is not a valid route name.",
                )
            )
            return

        if route_name in self._instance_mapping:
            result = await self._routes[route_name](
                self._instance_mapping[route_name],
                **data["arguments"],
            )
        else:
            result = await self._routes[route_name](**data["arguments"])

        await resolution_handler(
            data=Packet(
                identifier=self.identifier,
                type="SUCCESS_RESPONSE",
                data=result,
            )
        )

    async def request(self, route: str, **kwargs):
        """Make a request to the server"""
        request_future: asyncio.Future = await self.router.send(
            ClientToServerPacket(
                identifier=self.identifier,
                type="CLIENT_REQUEST",
                data=RequestPacket(route=route, arguments=kwargs),
            )
        )
        d = await request_future
        packet: Packet = json.loads(d)
        ws_type: Literal["CLIENT_REQUEST_RESPONSE"] = packet["type"]
        if ws_type != "CLIENT_REQUEST_RESPONSE":
            raise ValueError(
                "Unexpected websocket type received. Figured this might happen"
            )

        return packet["data"]

    async def _connect(self) -> None:
        try:
            async with websockets.connect(self._url) as websocket:
                print(type(websocket))
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
                        print("Below is setting")
                        print(id(self._connection_future))
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

            log.error("%s", e)
            raise e
        except WebSocketException as e:
            log.error("%s", e)
            raise
        finally:
            self._connection_future = asyncio.Future()
