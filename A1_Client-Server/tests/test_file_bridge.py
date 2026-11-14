import io
import json
import queue
import threading
import time
import uuid
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from bridge import BridgeServer, Session, read_line
from bridge_files import ACCEPT_TIMEOUT, MAX_FILE, FileService


def wait(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "Timed out"


def metadata(**changes):
    return dict(
        requestId=str(uuid.uuid4()),
        transferId=str(uuid.uuid4()),
        conversationId="private-b",
        recipient="bob",
        name="dữ-liệu.bin",
        **changes,
    )


class FakeClient:
    def __init__(self, *_):
        self.events, self.received_files = queue.Queue(256), queue.Queue()
        self.calls = []
        self.release = threading.Event()
        self.fail = False

    def start(self):
        return self

    def send_file(self, path, recipient):
        wire = str(uuid.uuid4())
        size = Path(path).stat().st_size
        self.calls.append((wire, Path(path).read_bytes()))
        self.events.put(
            dict(
                type="file_sending",
                transfer_id=wire,
                filename=Path(path).name,
                recipient=recipient,
                size=size,
            )
        )
        self.release.wait(3)
        self.events.put(
            dict(
                type="file_progress",
                transfer_id=wire,
                direction="send",
                bytes=size,
                total=size,
            )
        )
        if self.fail:
            self.events.put(
                dict(type="file_failed", transfer_id=wire, reason="REJECTED")
            )
            raise RuntimeError("secret path must not reach UI")
        self.events.put(dict(type="file_sent", transfer_id=wire, size=size))
        return SimpleNamespace(
            transfer_id=wire, size=size, filename=Path(path).name, recipient=recipient
        )

    def accept_file(self, wire):
        pass

    def reject_file(self, wire, reason="REJECTED"):
        pass

    def close(self):
        self.release.set()


@pytest.fixture
def service(tmp_path):
    events = []
    files = FileService(
        "alice",
        FakeClient,
        {},
        ("127.0.0.1", 1),
        tmp_path,
        lambda kind, data: events.append((kind, data)),
    )
    files.start()
    yield files, events
    files.close_async()
    assert files.closed.wait(5)
    assert not files.root.exists()


def test_exclusive_correlation_with_identical_metadata_and_delayed_events(service):
    files, events = service
    first, second = metadata(), metadata()
    files.upload(first, 3, io.BytesIO(b"one"))
    files.upload(second, 3, io.BytesIO(b"two"))
    wait(lambda: len(files.client.calls) == 1)
    time.sleep(0.03)
    assert len(files.client.calls) == 1
    files.client.release.set()
    wait(lambda: files.records[second["transferId"]]["data"]["status"] == "completed")
    wait(lambda: files.active is None)
    for meta, call in zip((first, second), files.client.calls, strict=True):
        assert files.wire_ids[call[0]] is files.records[meta["transferId"]]
        assert call[0] != meta["transferId"]
    assert [c[1] for c in files.client.calls] == [b"one", b"two"]
    assert files.used_bytes == 0
    assert not list(files.root.glob("upload-*"))
    assert not any("secret" in str(event) for event in events)


def test_failure_then_identical_retry_does_not_reuse_wire_context(service):
    files, _ = service
    first = metadata()
    files.client.fail = True
    files.client.release.set()
    files.upload(first, 1, io.BytesIO(b"a"))
    wait(lambda: files.active is None and len(files.client.calls) == 1)
    assert files.records[first["transferId"]]["data"]["status"] == "rejected"
    files.client.fail = False
    second = metadata()
    files.upload(second, 1, io.BytesIO(b"b"))
    wait(lambda: files.records[second["transferId"]]["data"]["status"] == "completed")
    assert (
        files.records[first["transferId"]]["wire_id"]
        != files.records[second["transferId"]]["wire_id"]
    )


def test_full_progress_without_complete_never_marks_success(service):
    files, _ = service
    meta = metadata()
    files.upload(meta, 1, io.BytesIO(b"x"))
    wait(lambda: files.records[meta["transferId"]]["wire_id"] is not None)
    wire = files.records[meta["transferId"]]["wire_id"]
    files.client.events.put(
        dict(type="file_progress", transfer_id=wire, direction="send", bytes=1, total=1)
    )
    wait(lambda: files.records[meta["transferId"]]["data"]["transferredBytes"] == 1)
    assert files.records[meta["transferId"]]["data"]["status"] == "transferring"


def test_correlation_mismatch_disables_service_and_cleans_staging(service):
    files, events = service
    files.client.events.put(
        dict(
            type="file_sending",
            transfer_id=str(uuid.uuid4()),
            filename="foreign",
            recipient="bob",
            size=1,
        )
    )
    assert files.closed.wait(5)
    assert files.stopped.is_set() and not files.root.exists()
    assert events[-1][0] == "files.changed" and events[-1][1]["state"] == "unavailable"


def test_cleanup_survives_client_close_error(service):
    files, _ = service

    def broken_close():
        raise OSError("test-only client close error")

    files.client.close = broken_close
    files.close_async()
    assert files.closed.wait(5) and not files.root.exists()


def test_missing_final_confirmation_is_unknown_not_completed(service):
    files, _ = service

    def timed_out(*_):
        raise TimeoutError("FIN retry limit exceeded")

    files.client.send_file = timed_out
    meta = metadata()
    files.upload(meta, 0, io.BytesIO())
    wait(lambda: files.records[meta["transferId"]]["data"]["status"] == "unknown")
    wait(lambda: files.active is None)
    assert files.used_bytes == 0 and not list(files.root.glob("upload-*"))
    assert files.records[meta["transferId"]]["data"]["sendPending"] is False


def test_accept_timeout_waits_for_worker_exit_then_allows_next_file(service):
    files, _ = service
    release = threading.Event()
    original = files.client.send_file

    def timeout_after_event(path, recipient):
        wire = str(uuid.uuid4())
        files.client.calls.append((wire, Path(path).read_bytes()))
        files.client.events.put(
            dict(
                type="file_sending",
                transfer_id=wire,
                filename=Path(path).name,
                recipient=recipient,
                size=1,
            )
        )
        files.client.events.put(
            dict(
                type="file_failed",
                transfer_id=wire,
                reason="OFFER retry limit exceeded",
            )
        )
        assert release.wait(3)
        raise RuntimeError("OFFER retry limit exceeded")

    files.client.send_file = timeout_after_event
    first, second = metadata(), metadata()
    try:
        files.upload(first, 1, io.BytesIO(b"a"))
        wait(lambda: files.active and files.active.get("failure_reason"))
        files.active[
            "done"
        ].set()  # Even an early done signal cannot release a live worker.
        files.upload(second, 1, io.BytesIO(b"b"))
        time.sleep(0.05)
        data = files.records[first["transferId"]]["data"]
        assert files.worker.is_alive() and len(files.client.calls) == 1
        assert data["status"] == "awaiting_acceptance" and data["sendPending"] is True
        files.client.send_file = original
        files.client.release.set()
        release.set()
        wait(
            lambda: files.records[second["transferId"]]["data"]["status"] == "completed"
        )
        assert data["status"] == "failed" and data["sendPending"] is False
        assert data["error"] == {
            "code": "ACCEPT_TIMEOUT",
            "userMessage": ACCEPT_TIMEOUT,
        }
        assert data["transferredBytes"] == 0
        assert files.used_bytes == 0 and not list(files.root.glob("upload-*"))
    finally:
        release.set()


@pytest.mark.parametrize(
    "reason,progress,expected",
    [
        ("OFFER retry limit exceeded", None, "failed"),
        ("OFFER retry limit exceeded", 0, "unknown"),
        ("FIN retry limit exceeded", 1, "unknown"),
        ("DATA retry limit exceeded", 0, "unknown"),
        ("Transfer deadline exceeded", None, "unknown"),
    ],
)
def test_send_failure_classification_uses_p1_reason_and_phase(
    service, reason, progress, expected
):
    files, _ = service

    def fail(path, recipient):
        wire = str(uuid.uuid4())
        files.client.events.put(
            dict(
                type="file_sending",
                transfer_id=wire,
                filename=Path(path).name,
                recipient=recipient,
                size=1,
            )
        )
        if progress is not None:
            files.client.events.put(
                dict(
                    type="file_progress",
                    transfer_id=wire,
                    direction="send",
                    bytes=progress,
                    total=1,
                )
            )
        files.client.events.put(
            dict(type="file_failed", transfer_id=wire, reason=reason)
        )
        raise RuntimeError(reason)

    files.client.send_file = fail
    meta = metadata()
    files.upload(meta, 1, io.BytesIO(b"x"))
    wait(lambda: files.records[meta["transferId"]]["data"]["status"] == expected)
    data = files.records[meta["transferId"]]["data"]
    assert data["sendPending"] is False and files.active is None
    assert (data["error"]["code"] == "ACCEPT_TIMEOUT") == (expected == "failed")


@pytest.mark.parametrize(
    "reason,accepted,code",
    [
        ("TRANSFER_EXPIRED", False, "ACCEPT_TIMEOUT"),
        ("SENDER_FAILED", False, "FILE_FAILED"),
        ("TRANSFER_EXPIRED", True, "FILE_FAILED"),
    ],
)
def test_receiver_does_not_invent_sender_accept_timeout(
    service, reason, accepted, code
):
    files, _ = service
    wire = str(uuid.uuid4())
    with files.lock:
        files._event(
            dict(
                type="file_offer",
                transfer_id=wire,
                sender="bob",
                filename="wait.bin",
                size=1,
                sha256="a" * 64,
            )
        )
        if accepted:
            files.decide(wire, True)
        files._event(dict(type="file_failed", transfer_id=wire, reason=reason))
    data = files.records[wire]["data"]
    assert data["status"] == "failed" and data["error"]["code"] == code
    if code == "ACCEPT_TIMEOUT":
        assert data["error"]["userMessage"] == ACCEPT_TIMEOUT
    assert files.used_bytes == 0


@pytest.mark.parametrize(
    "change,length",
    [
        ({"name": "../escape"}, 1),
        ({"name": "CON"}, 1),
        ({"name": "Đ" * 65}, 1),
        ({}, MAX_FILE + 1),
        ({}, -1),
        ({"recipient": "alice"}, 1),
        ({"conversationId": "global"}, 1),
    ],
)
def test_upload_validation_does_not_read_or_create_temp(service, change, length):
    files, _ = service
    meta = metadata()
    meta.update(change)

    class Unreadable:
        def read(self, _):
            pytest.fail("Invalid upload read body")

    with pytest.raises(ValueError):
        files.upload(meta, length, Unreadable())
    assert files.used_bytes == 0 and not list(files.root.iterdir())


def test_truncated_upload_quota_and_duplicates(service):
    files, _ = service
    meta = metadata()
    with pytest.raises(ValueError, match="chưa đủ"):
        files.upload(meta, 3, io.BytesIO(b"x"))
    assert files.used_bytes == 0 and not list(files.root.iterdir())
    with pytest.raises(ValueError, match="sử dụng"):
        files.upload(meta, 3, io.BytesIO(b"xxx"))
    files.used_bytes = MAX_FILE
    with pytest.raises(ValueError, match="hạn mức"):
        files.upload(metadata(), 1, io.BytesIO(b"x"))
    files.used_bytes = 0


def test_disconnect_during_upload_cleans_only_private_root(service):
    files, _ = service

    class Interrupted:
        def read(self, _):
            files.close_async()
            return b"x"

    with pytest.raises(ValueError):
        files.upload(metadata(), 3, Interrupted())
    assert files.closed.wait(5) and not files.root.exists()


def test_receive_requires_accept_and_download_stays_in_own_session(service):
    files, events = service
    wire = str(uuid.uuid4())
    with files.lock:
        files._event(
            dict(
                type="file_offer",
                transfer_id=wire,
                sender="bob",
                filename="received.bin",
                size=1,
                sha256="a" * 64,
            )
        )
    assert events[-1][1]["status"] == "awaiting_acceptance"
    with pytest.raises(ValueError):
        with files.download(wire):
            pass
    assert files.decide(wire, True)
    with pytest.raises(ValueError):
        files.decide(wire, True)
    files.downloads.mkdir()
    path = files.downloads / "received.bin"
    path.write_bytes(b"x")
    result = SimpleNamespace(transfer_id=wire, path=path, size=1, sha256="a" * 64)
    with files.lock:
        files._received(result)
    with files.download(wire) as (stream, data):
        assert stream.read() == b"x" and data["downloadAvailable"]
    assert files.used_bytes == 1
    with pytest.raises(ValueError):
        with files.download(str(uuid.uuid4())):
            pass


def test_reject_does_not_reserve_disk(service):
    files, _ = service
    wire = str(uuid.uuid4())
    with files.lock:
        files._event(
            dict(
                type="file_offer",
                transfer_id=wire,
                sender="bob",
                filename="x",
                size=1,
                sha256="0" * 64,
            )
        )
    assert files.decide(wire, False)
    assert files.records[wire]["data"]["status"] == "rejected" and files.used_bytes == 0


@pytest.fixture
def file_http(tmp_path):
    with BridgeServer(("127.0.0.1", 0), ("127.0.0.1", 1), storage=tmp_path) as server:
        session = Session(str(uuid.uuid4()))
        session.username, session.connected = "alice", True
        files = FileService(
            "alice", FakeClient, {}, ("127.0.0.1", 1), tmp_path, session.file_publish
        )
        session.files = files
        files.start()
        server.sessions["test-token"] = session
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        yield server, session, files, f"http://127.0.0.1:{server.server_port}"
        server.shutdown()
        thread.join(2)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Connect-Session": "bad"},
        {"X-Connect-Session": "test-token", "Origin": "http://evil.invalid"},
    ],
)
def test_http_upload_rejects_unauthorized_before_staging(file_http, headers):
    server, _, files, _ = file_http
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    try:
        connection.putrequest("POST", "/api/files/upload?" + urlencode(metadata()))
        for name, value in {
            "Content-Type": "application/octet-stream",
            "Content-Length": "1",
            **headers,
        }.items():
            connection.putheader(name, value)
        # Reject from headers before reading a body; unread bytes can reset Windows TCP.
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == (403 if "Origin" in headers else 400)
        assert isinstance(json.loads(response.read())["error"], str)
    finally:
        connection.close()
    assert not files.records and files.used_bytes == 0


def test_http_binary_upload_and_no_static_access(file_http):
    _, _, files, base = file_http
    payload = bytes(range(256))
    request = Request(
        base + "/api/files/upload?" + urlencode(metadata()),
        data=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Connect-Session": "test-token",
        },
    )
    with urlopen(request, timeout=2) as response:
        assert json.load(response)["accepted"]
    wait(lambda: bool(files.client.calls))
    assert files.client.calls[0][1] == payload
    for path in ("/runtime/files/", "/../runtime/files/"):
        with pytest.raises(HTTPError):
            urlopen(base + path, timeout=2)


def test_received_result_cannot_publish_a_path_outside_download_root(service, tmp_path):
    files, _ = service
    wire = str(uuid.uuid4())
    with files.lock:
        files._event(
            dict(
                type="file_offer",
                transfer_id=wire,
                sender="bob",
                filename="safe.bin",
                size=1,
                sha256="a" * 64,
            )
        )
    files.decide(wire, True)
    foreign = tmp_path / "outside.bin"
    foreign.write_bytes(b"x")
    with files.lock, pytest.raises(ValueError, match="received file"):
        files._received(
            SimpleNamespace(transfer_id=wire, path=foreign, size=1, sha256="a" * 64)
        )
    assert files.records[wire]["data"]["status"] == "transferring"
    assert "downloadAvailable" not in files.records[wire]["data"]


def test_http_download_ownership_and_revoked_session(file_http, tmp_path):
    server, session, files, base = file_http
    wire = str(uuid.uuid4())
    with files.lock:
        files._event(
            dict(
                type="file_offer",
                transfer_id=wire,
                sender="bob",
                filename="nhận.bin",
                size=1,
                sha256="a" * 64,
            )
        )
    files.decide(wire, True)
    files.downloads.mkdir()
    path = files.downloads / "nhận.bin"
    path.write_bytes(b"x")
    with files.lock:
        files._received(
            SimpleNamespace(transfer_id=wire, path=path, size=1, sha256="a" * 64)
        )
    other = Session(str(uuid.uuid4()))
    other.username, other.connected = "carol", True
    other.files = FileService(
        "carol", FakeClient, {}, ("127.0.0.1", 1), tmp_path, other.file_publish
    )
    other.files.start()
    server.sessions["other-token"] = other
    request = Request(
        base + "/api/files/" + wire, headers={"X-Connect-Session": "test-token"}
    )
    with urlopen(request, timeout=2) as response:
        assert response.read() == b"x"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Content-Disposition"].startswith("attachment;")
    for token in ("other-token", "missing"):
        request = Request(
            base + "/api/files/" + wire, headers={"X-Connect-Session": token}
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 409
    session.end("disconnected")
    request = Request(
        base + "/api/files/" + wire, headers={"X-Connect-Session": "test-token"}
    )
    with pytest.raises(HTTPError):
        urlopen(request, timeout=2)


def test_file_session_unsupported_retains_tcp_and_no_ticket_event():
    import socket

    session = Session(str(uuid.uuid4()), FakeClient)
    session.username, session.connected = "alice", True
    session.sock, peer = socket.socketpair()
    try:
        session.refresh_files()
        assert json.loads(read_line(peer)) == {"action": "FILE_SESSION"}
        with session.condition:
            session.packet({"status": "INVALID_REQUEST"})
        assert session.connected and session.pending is None and session.files is None
        assert session.poll(0)["events"][-1]["data"]["state"] == "unavailable"
        session.refresh_files()
        assert session.pending is None
    finally:
        session.end("disconnected")
        peer.close()
