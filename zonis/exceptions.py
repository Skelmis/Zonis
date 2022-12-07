class BaseZonisException(Exception):
    """A base exception handler for Zonis."""

    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = self.__doc__

    def __str__(self):
        return self.message


class DuplicateConnection(BaseZonisException):
    """You have attempted to connect with a duplicated identifier.
    Please try again with a unique one or provide the correct override key."""


class DuplicateRoute(BaseZonisException):
    """You are attempting to register multiple routes with the same name.
    Consider setting the route_name argument to something unique."""


class UnhandledWebsocketType(BaseZonisException):
    """Found a websocket type we can't handle."""


class UnknownRoute(BaseZonisException):
    """The route you requested does not exist."""


class UnknownClient(BaseZonisException):
    """The client you requested is not currently connected."""


class RequestFailed(BaseZonisException):
    """This request resulted in an error on the end client."""

    def __init__(self, data):
        super().__init__()
        self.response_data = data

    def __str__(self):
        return self.message + "\n\n" + self.response_data
