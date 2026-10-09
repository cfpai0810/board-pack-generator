"""Suite-wide guard: no test may open a network connection.

The model path is tested only with fake clients. If anything in the suite
tried to reach the network (a real SDK client, a stray request), the
connection attempt fails loudly instead of quietly calling an API.
"""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
