"""Current checkout only: real P2 tickets, P1 UDP and P3 HTTP (no fixture tickets)."""

import hashlib
import io
import json
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from bridge import BridgeServer, read_line
from bridge_files import load_p1
from server.socket_server import SocketServer

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "public-integrated-test-only"


def wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Integrated operation timed out")


@pytest.fixture
def integrated(tmp_path):
    factory = load_p1(ROOT)
    for name in ("p1.client", "shared.protocol", "server.socket_server", "bridge"):
        assert Path(sys.modules[name].__file__).resolve().is_relative_to(ROOT), name
    tcp = SocketServer(host="127.0.0.1", port=0, udp_port=0)
    tcp_thread = threading.Thread(target=tcp.start)
    tcp_thread.start()
    http = None
    try:
        wait(lambda: tcp.server_socket is not None)
        http = BridgeServer(
            ("127.0.0.1", 0),
            tcp.server_socket.getsockname(),
            file_factory=factory,
            storage=tmp_path,
        )
        http_thread = threading.Thread(target=http.serve_forever)
        http_thread.start()
        yield tcp, http
    finally:
        if http:
            http.shutdown()
            http.server_close()
            http_thread.join(5)
            assert not http_thread.is_alive()
        tcp.stop()
        tcp_thread.join(5)
        assert not tcp_thread.is_alive()


def api(http, route, body=None, token=None, *, binary=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Connect-Session"] = token
    data = None if body is None else json.dumps(body).encode()
    with urlopen(
        Request(f"http://127.0.0.1:{http.server_port}" + route, data, headers),
        timeout=20,
    ) as response:
        content = response.read()
    return content if binary else json.loads(content)


def login(tcp, http, username):
    with socket.create_connection(tcp.server_socket.getsockname(), timeout=5) as sock:
        sock.sendall(b"HELLO\n")
        assert read_line(sock) == b"WELCOME\n"
        sock.sendall(
            (
                json.dumps(
                    dict(action="REGISTER", username=username, password=PASSWORD)
                )
                + "\n"
            ).encode()
        )
        assert json.loads(read_line(sock))["status"] == "REGISTER_SUCCESS"
    result = api(
        http,
        "/api/connect",
        dict(sessionId=str(uuid.uuid4()), username=username, password=PASSWORD),
    )
    session = http.sessions[result["token"]]
    wait(
        lambda: any(
            e["type"] == "files.changed" and e["data"]["state"] == "ready"
            for _, e in session.events
        )
    )
    # Actual P2 allocated a relay peer; no test code provisions a ticket.
    assert username in tcp.file_relay._usernames
    return result["token"], session


def send(http, token, session, text, recipient=None):
    wait(lambda: session.pending is None)
    message_id = str(uuid.uuid4())
    assert api(
        http,
        "/api/message",
        dict(
            requestId=str(uuid.uuid4()),
            messageId=message_id,
            conversationId="private" if recipient else "global",
            recipient=recipient,
            text=text,
        ),
        token,
    )["accepted"]
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["messageId"] == message_id
            and e["data"]["status"] == "sent"
            for _, e in session.events
        )
    )


def test_current_login_online_chat_and_ticket_revocation(integrated):
    tcp, http = integrated
    a_token, a = login(tcp, http, "integrated-alice")
    b_token, b = login(tcp, http, "integrated-bob")
    wait(lambda: a.users.get(b.username, {}).get("presence") == "online")
    send(http, a_token, a, "Kênh chung thật")
    wait(
        lambda: any(
            e["type"] == "message.upsert" and e["data"]["text"] == "Kênh chung thật"
            for _, e in b.events
        )
    )
    send(http, b_token, b, "Riêng Bob → Alice", a.username)
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "Riêng Bob → Alice"
            and e["data"]["recipientId"] == a.username
            for _, e in a.events
        )
    )
    files = b.files
    api(http, "/api/disconnect", {}, b_token)
    wait(lambda: b.username not in tcp.file_relay._usernames)
    wait(lambda: a.users.get(b.username, {}).get("presence") == "offline")
    assert files.closed.wait(5) and not files.root.exists()
    send(http, a_token, a, "Chat vẫn hoạt động")


@pytest.mark.parametrize(
    "reverse,reject,payload",
    [
        (False, False, bytes(range(256)) * 257),
        (True, False, bytes(range(256)) * 257),
        (True, False, b""),
        (True, True, b"reject this"),
    ],
)
def test_current_bidirectional_files_hash_reject_and_chat(
    integrated, reverse, reject, payload
):
    tcp, http = integrated
    a = login(tcp, http, "integrated-alice")
    b = login(tcp, http, "integrated-bob")
    (sender_token, sender), (receiver_token, receiver) = (b, a) if reverse else (a, b)
    received_paths = []
    for _ in range(1 if reject else 2):
        transfer_id = str(uuid.uuid4())
        query = urlencode(
            dict(
                requestId=str(uuid.uuid4()),
                transferId=transfer_id,
                conversationId="private",
                recipient=receiver.username,
                name="Báo cáo trùng tên – Đức.bin",
            )
        )
        request = Request(
            f"http://127.0.0.1:{http.server_port}/api/files/upload?{query}",
            payload,
            {
                "Content-Type": "application/octet-stream",
                "X-Connect-Session": sender_token,
            },
        )
        with urlopen(request, timeout=20) as response:
            assert json.load(response)["accepted"]
        wait(
            lambda: any(
                r["data"]["status"] == "awaiting_acceptance"
                for r in receiver.files.records.values()
            )
        )
        wire = next(
            k
            for k, r in receiver.files.records.items()
            if r["data"]["status"] == "awaiting_acceptance"
        )
        send(http, sender_token, sender, "Chat trong lúc chờ file")
        decision = "reject" if reject else "accept"
        assert api(
            http, "/api/files/" + decision, {"transferId": wire}, receiver_token
        )["accepted"]
        expected = "rejected" if reject else "completed"
        wait(lambda: sender.files.records[transfer_id]["data"]["status"] == expected)
        wait(lambda: receiver.files.records[wire]["data"]["status"] == expected)
        if reject:
            with pytest.raises(HTTPError) as denied:
                api(http, "/api/files/" + wire, token=receiver_token, binary=True)
            assert denied.value.code == 409
        else:
            actual = api(http, "/api/files/" + wire, token=receiver_token, binary=True)
            assert len(actual) == len(payload)
            assert hashlib.sha256(actual).digest() == hashlib.sha256(payload).digest()
            received_paths.append(receiver.files.records[wire]["path"])
            with pytest.raises(HTTPError) as denied:
                api(http, "/api/files/" + wire, token=sender_token, binary=True)
            assert denied.value.code == 409
    assert len(set(received_paths)) == len(received_paths)


def test_current_disconnect_pending_file_cleans_session(integrated):
    tcp, http = integrated
    a_token, a = login(tcp, http, "integrated-alice")
    _, b = login(tcp, http, "integrated-bob")
    meta = dict(
        requestId=str(uuid.uuid4()),
        transferId=str(uuid.uuid4()),
        conversationId="private",
        recipient=b.username,
        name="pending.bin",
    )
    assert a.files.upload(meta, 1, io.BytesIO(b"x"))
    wait(lambda: bool(b.files.records))
    files = a.files
    api(http, "/api/disconnect", {}, a_token)
    assert files.closed.wait(5) and not files.root.exists()
    wait(lambda: a.username not in tcp.file_relay._usernames)
    assert b.connected
