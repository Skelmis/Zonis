Zonis
---

A coro based callback system for many to one IPC setups.

`pip install zonis`


---

### Simplistic example

Client:
```python
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
```

Server:
```python
import asyncio
import json

from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect

from zonis import UnknownClient
from zonis.server import Server

app = FastAPI()
server = Server(using_fastapi_websockets=True)


@app.get("/")
async def index():
    try:
        response = await server.request("ping")
        return {"data": response}  # Returns pong
    except UnknownClient as e:
        return e


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    d: str = await websocket.receive_text()
    identifier = await server.parse_identify(json.loads(d), websocket)

    try:
        await asyncio.Future()
    except WebSocketDisconnect:
        await server.disconnect(identifier)
        print(f"Closed connection for {identifier}")
```


See the [examples](https://github.com/Skelmis/Zonis/tree/master/examples) directory for more use cases.

#### For documentation, please see [here](https://zonis.readthedocs.io/en/latest/).

---

### Support

Want realtime help? Join the discord [here](https://discord.gg/BqPNSH2jPg).

---

### Funding

Want a feature added quickly? Want me to help build your software using this?

Sponsor me [here](https://github.com/sponsors/Skelmis)

