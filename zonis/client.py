import asyncio
import logging

import signal
from typing import Optional, Dict, Any


from zonis import (
    Packet,
    Router,
    RouteHandler,
    UnknownPacket,
    UnhandledWebsocketType,
)
from zonis.packet import (
    RequestPacket,
    IdentifyDataPacket,
    ClientToServerPacket,
)

log = logging.getLogger(__name__)


class Client(RouteHandler):
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
        super().__init__()
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
        self.__is_open: bool = True
        self.__current_ws = None
        self.__task: Optional[asyncio.Task] = None
        self._instance_mapping: Dict[str, Any] = {}

        self.router: Router = Router(self.identifier, None).register_receiver(
            self._request_handler
        )

        # https://github.com/gearbot/GearBot/blob/live/GearBot/GearBot.py
        try:
            for signame in ("SIGINT", "SIGTERM", "SIGKILL"):
                asyncio.get_event_loop().add_signal_handler(
                    getattr(signal, signame),
                    lambda: asyncio.ensure_future(self.close()),
                )
        except Exception as e:
            pass  # doesn't work on windows

    async def block_until_closed(self):
        """A blocking call which releases when the WS closes."""
        await self.router.block_until_closed()

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
        data: Packet = await request_future
        if "type" not in data:
            log.debug("Failed to resolve packet type for %s", data)
            raise UnknownPacket

        if "data" not in data:
            log.debug(
                "Failed to resolve packet as it was missing the 'data' field: %s",
                data,
            )
            raise UnknownPacket

        if data["type"] != "SUCCESS_RESPONSE":
            raise UnhandledWebsocketType(
                f"Client.request expected a packet of type "
                f"SUCCESS_RESPONSE. Received {data['type']}"
            )

        return data["data"]
