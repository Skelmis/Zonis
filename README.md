Zonis
---

A coro based callback system for many to one IPC setups.

#### Examples

##### Simple

*Client*

```python
import asyncio

from zonis.client import Client

async def main():
    client = Client()
    
    @client.route()
    async def ping():
        return "ping"
    
    await client.start()

asyncio.run(main())
```

*Server*

```python
import json
import asyncio

from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect

from zonis import BaseZonisException
from zonis.server import Server

app = FastAPI()
server = Server()

@app.get("/")
async def index():
    response = await server.request("ping")
    return {"data": response} # Returns pong

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    d: str = await websocket.receive_text()
    try:
        identifier = await server.parse_identify(json.loads(d), websocket)
    except BaseZonisException:
        print("WS failed to identify")
        return

    try:
        await asyncio.Future()
    except WebSocketDisconnect:
        server.disconnect(identifier)

```

---

##### Multiple clients

*Client one*

```python
import asyncio

from zonis.client import Client

async def main():
    client = Client(identifier="one")
    
    @client.route()
    async def ping():
        return f"ping {client.identifier}"
    
    await client.start()

asyncio.run(main())
```

*Client two*

```python
import asyncio

from zonis.client import Client

async def main():
    client = Client(identifier="two")
    
    @client.route()
    async def ping():
        return f"ping {client.identifier}"
    
    await client.start()

asyncio.run(main())
```

*Server*

```python
from fastapi import FastAPI

from zonis.server import Server

app = FastAPI()
server = Server()

@app.on_event("startup")
async def startup_event():
    await server.start()

@app.get("/")
async def index():
    response = await server.request_all("ping")
    return {"data": response} # Returns {"data": {"one": "pong one", "two": "pong two"}}

@app.get("/one")
async def one():
    response = await server.request("ping", client_identifier="one")
    return {"data": response} # Returns {"data": "pong one"}
```