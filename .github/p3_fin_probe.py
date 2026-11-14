"""Read-only tracing hooks for one unchanged UDP test. No fault/delay injection."""

import argparse
import json
import os
import platform
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "A1_Client-Server"
sys.path.insert(0, str(ROOT))
import p1.client as client_module  # noqa: E402
import pytest  # noqa: E402
from p1.client import FileClient, _ReceiveState  # noqa: E402
from p1.relay import FileRelay  # noqa: E402
from shared.protocol import HEADER  # noqa: E402
from shared.protocol import MessageType as Kind  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
start = time.perf_counter_ns()
events, lock, context = [], threading.Lock(), threading.local()
controls = {Kind.OFFER, Kind.ACCEPT, Kind.FIN, Kind.COMPLETE, Kind.ERROR, Kind.CANCEL}


def log(stage, **data):
    entry = dict(
        ms=round((time.perf_counter_ns() - start) / 1e6, 3),
        stage=stage,
        thread=threading.current_thread().name,
        **data,
    )
    with lock:
        events.append(entry)
        print(json.dumps(entry), flush=True)


def snapshot(client, transfer_id):
    incoming = client._incoming.get(transfer_id)
    receipt = client._receipts.get(transfer_id)
    outgoing = client._outgoing.get(transfer_id)
    return dict(
        user=client.ticket.username,
        transfer=str(transfer_id),
        phase=incoming.phase if incoming else None,
        count=incoming.count if incoming else None,
        chunks=incoming.offer.total_chunks if incoming else None,
        receipt=receipt[0].name if receipt else None,
        accepted=outgoing.accepted if outgoing else None,
        complete=outgoing.complete if outgoing else None,
        error=outgoing.error if outgoing else None,
    )


send = FileClient._send


def traced_send(self, kind, *a, **kw):
    transfer = a[0] if a else kw.get("transfer_id")
    if kind in controls:
        log("client.send.begin", kind=kind.name, **snapshot(self, transfer))
    try:
        return send(self, kind, *a, **kw)
    finally:
        if kind in controls:
            log("client.send.end", kind=kind.name, **snapshot(self, transfer))


FileClient._send = traced_send

handle = FileClient._handle


def traced_handle(self, packet):
    if packet.kind in controls:
        log(
            "client.receive",
            kind=packet.kind.name,
            **snapshot(self, packet.transfer_id),
        )
    try:
        return handle(self, packet)
    finally:
        if packet.kind in controls:
            log(
                "client.handled",
                kind=packet.kind.name,
                **snapshot(self, packet.transfer_id),
            )


FileClient._handle = traced_handle

exchange = FileClient._control_exchange


def traced_exchange(self, state, transfer_id, kind, payload, predicate, deadline):
    before = time.perf_counter_ns()
    log(
        "exchange.begin",
        kind=kind.name,
        remaining_ms=round((deadline - time.monotonic()) * 1000, 3),
        initial_rto=self.initial_rto,
        max_rto=self.max_rto,
        max_retries=self.max_retries,
        **snapshot(self, transfer_id),
    )
    try:
        return exchange(self, state, transfer_id, kind, payload, predicate, deadline)
    except BaseException as e:
        log(
            "exchange.error",
            kind=kind.name,
            exception=type(e).__name__,
            reason=str(e),
            **snapshot(self, transfer_id),
        )
        raise
    finally:
        log(
            "exchange.end",
            kind=kind.name,
            elapsed_ms=round((time.perf_counter_ns() - before) / 1e6, 3),
            retransmissions=state.retransmissions,
            **snapshot(self, transfer_id),
        )


FileClient._control_exchange = traced_exchange

chunks = FileClient._send_chunks


def traced_chunks(self, stream, offer, transfer_id, state, deadline):
    log("data.begin", **snapshot(self, transfer_id))
    result = chunks(self, stream, offer, transfer_id, state, deadline)
    log(
        "data.all_acked",
        retransmissions=state.retransmissions,
        **snapshot(self, transfer_id),
    )
    return result


FileClient._send_chunks = traced_chunks

worker = FileClient._verify


def traced_worker(self, transfer_id, incoming):
    context.transfer = str(transfer_id)
    context.user = self.ticket.username
    log("worker.begin", **snapshot(self, transfer_id))
    try:
        return worker(self, transfer_id, incoming)
    finally:
        log("worker.end", **snapshot(self, transfer_id))
        context.transfer = None


FileClient._verify = traced_worker

verify = _ReceiveState.verify


def traced_verify(self, stopped):
    before = time.perf_counter_ns()
    log(
        "verify.begin",
        transfer=str(self.transfer_id),
        phase=self.phase,
        count=self.count,
        chunks=self.offer.total_chunks,
    )
    try:
        return verify(self, stopped)
    except BaseException as e:
        log(
            "verify.error",
            transfer=str(self.transfer_id),
            exception=type(e).__name__,
            reason=str(e),
        )
        raise
    finally:
        log(
            "verify.end",
            transfer=str(self.transfer_id),
            phase=self.phase,
            elapsed_ms=round((time.perf_counter_ns() - before) / 1e6, 3),
        )


_ReceiveState.verify = traced_verify


def timed_io(name, fn):
    def traced(*a, **kw):
        transfer = getattr(context, "transfer", None)
        if not transfer:
            return fn(*a, **kw)
        log(name + ".begin", transfer=transfer, user=context.user)
        before = time.perf_counter_ns()
        try:
            return fn(*a, **kw)
        finally:
            log(
                name + ".end",
                transfer=transfer,
                user=context.user,
                elapsed_ms=round((time.perf_counter_ns() - before) / 1e6, 3),
            )

    return traced


os.fsync = timed_io("fsync", os.fsync)
os.replace = timed_io("publish", os.replace)
client_module.file_digest = timed_io("hash", client_module.file_digest)

relay_handle = FileRelay._handle


def traced_relay(self, peer, packet, endpoint):
    def state():
        t = self._transfers.get(packet.transfer_id)
        return dict(
            state=t.state if t else None,
            fin_seen=t.fin_seen if t else None,
            reason=t.reason.decode("utf-8", "replace") if t else "",
        )

    if packet.kind in controls:
        log(
            "relay.receive",
            transfer=str(packet.transfer_id),
            user=peer.ticket.username,
            kind=packet.kind.name,
            **state(),
        )
    result = relay_handle(self, peer, packet, endpoint)
    if packet.kind in controls:
        log(
            "relay.handled",
            transfer=str(packet.transfer_id),
            kind=packet.kind.name,
            outputs=[
                dict(kind=p.kind.name, user=self._peers[s].ticket.username)
                for s, p, *_ in result
            ],
            **state(),
        )
    return result


FileRelay._handle = traced_relay

relay_send = FileRelay._send_datagram


def traced_relay_send(self, data, endpoint):
    h = HEADER.unpack_from(data)
    kind = Kind(h[2])
    if kind in controls:
        import uuid

        log(
            "relay.send",
            transfer=str(uuid.UUID(bytes=h[4])),
            kind=kind.name,
            port=endpoint[1],
        )
    return relay_send(self, data, endpoint)


FileRelay._send_datagram = traced_relay_send

try:
    exit_code = pytest.main(
        [
            "-q",
            "-s",
            "tests/test_udp_transfer.py::TransferTests::test_bidirectional_concurrent_files_and_same_names",
            "--junitxml=" + str(args.output / "junit.xml"),
        ]
    )
finally:
    events.sort(key=lambda e: e["ms"])
    metadata = dict(
        python=sys.version,
        platform=platform.platform(),
        test="tests/test_udp_transfer.py::TransferTests::test_bidirectional_concurrent_files_and_same_names",
        observational=True,
        parametersChanged=False,
        elapsed_ms=round((time.perf_counter_ns() - start) / 1e6, 3),
    )
    (args.output / "timeline.json").write_text(
        json.dumps(dict(metadata=metadata, events=events), indent=2), encoding="utf-8"
    )
summary = dict(
    exit_code=int(exit_code),
    events=len(events),
    verify_ms=[e["elapsed_ms"] for e in events if e["stage"] == "verify.end"],
    fsync_ms=[e["elapsed_ms"] for e in events if e["stage"] == "fsync.end"],
    fin_sends=sum(
        e["stage"] == "client.send.begin" and e.get("kind") == "FIN" for e in events
    ),
    complete_sends=sum(
        e["stage"] == "client.send.begin" and e.get("kind") == "COMPLETE"
        for e in events
    ),
    errors=[e for e in events if e["stage"].endswith(".error")],
)
(args.output / "summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
print(json.dumps(summary))
sys.exit(exit_code)
