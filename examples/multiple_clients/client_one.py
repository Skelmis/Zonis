import asyncio

from zonis import Client


async def main():
    client = Client(url="localhost:12345/ws", identifier="one")

    @client.route()
    async def ping():
        return "pong"

    @client.route()
    async def one():
        return "I am a client specific route on one"

    await client.start()
    await client.block_until_closed()


asyncio.run(main())
