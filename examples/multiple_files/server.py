import asyncio
import json

from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect

from zonis import UnknownClient, BaseZonisException
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


@app.get("/route")
async def index():
    try:
        response = await server.request("second_file")
        return {"data": response}
    except UnknownClient as e:
        return e


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
