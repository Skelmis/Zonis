import asyncio

from zonis.client import Client


async def main():
    client = Client(url="localhost:12345/ws", identifier="two")

    @client.route()
    async def ping():
        return "pong"

    @client.route()
    async def two():
        return "I am a client specific route on two"

    await client.start()
    await asyncio.Future()


asyncio.run(main())
