import asyncio
import json

from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect

from zonis import UnknownClient, BaseZonisException, RequestFailed
from zonis.server import Server

app = FastAPI()
server = Server(using_fastapi_websockets=True)


@app.get("/")
async def index():
    try:
        response = await server.request_all("ping")
        return {"data": response}
    except UnknownClient as e:
        return e


@app.get("/one")
async def one():
    try:
        response = await server.request("one", client_identifier="one")
        return {"data": response}
    except UnknownClient as e:
        return e


@app.get("/two")
async def two():
    try:
        response = await server.request("two", client_identifier="two")
        return {"data": response}
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
