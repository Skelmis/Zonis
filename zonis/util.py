import asyncio
import logging

log = logging.getLogger(__name__)
background_tasks: set[tuple[str, asyncio.Task]] = set()


def create_task(*args, router_id: str, **kwargs) -> asyncio.Task:
    """Creates a task while maintain a background reference so they dont get de-reffed"""
    task = asyncio.create_task(*args, **kwargs)
    background_tasks.add((router_id, task))
    task.add_done_callback(lambda _: background_tasks.discard((router_id, task)))
    return task
