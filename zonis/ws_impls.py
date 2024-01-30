from typing import Protocol, runtime_checkable


@runtime_checkable
class WebsocketProtocol(Protocol):
    """The protocol underlying websockets should be exposed via."""

    def __init__(self, ws):
        raise NotImplementedError

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
    """A websocket implementation wrapping FastAPI websockets"""

    def __init__(self, ws):
        self.ws = ws

    async def send(self, content: str) -> None:
        await self.ws.send_text(content)

    async def receive(self) -> str | bytes | dict:
        return await self.ws.receive_text()


class Websockets:
    """A websocket implementation wrapping the websockets library"""

    def __init__(self, ws):
        self.ws = ws

    async def send(self, content: str) -> None:
        await self.ws.send(content)

    async def receive(self) -> str | bytes | dict:
        return await self.ws.recv()
