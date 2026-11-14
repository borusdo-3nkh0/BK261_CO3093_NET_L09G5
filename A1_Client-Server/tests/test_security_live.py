"""Current checkout only: real P2 tickets, P1 UDP and P3 HTTP (no fixture tickets)."""

import hashlib
import hmac
import io
import json
import shutil
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
from security.context import Context, SecurityError, chat_aad, new_material
from security.tls import client_context, create_certificates, server_context
from security.udp import PacketCodec
from server.socket_server import SocketServer
from shared.protocol import (
    HEADER,
    MAX_DATAGRAM,
    MessageType,
    Packet,
    ProtocolError,
    peek_session_id,
)

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
    certs = tmp_path / "tls"
    create_certificates(certs)
    tls = server_context(certs / "server.pem", certs / "server.key")
    tcp = SocketServer(host="127.0.0.1", port=0, udp_port=0, tls_context=tls)
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
            tls_context=client_context(certs / "ca.pem"),
            https_context=tls,
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
        for name in ("tls", "other", "wrong-ca"):
            path = tmp_path / name
            if path.exists():
                shutil.rmtree(path)


def api(http, route, body=None, token=None, *, binary=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Connect-Session"] = token
    data = None if body is None else json.dumps(body).encode()
    with urlopen(
        Request(f"https://127.0.0.1:{http.server_port}" + route, data, headers),
        timeout=20,
        context=http.tls_context,
    ) as response:
        content = response.read()
    return content if binary else json.loads(content)


def login(tcp, http, username):
    raw = socket.create_connection(tcp.server_socket.getsockname(), timeout=5)
    with http.tls_context.wrap_socket(raw, server_hostname="127.0.0.1") as sock:
        assert sock.version() in {"TLSv1.2", "TLSv1.3"}
        sock.sendall(b"HELLO2\n")
        assert read_line(sock) == b"WELCOME2\n"
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
    assert not any(
        secret in json.dumps(result)
        for secret in ('"c2s"', '"s2c"', '"ticket"', '"key"')
    )
    wait(
        lambda: any(
            e["type"] == "files.changed" and e["data"]["state"] == "ready"
            for _, e in session.events
        )
    )
    # Actual P2 allocated a relay peer; no test code provisions a ticket.
    assert username in tcp.file_relay._usernames
    assert session.crypto is not None and session.files.client.ticket.version == 2
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


def test_registration_https_then_login_and_chat(integrated):
    tcp, http = integrated
    username = "web-Đức"
    body = dict(username=username, password=PASSWORD)
    assert api(http, "/api/register", body) == {"status": "REGISTER_SUCCESS"}
    assert not http.sessions
    assert tcp.session_manager.get_session(username) is None
    assert username not in tcp.file_relay._usernames
    assert api(http, "/api/register", body) == {"status": "REGISTER_FAILED"}
    for invalid in (
        dict(username="  ", password=PASSWORD),
        dict(username=3, password=PASSWORD),
        dict(username="invalid", password=""),
        dict(username="invalid", password=None),
        dict(username="Đ" * 1100, password=PASSWORD),
    ):
        with pytest.raises(HTTPError) as error:
            api(http, "/api/register", invalid)
        assert error.value.code == 400
        response = json.loads(error.value.read())
        assert isinstance(response["error"], str)
        assert PASSWORD not in json.dumps(response)
    assert not http.sessions
    result = api(
        http,
        "/api/connect",
        dict(sessionId=str(uuid.uuid4()), **body),
    )
    a_token, a = result["token"], http.sessions[result["token"]]
    assert a.connected and a.crypto
    b_token, b = login(tcp, http, "existing-bob")
    send(http, a_token, a, "Đăng ký Web rồi chat")
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "Đăng ký Web rồi chat"
            for _, e in b.events
        )
    )
    send(http, b_token, b, "Đăng nhập cũ trả lời", a.username)
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "Đăng nhập cũ trả lời"
            for _, e in a.events
        )
    )


def test_registration_rejects_bad_ca_without_creating_account(integrated, tmp_path):
    tcp, http = integrated
    trusted = http.tls_context
    create_certificates(tmp_path / "wrong-ca")
    http.tls_context = client_context(tmp_path / "wrong-ca/ca.pem")
    try:
        with pytest.raises(HTTPError) as error:
            # Browser still trusts HTTPS; only the bridge-to-P2 CA is wrong.
            request = Request(
                f"https://127.0.0.1:{http.server_port}/api/register",
                json.dumps(dict(username="bad-ca", password=PASSWORD)).encode(),
                {"Content-Type": "application/json"},
            )
            urlopen(request, timeout=20, context=trusted)
        assert error.value.code == 503
        assert PASSWORD not in error.value.read().decode()
        assert "bad-ca" not in tcp.auth_manager.users
        assert not http.sessions
    finally:
        http.tls_context = trusted


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
            f"https://127.0.0.1:{http.server_port}/api/files/upload?{query}",
            payload,
            {
                "Content-Type": "application/octet-stream",
                "X-Connect-Session": sender_token,
            },
        )
        with urlopen(request, timeout=20, context=http.tls_context) as response:
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


def test_live_ciphertext_fault_retry_and_replay(
    integrated, tmp_path, monkeypatch, record_property
):
    tcp, http = integrated
    a_token, a = login(tcp, http, "wire-alice")
    b_token, b = login(tcp, http, "wire-bob")
    marker = b"PRIVATE-FILE-PLAINTEXT-NOT-ON-WIRE!"
    payload = marker * 2048
    raw, messages, rejected = [], [], []
    original_decode, original_deliver = (
        PacketCodec.decode,
        tcp.message_router.send_to_client,
    )
    original_encode, nonces, encodings = PacketCodec.encode, set(), []

    def encode(codec, packet):
        data = original_encode(codec, packet)
        identity = (codec.context.tx_aad, data[HEADER.size : HEADER.size + 12])
        assert identity not in nonces
        nonces.add(identity)
        encodings.append((packet.kind, packet.sequence, codec.context.tx_aad))
        return data

    def decode(codec, data):
        raw.append(data)
        try:
            return original_decode(codec, data)
        except ProtocolError:
            rejected.append(True)
            raise

    def deliver(username, data, **options):
        value = json.loads(data)
        if value.get("type") in {"UNICAST", "BROADCAST"}:
            assert isinstance(value["message"], dict) and value["message"]["v"] == 2
            messages.append(value)
        return original_deliver(username, data, **options)

    monkeypatch.setattr(PacketCodec, "decode", decode)
    monkeypatch.setattr(PacketCodec, "encode", encode)
    monkeypatch.setattr(tcp.message_router, "send_to_client", deliver)
    original_send = tcp.file_relay._send_datagram
    dropped, held = set(), []

    def faults(data, endpoint):
        kind, sequence = data[5], HEADER.unpack_from(data)[5]
        if kind in {MessageType.ACK, MessageType.COMPLETE} and kind not in dropped:
            dropped.add(kind)
            return
        if kind == MessageType.DATA and kind not in dropped:
            dropped.add(kind)
            corrupt = bytearray(data[:-16])
            corrupt[HEADER.size + 12] ^= 1
            key = tcp.file_relay._peers[peek_session_id(data)].ticket.key
            original_send(
                bytes(corrupt) + hmac.digest(key, corrupt, "sha256")[:16], endpoint
            )
            return  # Valid HMAC, invalid GCM tag; recover by a fresh-nonce retry.
        if kind == MessageType.DATA and sequence == 4 and not held:
            held.append((data, endpoint))
            return
        if kind == MessageType.DATA and sequence == 2 and "aad" not in dropped:
            dropped.add("aad")
            corrupt = bytearray(data[:-16])
            corrupt[38:42] = (3).to_bytes(4, "big")
            key = tcp.file_relay._peers[peek_session_id(data)].ticket.key
            original_send(
                bytes(corrupt) + hmac.digest(key, corrupt, "sha256")[:16], endpoint
            )
            return
        original_send(data, endpoint)
        if kind == MessageType.DATA and sequence == 5 and held:
            original_send(*held[0])
            original_send(
                *held[0]
            )  # Exact replay on the real UDP path must be dropped.

    monkeypatch.setattr(tcp.file_relay, "_send_datagram", faults)
    send(http, a_token, a, "private chat wire marker", b.username)
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "private chat wire marker"
            for _, e in b.events
        )
    )
    send(http, b_token, b, "common chat wire marker")
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "common chat wire marker"
            for _, e in a.events
        )
    )
    info = dict(
        requestId=str(uuid.uuid4()),
        transferId=str(uuid.uuid4()),
        conversationId="private",
        recipient=b.username,
        name="wire.bin",
    )
    assert a.files.upload(info, len(payload), io.BytesIO(payload))
    wait(lambda: bool(b.files.records))
    wire = next(iter(b.files.records))
    assert api(http, "/api/files/accept", dict(transferId=wire), b_token)["accepted"]
    wait(
        lambda: a.files.records[info["transferId"]]["data"]["status"] == "completed",
        timeout=30,
    )
    wait(lambda: b.files.records[wire]["data"]["status"] == "completed")
    actual = api(http, "/api/files/" + wire, token=b_token, binary=True)
    assert (
        actual == payload
        and hashlib.sha256(actual).digest() == hashlib.sha256(payload).digest()
    )
    assert (
        rejected
        and messages
        and all(marker not in frame and len(frame) <= MAX_DATAGRAM for frame in raw)
    )
    assert (
        len(b.files.records) == 1
        and len(list(b.files.downloads.rglob("wire.bin"))) == 1
    )
    # Retries must encrypt afresh; received exact duplicates are deliberately present.
    assert len(encodings) == len(nonces) > 10
    assert len(encodings) > len(set(encodings)), (
        "Lost ACK/COMPLETE must exercise fresh-nonce retries"
    )
    record_property("encryptedUdpFrames", len(raw))
    record_property("rejectedTamperOrReplay", len(rejected))
    record_property("plaintextHashMatch", True)


@pytest.mark.parametrize("bad", ["ca", "hostname", "v1", "plaintext"])
def test_live_rejects_bad_certificate_and_old_client(integrated, tmp_path, bad):
    tcp, http = integrated
    context = http.tls_context
    if bad == "ca":
        create_certificates(tmp_path / "other")
        context = client_context(tmp_path / "other/ca.pem")
    raw = socket.create_connection(tcp.server_socket.getsockname(), timeout=3)
    if bad == "plaintext":
        with raw:
            raw.sendall(b"HELLO\n")
            raw.shutdown(socket.SHUT_WR)
            try:
                assert b"WELCOME" not in raw.recv(1024)
            except ConnectionResetError:
                pass
    elif bad in {"ca", "hostname"}:
        import ssl

        with pytest.raises(ssl.SSLCertVerificationError):
            context.wrap_socket(
                raw,
                server_hostname="wrong.invalid" if bad == "hostname" else "127.0.0.1",
            )
        raw.close()
    else:
        with context.wrap_socket(raw, server_hostname="127.0.0.1") as sock:
            sock.sendall(b"HELLO\n")
            assert read_line(sock) == b"ERROR\n"


@pytest.mark.parametrize("fault", ["key", "tag", "aad"])
def test_live_wrong_chat_key_and_reconnect_revoke(integrated, monkeypatch, fault):
    import base64

    tcp, http = integrated
    token, a = login(tcp, http, "reconnect-alice")
    old_chat, old_files = a.crypto, a.files
    ticket = old_files.client.ticket
    old_packet = old_files.client.codec.encode(
        Packet(MessageType.PING, ticket.session_id)
    )
    sid = str(old_chat.sid)
    statuses = []
    original = tcp.message_router.send_to_client

    def observe(username, data):
        statuses.append(json.loads(data).get("status"))
        return original(username, data)

    monkeypatch.setattr(tcp.message_router, "send_to_client", observe)
    bad = new_material()
    bad["session_id"] = sid
    source = Context(bad) if fault == "key" else old_chat
    forged = source.encrypt_text(
        "must not route",
        chat_aad("UNICAST" if fault == "aad" else "BROADCAST", a.username, None),
    )
    if fault == "tag":
        encoded = base64.b64decode(forged["data"])
        forged["data"] = base64.b64encode(
            encoded[:-1] + bytes([encoded[-1] ^ 1])
        ).decode()
    wait(lambda: a.pending is None)
    with a.condition:
        a.sock.sendall(
            (json.dumps(dict(action="BROADCAST", message=forged)) + "\n").encode()
        )
    wait(lambda: not a.connected)
    assert "SECURITY_FAILED" in statuses and "BROADCAST_SUCCESS" not in statuses
    wait(lambda: a.username not in tcp.file_relay._usernames)
    assert old_files.closed.wait(5)
    with pytest.raises(SecurityError):
        old_chat.seal(b"revoked")
    result = api(
        http,
        "/api/connect",
        dict(sessionId=str(uuid.uuid4()), username=a.username, password=PASSWORD),
    )
    replacement = http.sessions[result["token"]]
    wait(lambda: replacement.files is not None)
    assert str(replacement.crypto.sid) != sid
    assert replacement.files.client.ticket.session_id != ticket.session_id
    assert replacement.files.client.ticket.c2s != ticket.c2s
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as replay:
        replay.settimeout(0.2)
        replay.sendto(old_packet, tcp.file_relay.address)
        with pytest.raises(socket.timeout):
            replay.recvfrom(MAX_DATAGRAM)
    assert ticket.session_id not in tcp.file_relay._peers
    send(http, result["token"], replacement, "chat after new keys")


def test_bridge_reports_ca_failure_without_fallback(integrated, tmp_path):
    from bridge import Session

    tcp, _ = integrated
    create_certificates(tmp_path / "wrong-ca")
    session = Session(
        str(uuid.uuid4()), tls_context=client_context(tmp_path / "wrong-ca/ca.pem")
    )
    session.open(tcp.server_socket.getsockname(), "not-sent", "not-sent")
    assert not session.connected and session.crypto is None
    assert session.poll(0)["events"][-1]["data"]["error"]["code"] == "TLS_VERIFY_FAILED"


def test_secure_chat_frame_and_plaintext_limit(integrated, monkeypatch):
    tcp, http = integrated
    token, a = login(tcp, http, "limit-alice")
    _, b = login(tcp, http, "limit-bob")
    send(http, token, a, "x" * 4000, b.username)
    wait(
        lambda: any(
            e["type"] == "message.upsert" and len(e["data"]["text"]) == 4000
            for _, e in b.events
        )
    )
    statuses, original = [], tcp.message_router.send_to_client

    def observe(username, data, **options):
        statuses.append(json.loads(data).get("status"))
        return original(username, data, **options)

    monkeypatch.setattr(tcp.message_router, "send_to_client", observe)
    wait(lambda: a.pending is None)
    message = a.crypto.encrypt_text(
        "x" * 4001, chat_aad("UNICAST", a.username, b.username)
    )
    with a.condition:
        a.sock.sendall(
            (
                json.dumps(
                    dict(action="UNICAST", recipient=b.username, message=message)
                )
                + "\n"
            ).encode()
        )
    wait(lambda: "INVALID_REQUEST" in statuses)
    assert b.connected and not any(
        e["type"] == "message.upsert" and len(e["data"]["text"]) > 4000
        for _, e in b.events
    )
