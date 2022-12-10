import asyncio

from zonis.client import Client, route


class Test:
    def __init__(self):
        self.msg = "ping"

    @route()
    async def ping(self):
        return self.msg


async def main():
    client = Client(url="localhost:12345/ws")
    client.register_class_instance_for_routes(Test(), "ping")

    await client.start()
    await asyncio.Future()


asyncio.run(main())
