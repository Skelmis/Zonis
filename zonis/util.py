import asyncio

background_tasks: set[asyncio.Task] = set()


def create_task(*args, **kwargs) -> asyncio.Task:
    task = asyncio.create_task(*args, **kwargs)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task
