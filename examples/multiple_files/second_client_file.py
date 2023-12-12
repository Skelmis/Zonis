from zonis import route


@route()
async def second_file():
    return "This is another file"
