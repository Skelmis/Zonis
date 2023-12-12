from __future__ import annotations

import logging
from typing import Optional, Callable, Any

from zonis import DuplicateRoute

log = logging.getLogger(__name__)
deferred_routes = {}


def route(route_name: Optional[str] = None):
    """Turn an async function into a valid IPC route.

    Parameters
    ----------
    route_name: Optional[str]
        An optional name for this IPC route,
        defaults to the name of the function.

    Raises
    ------
    DuplicateRoute
        A route with this name already exists
    """

    def decorator(func: Callable):
        name = route_name or func.__name__
        if name in deferred_routes:
            raise DuplicateRoute

        deferred_routes[name] = func
        return func

    return decorator


class RouteHandler:
    def __init__(
        self,
    ) -> None:
        self._routes: dict[str, Callable] = {}
        self.__is_open: bool = True
        self.__current_ws = None
        self._instance_mapping: dict[str, Any] = {}

    def route(self, route_name: Optional[str] = None):
        """Turn an async function into a valid IPC route.

        Parameters
        ----------
        route_name: Optional[str]
            An optional name for this IPC route,
            defaults to the name of the function.

        Raises
        ------
        DuplicateRoute
            A route with this name already exists

        Notes
        -----
        If this is a method on a class, you will also
        need to use the ``register_class_instance_for_routes``
        method for this to work as an IPC route.
        """

        def decorator(func: Callable):
            name = route_name or func.__name__
            if name in self._routes:
                raise DuplicateRoute

            log.debug("Registered route %s for class %s", name, self.__class__.__name__)
            self._routes[name] = func
            return func

        return decorator

    def load_routes(self) -> None:
        """Loads all decorated routes."""
        global deferred_routes
        for k, v in deferred_routes.items():
            if k in self._routes:
                raise DuplicateRoute

            log.debug("Registered route %s for class %s", k, self.__class__.__name__)
            self._routes[k] = v
        deferred_routes = {}

    def register_class_instance_for_routes(self, instance, *routes) -> None:
        """Register a class instance for the given route.

        When you turn a method on a class into an IPC route,
        you need to call this method with the instance of the class
        to use as well as the names of the routes for registration to work correctly.

        Parameters
        ----------
        instance
            The class instance the methods live on
        routes
            A list of strings representing the names
            of the IPC routes for this class.
        """
        for r in routes:
            self._instance_mapping[r] = instance
