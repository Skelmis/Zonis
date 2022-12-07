from typing import TypedDict, Any, Optional, Literal, Type, Dict

from zonis.exceptions import (
    BaseZonisException,
    DuplicateConnection,
    UnhandledWebsocketType,
)

# Closure codes can be between 3000-4999
custom_close_codes: Dict[int, Type[BaseZonisException]] = {
    4102: DuplicateConnection,
    3001: UnhandledWebsocketType,
}


class Packet(TypedDict):
    data: Any
    type: Literal["IDENTIFY", "REQUEST", "SUCCESS_RESPONSE", "FAILURE_RESPONSE"]
    identifier: str


class RequestPacket(TypedDict):
    route: str
    arguments: Dict[str, Any]


class IdentifyDataPacket(TypedDict):
    override_key: Optional[str]
    secret_key: str


class IdentifyPacket(TypedDict):
    identifier: str
    type: Literal["IDENTIFY"]
    data: IdentifyDataPacket
