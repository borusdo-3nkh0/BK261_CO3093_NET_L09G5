"""Optional reference integration: real P1 UDP, no P2 or network simulation."""

import hashlib
import importlib.util
import io
import os
from pathlib import Path

import pytest

from bridge_files import FileService, load_p1
from tests.test_file_bridge import metadata, wait


@pytest.fixture
def p1_services(tmp_path, request):
    default = Path(__file__).resolve().parents[2] / "../MMT-P1/A1_Client-Server"
    root = Path(os.environ.get("CONNECT_P1_ROOT", default)).resolve()
    if not (root / "p1/client.py").is_file():
        if os.environ.get("CONNECT_REQUIRE_INTEGRATION") == "1":
            pytest.fail("Required P1 checkout is missing; set CONNECT_P1_ROOT")
        pytest.skip("Set CONNECT_P1_ROOT to run real P1 reference integration")
    factory = load_p1(root)
    from p1.relay import FileRelay

    mode = getattr(request, "param", None)
    if mode:
        spec = importlib.util.spec_from_file_location(
            "p1_reference_faults", root / "tests/test_udp_transfer.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        relay = module.FaultRelay(
            faults=mode == "faults", bad_hash=mode == "bad_hash"
        ).start()
    else:
        relay = FileRelay(port=0).start()
    events_a, events_b = [], []
    a = FileService(
        "alice",
        factory,
        relay.register_session("alice").to_dict(),
        relay.address,
        tmp_path,
        lambda k, d: events_a.append((k, d)),
    )
    b = FileService(
        "bob",
        factory,
        relay.register_session("bob").to_dict(),
        relay.address,
        tmp_path,
        lambda k, d: events_b.append((k, d)),
    )
    a.start()
    b.start()
    yield a, b, events_a, events_b
    for service in (a, b):
        service.close_async()
    for service in (a, b):
        assert service.closed.wait(5) and not service.root.exists()
    relay.close()


def test_real_p1_sequential_same_metadata_keeps_ids_and_hashes(p1_services):
    a, b, _, _ = p1_services
    payloads = [b"a" * 8192, b"b" * 8192]
    metas = [metadata(), metadata()]
    for meta, payload in zip(metas, payloads, strict=True):
        assert a.upload(meta, len(payload), io.BytesIO(payload))
    received = []
    for n, (meta, payload) in enumerate(zip(metas, payloads, strict=True), 1):
        wait(lambda: len(b.records) == n)
        pending = [
            r
            for r in b.records.values()
            if r["data"]["status"] == "awaiting_acceptance"
        ]
        assert len(pending) == 1
        wire = pending[0]["wire_id"]
        assert wire != meta["transferId"]
        # The receiver can observe OFFER before the sender UI pump runs.
        wait(lambda: wire in a.wire_ids)
        assert a.wire_ids[wire] is a.records[meta["transferId"]]
        assert a.records[meta["transferId"]]["data"]["status"] == "awaiting_acceptance"
        assert b.decide(wire, True)
        wait(lambda: a.records[meta["transferId"]]["data"]["status"] == "completed")
        wait(lambda: b.records[wire]["data"]["status"] == "completed")
        with b.download(wire) as (stream, _):
            actual = stream.read()
        assert (
            actual == payload
            and hashlib.sha256(actual).digest() == hashlib.sha256(payload).digest()
        )
        received.append(wire)
    assert len(set(received)) == 2
    wait(lambda: a.active is None)
    assert a.used_bytes == 0 and not list(a.root.glob("upload-*"))
    assert len({r["path"] for r in b.records.values()}) == 2


def test_real_p1_reject_then_empty_file_retry(p1_services):
    a, b, _, _ = p1_services
    meta = metadata()
    a.upload(meta, 0, io.BytesIO())
    wait(lambda: len(b.records) == 1)
    wire = next(iter(b.records))
    assert b.decide(wire, False)
    wait(lambda: a.records[meta["transferId"]]["data"]["status"] == "rejected")
    wait(lambda: a.active is None)
    retry = metadata()
    a.upload(retry, 0, io.BytesIO())
    wait(lambda: len(b.records) == 2)
    other = next(key for key in b.records if key != wire)
    assert b.decide(other, True)
    wait(lambda: a.records[retry["transferId"]]["data"]["status"] == "completed")
    wait(lambda: b.records[other]["data"]["status"] == "completed")
    with b.download(other) as (stream, data):
        assert stream.read() == b"" and data["totalBytes"] == 0


def test_real_p1_close_while_waiting_releases_staging(p1_services):
    a, b, _, _ = p1_services
    a.upload(metadata(), 1, io.BytesIO(b"x"))
    wait(lambda: len(b.records) == 1)
    a.close_async()
    assert a.closed.wait(5) and not a.root.exists()


@pytest.mark.parametrize("p1_services", ["faults"], indirect=True)
def test_real_p1_fault_recovery_keeps_bridge_ids_progress_and_hash(p1_services):
    a, b, events_a, _ = p1_services
    payload = bytes(range(256)) * 40 + b"partial"
    meta = metadata()
    a.upload(meta, len(payload), io.BytesIO(payload))
    wait(lambda: len(b.records) == 1, timeout=15)
    wire = next(iter(b.records))
    assert b.decide(wire, True)
    wait(
        lambda: a.records[meta["transferId"]]["data"]["status"] == "completed",
        timeout=30,
    )
    updates = [
        data
        for kind, data in events_a
        if kind == "transfer.upsert" and data["transferId"] == meta["transferId"]
    ]
    assert {data["transferId"] for data in updates} == {meta["transferId"]}
    counts = [data["transferredBytes"] for data in updates]
    assert counts == sorted(counts) and counts[-1] == len(payload)
    with b.download(wire) as (stream, _):
        assert stream.read() == payload
    wait(lambda: a.active is None)
    assert a.used_bytes == 0 and not list(a.root.glob("upload-*"))


@pytest.mark.parametrize("p1_services", ["bad_hash"], indirect=True)
def test_real_p1_hash_failure_is_not_published_and_next_empty_file_works(p1_services):
    a, b, _, events_b = p1_services
    meta = metadata()
    a.upload(meta, 1025, io.BytesIO(b"x" * 1025))
    wait(lambda: len(b.records) == 1)
    wire = next(iter(b.records))
    assert b.decide(wire, True)
    wait(lambda: b.records[wire]["data"]["status"] == "failed")
    wait(lambda: a.active is None)
    assert a.records[meta["transferId"]]["data"]["status"] == "failed"
    assert not any(
        kind == "transfer.upsert" and data["status"] == "completed"
        for kind, data in events_b
    )
    with pytest.raises(ValueError):
        with b.download(wire):
            pass
    assert not any(path.is_file() for path in b.downloads.rglob("*"))
    wait(lambda: b.used_bytes == 0)
    assert a.used_bytes == b.used_bytes == 0
    retry = metadata()
    a.upload(retry, 0, io.BytesIO())
    wait(lambda: len(b.records) == 2)
    next_wire = next(key for key in b.records if key != wire)
    assert b.decide(next_wire, True)
    wait(lambda: a.records[retry["transferId"]]["data"]["status"] == "completed")
