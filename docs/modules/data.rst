Packet data structures
^^^^^^^^^^^^^^^^^^^^^^

At the router level:

.. code-block:: text

    {
        "packet_id": "str",
        "type": "request|response",
        "data": {...}
    }

The packets which can be sent at the client level:

.. py:currentmodule:: zonis

.. autoclass:: Packet
    :members:
    :undoc-members:

.. autoclass:: RequestPacket
    :members:
    :undoc-members:

.. autoclass:: IdentifyDataPacket
    :members:
    :undoc-members:

.. autoclass:: IdentifyPacket
    :members:
    :undoc-members:

.. autoclass:: ClientToServerPacket
    :members:
    :undoc-members:
