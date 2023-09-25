import asyncio

from zonis.client import Client

import logging


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        print("Pong'd")
        return "pong"

    await client.start()
    response = await client.request("ping")
    print(f"Received response: {response}")
    await asyncio.Future()


asyncio.run(main())
