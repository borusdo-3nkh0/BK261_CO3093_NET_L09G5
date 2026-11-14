"""Target the observed Windows TLS read failure, not file-transfer behaviour."""

import socket
import ssl
import threading
import time
import uuid
from unittest.mock import Mock

import pytest

from server.socket_server import receive_line
from tests.test_security_live import api, login, wait
from tests.test_security_live import integrated as integrated


def test_live_would_block_keeps_session_and_routes_once(integrated, monkeypatch):
    tcp, http = integrated
    token, a = login(tcp, http, "would-block-alice")
    _, b = login(tcp, http, "would-block-bob")
    target = tcp.message_router.get_client(a.username)
    original = ssl.SSLSocket.recv
    injected = threading.Event()

    def recv(sock, *args, **kwargs):
        if sock is target and not injected.is_set():
            injected.set()
            raise BlockingIOError(10035, "Injected WSAEWOULDBLOCK")
        return original(sock, *args, **kwargs)

    monkeypatch.setattr(ssl.SSLSocket, "recv", recv)
    wait(lambda: a.pending is None)
    assert api(
        http,
        "/api/message",
        dict(
            requestId=str(uuid.uuid4()),
            messageId=str(uuid.uuid4()),
            conversationId="private",
            recipient=b.username,
            text="after would-block",
        ),
        token,
    )["accepted"]
    assert injected.wait(2)
    wait(lambda: not a.pending or not a.connected, timeout=3)
    assert a.connected
    wait(
        lambda: any(
            e["type"] == "message.upsert" and e["data"]["text"] == "after would-block"
            for _, e in b.events
        ),
        timeout=3,
    )
    assert (
        sum(
            e["type"] == "message.upsert" and e["data"]["text"] == "after would-block"
            for _, e in b.events
        )
        == 1
    )


def test_receive_lock_wait_keeps_original_deadline():
    lock = threading.Lock()
    lock.acquire()
    started = time.monotonic()
    try:
        with pytest.raises(socket.timeout):
            receive_line(None, timeout=0.05, io_lock=lock)
        assert time.monotonic() - started < 0.5
    finally:
        lock.release()


def test_locked_read_keeps_deadline_for_partial_input_and_disconnect():
    left, right = socket.socketpair()
    left.settimeout(1)
    lock = threading.Lock()
    right.sendall(b"partial")
    started = time.monotonic()
    try:
        with pytest.raises(socket.timeout):
            receive_line(left, timeout=0.05, io_lock=lock)
        assert time.monotonic() - started < 0.5
        assert left.gettimeout() == 1 and not lock.locked()
        right.close()
        assert receive_line(left, timeout=0.2, io_lock=lock) is None
    finally:
        right.close()
        left.close()


@pytest.mark.parametrize(
    "error",
    [
        ConnectionResetError(10054, "reset"),
        BlockingIOError(22, "not would-block"),
        ssl.SSLError(1, "fatal TLS failure"),
    ],
)
def test_locked_read_propagates_fatal_errors(error):
    left, right = socket.socketpair()
    lock = threading.Lock()
    proxy = Mock(wraps=left)
    proxy.recv.side_effect = error
    try:
        with pytest.raises(type(error)) as raised:
            receive_line(proxy, timeout=0.1, io_lock=lock)
        assert raised.value is error and not lock.locked()
    finally:
        left.close()
        right.close()


def test_live_router_and_receiver_share_ssl_lock(integrated, monkeypatch):
    tcp, http = integrated
    a_token, a = login(tcp, http, "lock-alice")
    b_token, b = login(tcp, http, "lock-bob")
    target = tcp.message_router.get_client(a.username)
    lock = tcp.message_router.send_locks[a.username]
    paused, release, attempted, written = (threading.Event() for _ in range(4))
    recv, sendall, route = (
        ssl.SSLSocket.recv,
        ssl.SSLSocket.sendall,
        tcp.message_router.send_to_client,
    )

    def receive(sock, *args, **kwargs):
        if sock is target:
            assert lock.locked() and sock.gettimeout() == 0
            if not paused.is_set():
                paused.set()
                assert release.wait(2)
        return recv(sock, *args, **kwargs)

    def write(sock, *args, **kwargs):
        if sock is target:
            assert lock.locked() and sock.gettimeout() != 0
            written.set()
        return sendall(sock, *args, **kwargs)

    def send_to_client(username, *args, **kwargs):
        if username == a.username:
            attempted.set()
        return route(username, *args, **kwargs)

    monkeypatch.setattr(ssl.SSLSocket, "recv", receive)
    monkeypatch.setattr(ssl.SSLSocket, "sendall", write)
    monkeypatch.setattr(tcp.message_router, "send_to_client", send_to_client)
    wait(lambda: not a.pending and not b.pending)

    def submit(token, text, recipient):
        assert api(
            http,
            "/api/message",
            dict(
                requestId=str(uuid.uuid4()),
                messageId=str(uuid.uuid4()),
                conversationId="private",
                recipient=recipient,
                text=text,
            ),
            token,
        )["accepted"]

    try:
        submit(a_token, "wake receiver", b.username)
        assert paused.wait(2)
        submit(b_token, "reply during read", a.username)
        assert attempted.wait(2)
        assert not written.is_set(), "Router must wait outside the active SSL read"
    finally:
        release.set()
    wait(
        lambda: any(
            e["type"] == "message.upsert" and e["data"]["text"] == "reply during read"
            for _, e in a.events
        ),
        timeout=3,
    )
    assert a.connected and b.connected and written.is_set()
