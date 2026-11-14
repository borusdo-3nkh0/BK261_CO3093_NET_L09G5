"""Current P1 UDP contract: exhaust OFFER waits without sleeping through retries."""

import hashlib
import io
import threading
from pathlib import Path
from unittest.mock import patch

from bridge_files import ACCEPT_TIMEOUT, FileService, load_p1
from p1.client import FileClient, TransferError
from p1.relay import FileRelay
from shared.protocol import MessageType as Kind
from tests.test_file_bridge import metadata, wait


def test_real_p1_offer_timeout_then_new_file_in_same_sessions(tmp_path):
    factory = load_p1(Path(__file__).resolve().parents[1])
    offered = threading.Event()
    received_reasons, sender_reasons, data_packets = [], [], []
    with FileRelay(port=0, secure=True) as relay:

        def receive(kind, data):
            if kind == "transfer.upsert" and data["status"] == "awaiting_acceptance":
                offered.set()

        a = FileService(
            "alice",
            factory,
            relay.register_session("alice").to_dict(),
            relay.address,
            tmp_path,
            lambda *_: None,
        )
        b = FileService(
            "bob",
            factory,
            relay.register_session("bob").to_dict(),
            relay.address,
            tmp_path,
            receive,
        )
        exchange, send, emit = (
            FileClient._control_exchange,
            FileClient._send,
            b.client._emit,
        )
        first_offer = True

        def expire_offer(self, state, transfer_id, kind, payload, predicate, deadline):
            nonlocal first_offer
            if self is a.client and kind == Kind.OFFER and first_offer:
                first_offer = False

                def no_sleep(*_args, **_kwargs):
                    assert offered.wait(2), "Receiver must actually see the offer"
                    return False

                # Preserve the original retry loop/limit; only virtualize its wait.
                with patch.object(state.condition, "wait_for", side_effect=no_sleep):
                    try:
                        return exchange(
                            self, state, transfer_id, kind, payload, predicate, deadline
                        )
                    except TransferError as error:
                        sender_reasons.append(str(error))
                        raise
            return exchange(
                self, state, transfer_id, kind, payload, predicate, deadline
            )

        def observe_send(self, kind, *args, **kwargs):
            if self is a.client and kind == Kind.DATA:
                data_packets.append(kind)
            return send(self, kind, *args, **kwargs)

        def observe_receive(event, **fields):
            if event == "file_failed":
                received_reasons.append(fields["reason"])
            return emit(event, **fields)

        try:
            a.start()
            b.start()
            with (
                patch.object(FileClient, "_control_exchange", expire_offer),
                patch.object(FileClient, "_send", observe_send),
                patch.object(b.client, "_emit", observe_receive),
            ):
                first = metadata()
                first["name"] = "wait.bin"
                a.upload(first, 1, io.BytesIO(b"x"))
                wait(
                    lambda: a.records[first["transferId"]]["data"]["status"] == "failed"
                )
                wait(lambda: bool(received_reasons))
                old = a.records[first["transferId"]]["data"]
                assert (
                    sender_reasons == ["OFFER retry limit exceeded"]
                    and not data_packets
                )
                assert (
                    received_reasons[0] == "SENDER_FAILED"
                )  # P1 does not relay the timeout cause.
                assert old["error"] == {
                    "code": "ACCEPT_TIMEOUT",
                    "userMessage": ACCEPT_TIMEOUT,
                }
                assert old["sendPending"] is False and a.active is None
                assert a.used_bytes == 0 and not list(a.root.glob("upload-*"))

                second, content = metadata(), bytes(range(256))
                second["name"] = "next.bin"
                offered.clear()
                a.upload(second, len(content), io.BytesIO(content))
                assert offered.wait(2)
                wire = next(
                    key
                    for key, r in b.records.items()
                    if r["data"]["status"] == "awaiting_acceptance"
                )
                b.decide(wire, True)
                wait(
                    lambda: (
                        a.records[second["transferId"]]["data"]["status"] == "completed"
                    )
                )
                wait(lambda: b.records[wire]["data"]["status"] == "completed")
                with b.download(wire) as (stream, _):
                    assert (
                        hashlib.sha256(stream.read()).digest()
                        == hashlib.sha256(content).digest()
                    )
                assert data_packets and old["status"] == "failed"
        finally:
            a.close_async()
            b.close_async()
            assert a.closed.wait(5) and b.closed.wait(5)
