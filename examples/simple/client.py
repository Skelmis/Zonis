import asyncio

from zonis import Client


async def main():
    client = Client(url="localhost:12344/ws")

    @client.route()
    async def ping():
        print("Pong'd!")
        return "pong"

    await client.start()
    await client.block_until_closed()


asyncio.run(main())
