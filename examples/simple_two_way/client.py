import asyncio

from zonis.client import Client

import logging

logging.basicConfig(
    # format="%(levelname)-7s | %(asctime)s | %(filename)12s:%(funcName)-12s | %(message)s",
    datefmt="%I:%M:%S %p %d/%m/%Y",
    level=logging.DEBUG,
)
logging.getLogger("httpx").setLevel(logging.NOTSET)
logging.getLogger("websockets").setLevel(logging.NOTSET)


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        print("Pong'd")
        return "pong"

    await client.start()
    print("here")
    await asyncio.sleep(5)
    print("sending")
    response = await client.request("ping")
    print(f"Received response: {response}")
    await asyncio.Future()


asyncio.run(main())
