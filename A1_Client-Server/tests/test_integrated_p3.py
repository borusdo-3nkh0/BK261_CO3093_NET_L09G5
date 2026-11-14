"""Current checkout only: real P2 tickets, P1 UDP and P3 HTTP (no fixture tickets)."""

import hashlib
import io
import json
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from tests.test_security_live import ROOT as ROOT
from tests.test_security_live import api, login, send, wait
from tests.test_security_live import integrated as integrated


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
