import asyncio

from zonis.client import Client


async def main():
    client = Client(url="localhost:12345/ws")

    @client.route()
    async def ping():
        print("Pong'd")
        return "pong"

    await client.start()
    print("here")
    await asyncio.sleep(5)
    response = await client.request("ping")
    print(response)
    await asyncio.Future()


asyncio.run(main())
