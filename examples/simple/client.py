import asyncio

from zonis.client import Client


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        return "pong"

    await client.start()
    await asyncio.Future()


asyncio.run(main())
