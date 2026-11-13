import json
import socket
import threading
import uuid
from http.client import HTTPConnection
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from bridge import BridgeServer, Session, encode, read_line


@pytest.fixture
def connected():
    session = Session(str(uuid.uuid4()))
    session.username = "alice"
    session.connected = True
    session.sock, peer = socket.socketpair()
    peer.settimeout(2)
    yield session, peer
    session.end("disconnected")
    peer.close()


def message(**overrides):
    return {
        "requestId": "req-1",
        "messageId": "msg-1",
        "conversationId": "global",
        "text": "Xin chào nhóm!",
        **overrides,
    }


def test_acceptance_is_not_ack_and_only_one_pending(connected):
    session, peer = connected
    assert session.send_message(message()) is True
    assert json.loads(read_line(peer)) == {
        "action": "BROADCAST",
        "message": "Xin chào nhóm!",
    }
    assert session.poll(0)["events"][0]["data"]["status"] == "sending"
    assert session.send_message(message(messageId="msg-2")) is False
    with session.condition:
        session.packet({"status": "BROADCAST_SUCCESS"})
    events = session.poll(0)["events"]
    assert [event["data"]["status"] for event in events] == ["sending", "sent"]
    assert events[1]["data"]["messageId"] == "msg-1"
    assert events[1]["data"]["revision"] == 2
    assert session.send_message(message()) is False


def test_incoming_during_pending_keeps_ack_correlation(connected):
    session, _ = connected
    session.send_message(message())
    with session.condition:
        session.packet({"type": "BROADCAST", "sender": "bob", "message": "<script>"})
        session.packet({"status": "BROADCAST_SUCCESS"})
    events = session.poll(0)["events"]
    assert events[1]["type"] == "users.snapshot"
    assert events[1]["data"]["users"][0]["presence"] == "unknown"
    assert events[2]["data"]["senderId"] == "bob"
    assert events[2]["data"]["text"] == "<script>"
    assert events[3]["data"]["messageId"] == "msg-1"


@pytest.mark.parametrize("status", ["AUTH_REQUIRED", "INVALID_REQUEST"])
def test_negative_ack_marks_failed(connected, status):
    session, _ = connected
    session.send_message(message())
    with session.condition:
        session.packet({"status": status})
    assert session.poll(0)["events"][-1]["data"]["status"] == "failed"


@pytest.mark.parametrize("status", ["UNICAST_SUCCESS", "UNICAST_FAILED"])
def test_private_ack_with_incoming_interleaving(connected, status):
    session, peer = connected
    assert session.send_message(message(conversationId="private-b", recipient="bob"))
    assert json.loads(read_line(peer)) == {
        "action": "UNICAST",
        "recipient": "bob",
        "message": "Xin chào nhóm!",
    }
    assert not session.send_message(message(messageId="global-2"))
    with session.condition:
        session.packet(
            {
                "type": "UNICAST",
                "sender": "carol",
                "recipient": "alice",
                "message": "Tin riêng xen kẽ",
            }
        )
        assert session.pending[0]["messageId"] == "msg-1"
        session.packet(
            {"type": "BROADCAST", "sender": "bob", "message": "Tin chung xen kẽ"}
        )
        session.packet({"status": status})
    messages = [
        event["data"]
        for event in session.poll(0)["events"]
        if event["type"] == "message.upsert"
    ]
    assert messages[1]["recipientId"] == "alice"
    assert messages[1]["conversationId"] not in {"global", "private-b"}
    assert messages[2]["conversationId"] == "global"
    assert messages[-1]["messageId"] == "msg-1"
    assert messages[-1]["conversationId"] == "private-b"
    assert messages[-1]["recipientId"] == "bob"
    assert messages[-1]["status"] == (
        "sent" if status == "UNICAST_SUCCESS" else "failed"
    )


@pytest.mark.parametrize("private", [False, True])
def test_wrong_ack_never_confirms_pending(connected, private):
    session, _ = connected
    request = message(conversationId="p", recipient="bob") if private else message()
    session.send_message(request)
    with session.condition, pytest.raises(ValueError, match="correlate ACK"):
        session.packet(
            {"status": "BROADCAST_SUCCESS" if private else "UNICAST_SUCCESS"}
        )
    assert session.pending[0]["status"] == "sending"
    assert session.poll(0)["events"][-1]["data"]["status"] == "sending"


def test_private_incoming_pair_id_stable_and_wrong_recipient_rejected(connected):
    session, _ = connected
    packet = {
        "type": "UNICAST",
        "sender": "bob",
        "recipient": "alice",
        "message": "Chào A",
    }
    with session.condition:
        session.packet(packet)
        session.packet({**packet, "message": "Tin thứ hai"})
        count = session.sequence
        with pytest.raises(ValueError):
            session.packet({**packet, "recipient": "someone-else"})
        assert session.sequence == count
    messages = [
        event["data"]
        for event in session.poll(0)["events"]
        if event["type"] == "message.upsert"
    ]
    assert messages[0]["conversationId"] == messages[1]["conversationId"] != "global"
    assert messages[0]["messageId"] != messages[1]["messageId"]
    assert session.users["bob"]["presence"] == "unknown"


@pytest.mark.parametrize(
    "overrides",
    [
        {"conversationId": "private"},
        {"text": ""},
        {"text": "   "},
        {"messageId": None},
        {"text": "Đ" * 1000},
        {"conversationId": "private", "recipient": "alice"},
        {"conversationId": "private", "recipient": ""},
        {"conversationId": "global", "recipient": "bob"},
    ],
)
def test_rejected_requests_do_not_write_tcp(connected, overrides):
    session, peer = connected
    with pytest.raises(ValueError):
        session.send_message(message(**overrides))
    assert session.pending is None
    peer.settimeout(0.02)
    with pytest.raises(TimeoutError):
        peer.recv(1)


@pytest.mark.parametrize("cause", ["eof", "timeout", "bad-frame"])
@pytest.mark.parametrize("private", [False, True])
def test_reader_loss_never_fabricates_sent(connected, cause, private):
    session, peer = connected
    session.send_message(
        message(conversationId="p", recipient="bob") if private else message()
    )
    read_line(peer)
    if cause == "timeout":
        session.pending = (session.pending[0], 0)
    elif cause == "bad-frame":
        peer.sendall(b"not-json\n")
    else:
        peer.shutdown(socket.SHUT_RDWR)
    thread = threading.Thread(target=session.receive)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    events = session.poll(0)["events"]
    assert events[-1]["data"]["state"] == "lost"
    assert not any(event["data"].get("status") == "sent" for event in events)


@pytest.mark.parametrize("status", ["LOGIN_FAILED", "LOGIN_SUCCESS"])
def test_open_uses_real_handshake_and_login(status):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        frames = []
        release = threading.Event()

        def serve():
            sock, _ = listener.accept()
            with sock:
                frames.append(read_line(sock))
                sock.sendall(b"WELCOME\n")
                frames.append(json.loads(read_line(sock)))
                sock.sendall(encode({"status": status}))
                release.wait(2)

        thread = threading.Thread(target=serve)
        thread.start()
        session = Session(str(uuid.uuid4()))
        session.open(listener.getsockname(), "alice", "public-test-password")
        events = session.poll(0)["events"]
        assert frames == [
            b"HELLO\n",
            {
                "action": "LOGIN",
                "username": "alice",
                "password": "public-test-password",
            },
        ]
        assert events[0]["data"]["state"] == (
            "connected" if status == "LOGIN_SUCCESS" else "disconnected"
        )
        assert "public-test-password" not in json.dumps(events)
        session.end("disconnected")
        release.set()
        thread.join(2)


def test_event_gap_is_rejected(connected):
    session, _ = connected
    with session.condition:
        for _ in range(260):
            session.connection("connected")
    with pytest.raises(ValueError, match="gián đoạn"):
        session.poll(0)


def test_online_snapshot_and_chat_share_one_pending(connected):
    session, peer = connected
    session.send_message(message())
    read_line(peer)
    assert not session.refresh_online()
    with session.condition:
        session.packet({"status": "BROADCAST_SUCCESS"})
    assert session.refresh_online()
    assert json.loads(read_line(peer)) == {"action": "LIST_ONLINE"}
    accepted = []
    waiting = threading.Thread(
        target=lambda: accepted.append(session.send_message(message(messageId="other")))
    )
    waiting.start()
    peer.settimeout(0.02)
    with pytest.raises(TimeoutError):
        peer.recv(1)
    peer.settimeout(2)
    with session.condition:
        session.packet(
            {"type": "UNICAST", "sender": "bob", "recipient": "alice", "message": "Hi"}
        )
        assert session.pending[0] == {"action": "LIST_ONLINE"}
        session.packet({"status": "LIST_ONLINE_SUCCESS", "users": ["alice", "bob"]})
    waiting.join(2)
    assert accepted == [True]
    assert json.loads(read_line(peer))["action"] == "BROADCAST"
    with session.condition:
        session.packet({"status": "BROADCAST_SUCCESS"})
    assert session.online_status == "available"
    assert session.users["bob"]["presence"] == "online"
    assert not session.refresh_online()
    session.next_online = 0
    assert session.refresh_online()
    read_line(peer)
    with session.condition:
        session.packet({"status": "LIST_ONLINE_SUCCESS", "users": ["alice"]})
    assert session.users["bob"]["presence"] == "offline"
    assert session.poll(0)["events"][-1]["data"]["onlineStatus"] == "available"


def test_unsupported_online_does_not_break_chat_or_probe_again(connected):
    session, peer = connected
    assert session.refresh_online()
    read_line(peer)
    with session.condition:
        session.packet({"status": "INVALID_REQUEST"})
    assert session.online_status == "unavailable" and session.connected
    assert not session.refresh_online()
    assert session.send_message(message())
    assert json.loads(read_line(peer))["action"] == "BROADCAST"


@pytest.mark.parametrize("users", [None, "alice", ["bob", "bob"], [""], [False]])
def test_invalid_online_list_never_publishes_presence(connected, users):
    session, peer = connected
    session.refresh_online()
    read_line(peer)
    with session.condition, pytest.raises(ValueError):
        session.packet({"status": "LIST_ONLINE_SUCCESS", "users": users})
    assert session.online_status == "loading"


def test_online_reply_after_disconnect_is_ignored(connected):
    session, peer = connected
    session.refresh_online()
    read_line(peer)
    session.end("lost")
    count = session.sequence
    with session.condition:
        session.packet({"status": "LIST_ONLINE_SUCCESS", "users": ["alice", "bob"]})
    assert session.sequence == count and session.online_status == "unavailable"
    assert not any(user["presence"] == "online" for user in session.users.values())


@pytest.fixture
def http_bridge():
    with BridgeServer(("127.0.0.1", 0), ("127.0.0.1", 1)) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}"
        server.shutdown()
        thread.join(2)


@pytest.mark.parametrize(
    "path,headers,body,expected",
    [
        ("/api/events", {}, None, 409),
        ("/api/connect", {"Origin": "http://evil.invalid"}, b"{}", 403),
        ("/api/connect", {}, b"[]", 400),
        ("/api/connect", {}, b"not-json", 400),
        ("/api/connect", {}, b'{"sessionId":"bad"}', 400),
        ("/api/message", {}, b"{}", 400),
    ],
)
def test_http_boundary(http_bridge, path, headers, body, expected):
    if "Origin" in headers:
        target = urlsplit(http_bridge)
        connection = HTTPConnection(target.hostname, target.port, timeout=2)
        try:
            connection.putrequest("POST", path)
            for name, value in {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                **headers,
            }.items():
                connection.putheader(name, value)
            # Verify header rejection without unread request bytes resetting Windows TCP.
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == expected
            assert isinstance(json.loads(response.read())["error"], str)
        finally:
            connection.close()
        return
    request = Request(
        http_bridge + path,
        data=body,
        headers={"Content-Type": "application/json", **headers},
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)
    assert error.value.code == expected
    assert isinstance(json.loads(error.value.read())["error"], str)


def test_static_server_exposes_web_only(http_bridge):
    with urlopen(http_bridge + "/", timeout=2) as response:
        assert b"js/main.js" in response.read()
    with pytest.raises(HTTPError) as error:
        urlopen(http_bridge + "/pyproject.toml", timeout=2)
    assert error.value.code == 404
