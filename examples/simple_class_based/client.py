import asyncio
import logging

from zonis import Client, route

logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("zonis").setLevel(level=logging.DEBUG)


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
    await client.block_until_closed()


asyncio.run(main())
