from typing import Protocol, runtime_checkable


@runtime_checkable
class WebsocketProtocol(Protocol):
    async def send(self, content: str) -> None:
        """Send a message down the wire.

        Parameters
        ----------
        content: str
            The content to send down the wire.
        """
        raise NotImplementedError

    async def receive(self) -> str | bytes | dict:
        """Listen for a message on the wire.

        Returns
        -------
        str|bytes|dict
            The content received
        """
        raise NotImplementedError


class FastAPIWebsockets:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, content: str) -> None:
        await self.ws.send_text(content)

    async def receive(self) -> str | bytes | dict:
        return await self.ws.receive_text()


class Websockets:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, content: str) -> None:
        await self.ws.send(content)

    async def receive(self) -> str | bytes | dict:
        return await self.ws.recv()
