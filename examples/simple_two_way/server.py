import asyncio
import json

from fastapi import FastAPI
from starlette.websockets import WebSocket, WebSocketDisconnect

from zonis import UnknownClient, BaseZonisException, RequestFailed
from zonis.server import Server

import logging

logging.basicConfig(
    format="%(levelname)-7s | %(asctime)s | %(filename)12s:%(funcName)-12s | %(message)s",
    datefmt="%I:%M:%S %p %d/%m/%Y",
    level=logging.DEBUG,
)

app = FastAPI()
server = Server(using_fastapi_websockets=True)


@server.route()
async def ping():
    return "Server pong"


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
    try:
        identifier = await server.parse_identify(json.loads(d), websocket)
    except BaseZonisException:
        print("WS failed to identify")
        return

    try:
        await asyncio.Future()
    except WebSocketDisconnect:
        server.disconnect(identifier)
