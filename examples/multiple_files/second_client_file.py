from zonis.client import route


@route()
async def second_file():
    return "This is another file"
