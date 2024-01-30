import asyncio

from zonis.client import Client


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        return "pong"

    await client.start()
    response = await client.request("ping")
    print(f"Received response: {response}")
    await client.block_until_closed()


asyncio.run(main())
