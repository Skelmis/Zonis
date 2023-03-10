Custom server backends
======================

Not using FastAPI or Websockets?

In order to add support for your platform all you need to do
is subclass `zonis.server.Server` and override the following methods:

- _recv
- _send

The existing implementations can be used as a reference for your own.