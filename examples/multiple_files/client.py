import asyncio

from zonis.client import Client

# Import it to force it to load
from second_client_file import second_file


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        return "pong"

    await client.start()
    await asyncio.Future()


asyncio.run(main())
