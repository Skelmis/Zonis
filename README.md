Zonis
---

A coro based callback system for many to one IPC setups.

`pip install zonis`

See the [examples](https://github.com/Skelmis/Zonis/tree/master/exampleshttps://github.com/Skelmis/Zonis/tree/master/examples) for simple use cases.
___
## Build the docs locally

If you want to build and run the docs locally using sphinx run
```
sphinx-autobuild -a docs docs/_build/html --watch zonis
```
this will build the docs and start a local server; additionally it will listed for changes to the source directory ``zonis`` and to the docs source directory ``docs/``.
You can find the builded files at ``docs/_build``.

---

Two way IPC:

Error:
```text
Traceback (most recent call last):
  File "/home/skelmis/Code/Python/zonis/examples/simple_two_way/client.py", line 22, in <module>
    asyncio.run(main())
  File "/usr/lib/python3.10/asyncio/runners.py", line 44, in run
    return loop.run_until_complete(main)
  File "/usr/lib/python3.10/asyncio/base_events.py", line 649, in run_until_complete
    return future.result()
  File "/home/skelmis/Code/Python/zonis/examples/simple_two_way/client.py", line 17, in main
    response = await client.request("ping")
  File "/home/skelmis/Code/Python/zonis/zonis/client.py", line 211, in request
    d = await self.__current_ws.recv()
  File "/home/skelmis/.cache/pypoetry/virtualenvs/zonis-QJXn1okD-py3.10/lib/python3.10/site-packages/websockets/legacy/protocol.py", line 532, in recv
    raise RuntimeError(
RuntimeError: cannot call recv while another coroutine is already waiting for the next message
```

Fix: `recv` on client and server needs to be a queue with single source of truth somehow to avoid above