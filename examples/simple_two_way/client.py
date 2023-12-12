import asyncio

from zonis.client import Client

import logging

logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("zonis").setLevel(level=logging.DEBUG)


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        print("Pong'd")
        return "pong"

    await client.start()
    response = await client.request("ping")
    print(f"Received response: {response}")
    await client.block_until_closed()


asyncio.run(main())
