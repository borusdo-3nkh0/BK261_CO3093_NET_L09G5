"""Remaining Windows acceptance gaps; fault hooks affect tests only."""

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from http.client import HTTPSConnection
from urllib.parse import urlencode

import pytest

from bridge_files import MAX_FILE
from shared.protocol import HEADER
from shared.protocol import MessageType as Kind
from tests.test_integrated_p3 import ROOT, api, login, send, wait
from tests.test_integrated_p3 import integrated as integrated


def meta(recipient, name="edge.bin"):
    return dict(
        requestId=str(uuid.uuid4()),
        transferId=str(uuid.uuid4()),
        conversationId="private",
        recipient=recipient,
        name=name,
    )


def upload(sender, receiver, path):
    info = meta(receiver.username, path.name)
    with path.open("rb") as stream:
        assert sender.files.upload(info, path.stat().st_size, stream)
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
    return info["transferId"], wire


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.mark.parametrize(
    "phase", [Kind.DATA, Kind.FIN, Kind.COMPLETE], ids=["DATA", "FIN", "COMPLETE"]
)
def test_disconnect_at_wire_phase(
    integrated, tmp_path, monkeypatch, phase, record_property
):
    tcp, http = integrated
    a_token, a = login(tcp, http, "edge-alice")
    b_token, b = login(tcp, http, "edge-bob")
    c_token, c = login(tcp, http, "edge-carol")
    _, d = login(tcp, http, "edge-david")
    initial_events = [e for _, e in a.events]
    reached = threading.Event()
    relay = tcp.file_relay
    original = relay._send_datagram

    def pause(data, endpoint):
        fields = HEADER.unpack_from(data)
        if fields[2] == phase and (phase != Kind.DATA or fields[5] >= 16):
            reached.set()
            return  # Drop at a deterministic wire boundary without blocking relay I/O.
        original(data, endpoint)

    monkeypatch.setattr(relay, "_send_datagram", pause)
    source = tmp_path / "phase.bin"
    source.write_bytes(bytes(range(256)) * 4096)
    transfer_id, wire = upload(a, b, source)
    assert api(http, "/api/files/accept", {"transferId": wire}, b_token)["accepted"]
    assert reached.wait(10), "Requested DATA/FIN/COMPLETE boundary not observed"
    wait(lambda: a.files.records[transfer_id]["data"]["transferredBytes"] > 0)
    assert a.files.records[transfer_id]["data"]["status"] != "completed"
    a_files, b_files = a.files, b.files
    if phase == Kind.COMPLETE:
        # Receiver may legitimately finish; sender has not received COMPLETE.
        wait(lambda: b_files.records[wire]["data"]["status"] == "completed")
        assert digest(b_files.records[wire]["path"]) == digest(source)
        api(http, "/api/disconnect", {}, a_token)
        # Backend records stop on close; the real UI reducer maps pending to unknown.
        replay = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                """
import fs from 'node:fs';
import {createState, applyEvent} from './web/js/state.js';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const state=createState({conversations:input.conversations});
// p2-http.js emits connecting locally before consuming bridge events.
const sessionId=input.events[0].sessionId;
applyEvent(state,{eventId:'adapter-local-connecting',sessionId,type:'connection.changed',
  data:{sessionId,revision:1,mode:'live',state:'connecting',selfUserId:null,error:null}});
for(const event of input.events) applyEvent(state,event);
console.log(state.transfers.get(input.id).status);
""",
            ],
            input=json.dumps(
                dict(
                    id=transfer_id,
                    events=initial_events + [e for _, e in a.events],
                    conversations=[
                        dict(conversationId="global", kind="global", participantIds=[]),
                        dict(
                            conversationId="private",
                            kind="private",
                            participantIds=[a.username, b.username],
                        ),
                    ],
                )
            ),
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        assert replay.returncode == 0, replay.stderr
        assert replay.stdout.strip() == "unknown"
    else:
        assert b_files.records[wire]["data"]["status"] != "completed"
        assert any(p.is_file() for p in b_files.downloads.rglob("*")), (
            "Partial file must exist before disconnect"
        )
        api(http, "/api/disconnect", {}, b_token)
        wait(
            lambda: (
                a_files.records[transfer_id]["data"]["status"] in {"failed", "unknown"}
            )
        )
        assert b_files.closed.wait(5) and not b_files.root.exists()
        wait(lambda: not a_files.active and a_files.used_bytes == 0)
        assert not list(a_files.root.glob("upload-*"))
    assert not any(
        e["type"] == "transfer.upsert"
        and e["data"]["transferId"] == transfer_id
        and e["data"]["status"] == "completed"
        for _, e in a.events
    )
    send(http, c_token, c, "Other clients survive " + phase.name, d.username)
    wait(
        lambda: any(
            e["type"] == "message.upsert"
            and e["data"]["text"] == "Other clients survive " + phase.name
            for _, e in d.events
        )
    )
    for token, files in ((a_token, a_files), (b_token, b_files)):
        if not files.stopped.is_set():
            api(http, "/api/disconnect", {}, token)
        assert files.closed.wait(5) and not files.root.exists()
    record_property("phase", phase.name)
    record_property("senderCompleted", False)
    record_property("otherClientsChat", True)
    record_property("cleanup", True)


@pytest.mark.large
def test_large_exact_limit_admission_and_oversize(integrated, tmp_path):
    tcp, http = integrated
    a_token, a = login(tcp, http, "large-alice")
    b_token, b = login(tcp, http, "large-bob")
    source = tmp_path / "exact-limit.bin"
    with source.open("wb") as stream:
        stream.truncate(MAX_FILE)
    transfer_id, wire = upload(a, b, source)
    assert a.files.used_bytes == MAX_FILE
    assert a.files.records[transfer_id]["path"].stat().st_size == MAX_FILE
    assert api(http, "/api/files/reject", {"transferId": wire}, b_token)["accepted"]
    wait(lambda: a.files.active is None and a.files.used_bytes == 0)
    assert not list(a.files.root.glob("upload-*"))
    before = set(a.files.records)
    query = urlencode(meta(b.username, "over-limit.bin"))
    connection = HTTPSConnection(
        "127.0.0.1", http.server_port, timeout=5, context=http.tls_context
    )
    try:
        connection.putrequest("POST", "/api/files/upload?" + query)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("X-Connect-Session", a_token)
        connection.putheader("Content-Length", str(MAX_FILE + 1))
        connection.endheaders()
        assert connection.getresponse().status == 400
    finally:
        connection.close()
    assert set(a.files.records) == before and a.files.used_bytes == 0
    assert not list(a.files.root.glob("upload-*"))


@pytest.mark.large
def test_large_file_hash_and_cleanup(integrated, tmp_path, record_property):
    mib = int(os.environ.get("CONNECT_LARGE_MIB", "32"))
    assert mib in {32, 256}
    tcp, http = integrated
    a_token, a = login(tcp, http, "large-alice")
    b_token, b = login(tcp, http, "large-bob")
    source = tmp_path / f"large-{mib}.bin"
    block = bytes(range(256)) * 4096
    with source.open("wb") as stream:
        for _ in range(mib):
            stream.write(block)
    expected = digest(source)
    started = time.monotonic()
    transfer_id, wire = upload(a, b, source)
    files_a, files_b = a.files, b.files
    assert api(http, "/api/files/accept", {"transferId": wire}, b_token)["accepted"]
    last_poll = 0.0

    def terminal():
        nonlocal last_poll
        if time.monotonic() - last_poll >= 2:
            # Real browser clients poll; keep the 90s abandoned-session guard intact.
            for token, session in ((a_token, a), (b_token, b)):
                api(http, f"/api/events?after={session.sequence - 1}", token=token)
                assert session.connected, "Live client unexpectedly disconnected"
            last_poll = time.monotonic()
        return files_a.records[transfer_id]["data"]["status"] in {
            "completed",
            "failed",
            "unknown",
        }

    try:
        wait(terminal, timeout=310)
        state = files_a.records[transfer_id]["data"]["status"]
        record_property("senderStatus", state)
        record_property(
            "transferredBytes", files_a.records[transfer_id]["data"]["transferredBytes"]
        )
        assert state == "completed", (
            f"{mib} MiB transfer ended {state}; production P1 default send timeout is 300s"
        )
        wait(lambda: files_b.records[wire]["data"]["status"] == "completed")
        assert digest(files_b.records[wire]["path"]) == expected
        wait(lambda: files_a.active is None and files_a.used_bytes == 0)
        assert not list(files_a.root.glob("upload-*"))
        record_property("sha256", expected)
    finally:
        record_property("sizeMiB", mib)
        record_property("elapsedSeconds", round(time.monotonic() - started, 3))
        for token, files in ((a_token, files_a), (b_token, files_b)):
            api(http, "/api/disconnect", {}, token)
            assert files.closed.wait(5) and not files.root.exists()
        record_property("cleanup", True)


@pytest.mark.load
def test_four_clients_chat_during_file(integrated, tmp_path, record_property):
    tcp, http = integrated
    _, a = login(tcp, http, "load-alice")
    b_token, b = login(tcp, http, "load-bob")
    c_token, c = login(tcp, http, "load-carol")
    _, d = login(tcp, http, "load-david")
    source = tmp_path / "concurrent.bin"
    source.write_bytes(bytes(range(256)) * 8192)
    transfer_id, wire = upload(a, b, source)
    started = time.monotonic()
    assert api(http, "/api/files/accept", {"transferId": wire}, b_token)["accepted"]
    wait(
        lambda: (
            a.files.records[transfer_id]["data"]["status"] == "transferring"
            and 0
            < a.files.records[transfer_id]["data"]["transferredBytes"]
            < source.stat().st_size
        )
    )
    overlap = []
    for n in range(5):
        text = "Concurrent common " + str(n)
        send(http, c_token, c, text)
        wait(
            lambda: all(
                any(
                    e["type"] == "message.upsert" and e["data"]["text"] == text
                    for _, e in other.events
                )
                for other in (a, b, d)
            ),
            timeout=5,
        )
        with a.files.lock:
            progress = dict(a.files.records[transfer_id]["data"])
        assert progress["status"] == "transferring"
        assert 0 < progress["transferredBytes"] < progress["totalBytes"]
        overlap.append(
            dict(
                message=text,
                receivers=3,
                status=progress["status"],
                transferredBytes=progress["transferredBytes"],
                totalBytes=progress["totalBytes"],
            )
        )
    wait(
        lambda: a.files.records[transfer_id]["data"]["status"] == "completed",
        timeout=25,
    )
    wait(lambda: b.files.records[wire]["data"]["status"] == "completed")
    assert digest(b.files.records[wire]["path"]) == digest(source)
    for other in (a, b, d):
        texts = [
            e["data"]["text"] for _, e in other.events if e["type"] == "message.upsert"
        ]
        assert all(texts.count("Concurrent common " + str(n)) == 1 for n in range(5))
    record_property("clients", 4)
    record_property("receivedWhileTransferring", json.dumps(overlap))
    record_property("elapsedSeconds", round(time.monotonic() - started, 3))
