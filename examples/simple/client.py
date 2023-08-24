import asyncio

from zonis.client import Client


async def main():
    client = Client(url="localhost:12344/ws")

    @client.route()
    async def ping():
        print("Pong'd!")
        return "pong"

    await client.start()
    print("here")
    await asyncio.Future()


asyncio.run(main())
