import collections
import hashlib
import socket
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from p1.client import FileClient, TransferError
from p1.relay import FileRelay
from shared.protocol import (
    HEADER,
    MAX_DATAGRAM,
    Packet,
    SessionTicket,
    decode_packet,
    encode_json,
    encode_packet,
    peek_session_id,
)
from shared.protocol import (
    MessageType as Kind,
)


class FaultRelay(FileRelay):
    """Deterministic faults on real relay-to-client UDP packets."""

    def __init__(
        self,
        *,
        faults=False,
        blackhole=False,
        bad_hash=False,
        block_first_transfer=False,
        **kwargs,
    ):
        super().__init__(port=0, **kwargs)
        self.faults, self.blackhole, self.bad_hash = faults, blackhole, bad_hash
        self.counts = collections.Counter()
        self.held = None
        self.data_seen = threading.Event()
        self.block_first_transfer = block_first_transfer
        self.blocked_transfer = None
        self.proofs = {}

    def _handle(self, peer, packet, endpoint):
        if packet.kind == Kind.PROVE:
            self.proofs[packet.session_id] = encode_packet(packet, peer.ticket.key)
        return super()._handle(peer, packet, endpoint)

    def _send_datagram(self, data, endpoint):
        ticket = self._peers[peek_session_id(data)].ticket
        packet = decode_packet(data, ticket.key)
        key = (packet.session_id, packet.transfer_id, packet.kind, packet.sequence)
        self.counts[key] += 1
        first = self.counts[key] == 1
        if packet.kind == Kind.DATA:
            self.data_seen.set()
            if self.block_first_transfer and self.blocked_transfer is None:
                self.blocked_transfer = packet.transfer_id
            if self.blackhole or packet.transfer_id == self.blocked_transfer:
                return
        if self.bad_hash and packet.kind == Kind.DATA and packet.sequence == 0:
            payload = bytes([packet.payload[0] ^ 1]) + packet.payload[1:]
            data = encode_packet(replace(packet, payload=payload), ticket.key)
        if self.faults and first:
            if packet.kind in {
                Kind.BOUND,
                Kind.OFFER,
                Kind.ACCEPT,
                Kind.FIN,
                Kind.COMPLETE,
                Kind.CHALLENGE,
            }:
                return
            if packet.kind == Kind.DATA and packet.sequence == 1:
                return
            if packet.kind == Kind.ACK and packet.sequence == 2:
                return
            if packet.kind == Kind.DATA and packet.sequence == 4:
                self.held = (data, endpoint)
                return
            if packet.kind == Kind.DATA and packet.sequence == 6:
                corrupt = bytearray(data)
                corrupt[HEADER.size] ^= 1
                super()._send_datagram(bytes(corrupt), endpoint)
                return
        super()._send_datagram(data, endpoint)
        if self.faults and packet.kind == Kind.DATA and packet.sequence == 3 and first:
            super()._send_datagram(data, endpoint)
        if self.held is not None and packet.kind == Kind.DATA and packet.sequence == 5:
            held, self.held = self.held, None
            super()._send_datagram(*held)


class DropReplyClient(FileClient):
    def __init__(self, *args, **kwargs):
        self.dropped = set()
        super().__init__(*args, **kwargs)

    def _send(self, kind, transfer_id=uuid.UUID(int=0), sequence=0, payload=b""):
        if (
            kind in {Kind.ACCEPT, Kind.COMPLETE, Kind.PROVE}
            and (kind, transfer_id) not in self.dropped
        ):
            self.dropped.add((kind, transfer_id))
            return
        return super()._send(kind, transfer_id, sequence, payload)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="p1-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def pair(
        self,
        *,
        receiver_class=FileClient,
        auto_accept=True,
        client_options=None,
        **relay_options,
    ):
        relay = FaultRelay(**relay_options).start()
        self.addCleanup(relay.close)
        options = dict(initial_rto=0.04, max_rto=0.16, max_retries=8, pacing=0.0002)
        options.update(client_options or {})
        alice = FileClient(
            relay.register_session("alice"),
            relay.address,
            self.root / "alice",
            auto_accept=True,
            **options,
        ).start()
        self.addCleanup(alice.close)
        bob = receiver_class(
            relay.register_session("bob"),
            relay.address,
            self.root / "bob",
            auto_accept=auto_accept,
            **options,
        ).start()
        self.addCleanup(bob.close)
        return relay, alice, bob

    def source(self, data, name="source.bin", folder="sources"):
        path = self.root / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def assert_received(self, sender, receiver, data, path=None):
        path = path or self.source(data)
        result = sender.send_file(path, receiver.ticket.username, timeout=60)
        received = receiver.received_files.get(timeout=2)
        self.assertEqual(received.path.read_bytes(), data)
        self.assertEqual(received.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(received.size, len(data))
        self.assertEqual(result.sha256, received.sha256)
        self.assertEqual(result.transfer_id, received.transfer_id)
        self.assertEqual(list(received.path.parent.iterdir()), [received.path])
        return result, received

    def next_offer(self, receiver):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            event = receiver.events.get(timeout=3)
            if event["type"] == "file_offer":
                return event
        self.fail("No offer received")

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_empty_small_exact_and_partial_files(self):
        _, alice, bob = self.pair()
        for index, data in enumerate(
            (
                b"",
                "xin chào".encode(),
                bytes(range(256)) * 4,
                bytes(range(256)) * 9 + b"last",
            )
        ):
            with self.subTest(size=len(data)):
                self.assert_received(
                    alice, bob, data, self.source(data, str(index) + ".bin")
                )

    def test_large_binary_file_is_verified(self):
        _, alice, bob = self.pair()
        self.assert_received(alice, bob, bytes(range(256)) * 8192 + b"partial")

    def test_loss_duplicate_reordering_corruption_and_control_loss_recover(self):
        relay, alice, bob = self.pair(faults=True)
        result, _ = self.assert_received(
            alice, bob, bytes(range(256)) * 128 + b"partial"
        )
        self.assertGreater(result.retransmissions, 0)
        self.assertTrue(
            any(
                kind == Kind.DATA and sequence == 1 and count >= 2
                for (_, _, kind, sequence), count in relay.counts.items()
            )
        )
        self.assertEqual(bob.received_files.qsize(), 0)
        self.assertEqual(len(list((self.root / "bob").iterdir())), 1)

    def test_lost_accept_and_complete_before_relay_are_recovered(self):
        _, alice, bob = self.pair(receiver_class=DropReplyClient)
        result, _ = self.assert_received(alice, bob, b"file" * 3000)
        self.assertGreaterEqual(result.retransmissions, 2)
        self.assertEqual(len(list((self.root / "bob").iterdir())), 1)

    def test_bidirectional_concurrent_files_and_same_names(self):
        _, alice, bob = self.pair()
        jobs = [
            (
                alice,
                bob,
                bytes([n]) * (32000 + n),
                self.source(bytes([n]) * (32000 + n), name="same.bin", folder=str(n)),
            )
            for n in range(2)
        ]
        jobs += [
            (
                bob,
                alice,
                bytes([n]) * (32000 + n),
                self.source(bytes([n]) * (32000 + n), name="same.bin", folder=str(n)),
            )
            for n in range(2, 4)
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(
                    sender.send_file, path, receiver.ticket.username, timeout=10
                )
                for sender, receiver, _, path in jobs
            ]
            results = [future.result(timeout=12) for future in futures]
        self.assertEqual(len({result.transfer_id for result in results}), 4)
        received = [bob.received_files.get(timeout=2) for _ in range(2)]
        received += [alice.received_files.get(timeout=2) for _ in range(2)]
        self.assertEqual(
            {item.path.read_bytes() for item in received}, {item[2] for item in jobs}
        )
        self.assertEqual(len({item.path for item in received}), 4)

    def test_manual_rejection_then_acceptance(self):
        _, alice, bob = self.pair(auto_accept=False)
        path = self.source(b"manual offer")
        with ThreadPoolExecutor(max_workers=1) as pool:
            rejected = pool.submit(alice.send_file, path, "bob", timeout=5)
            offer = self.next_offer(bob)
            bob.reject_file(offer["transfer_id"])
            with self.assertRaisesRegex(TransferError, "REJECTED"):
                rejected.result(timeout=3)
            accepted = pool.submit(alice.send_file, path, "bob", timeout=5)
            offer = self.next_offer(bob)
            bob.accept_file(offer["transfer_id"])
            accepted.result(timeout=3)
        self.assertEqual(
            bob.received_files.get(timeout=2).path.read_bytes(), b"manual offer"
        )

    def test_offline_and_self_recipient_fail_without_file_allocation(self):
        _, alice, bob = self.pair()
        for recipient, reason in (
            ("missing", "RECIPIENT_OFFLINE"),
            ("alice", "SELF_TRANSFER"),
        ):
            with (
                self.subTest(recipient=recipient),
                self.assertRaisesRegex(TransferError, reason),
            ):
                alice.send_file(self.source(b"data"), recipient, timeout=2)
        self.assertFalse((self.root / "bob").exists())

    def test_retry_exhaustion_removes_partial_file(self):
        _, alice, bob = self.pair(blackhole=True, client_options={"max_retries": 1})
        with self.assertRaisesRegex(TransferError, "retry limit"):
            alice.send_file(self.source(b"x" * 10000), "bob", timeout=3)
        self.wait_until(
            lambda: not bob._incoming
            and not list((self.root / "bob").iterdir())
        )
        self.assertEqual(list((self.root / "bob").iterdir()), [])

    def test_whole_file_hash_failure_never_reports_success(self):
        _, alice, bob = self.pair(bad_hash=True)
        with self.assertRaisesRegex(TransferError, "INTEGRITY"):
            alice.send_file(self.source(b"original file" * 1000), "bob", timeout=3)
        self.assertEqual(bob.received_files.qsize(), 0)
        self.assertEqual(list((self.root / "bob").iterdir()), [])

    def test_receiver_closing_cancels_sender_and_cleans_partial(self):
        relay, alice, bob = self.pair(blackhole=True)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                alice.send_file, self.source(b"x" * 10000), "bob", timeout=5
            )
            self.assertTrue(relay.data_seen.wait(2))
            bob.close()
            with self.assertRaisesRegex(TransferError, "CLIENT_CLOSED"):
                future.result(timeout=2)
        self.assertEqual(list((self.root / "bob").iterdir()), [])

    def test_relay_expiry_notifies_both_peers(self):
        _, alice, bob = self.pair(
            blackhole=True,
            idle_timeout=0.15,
            client_options={"initial_rto": 0.5, "max_rto": 0.5},
        )
        with self.assertRaisesRegex(TransferError, "TRANSFER_EXPIRED"):
            alice.send_file(self.source(b"x" * 10000), "bob", timeout=3)
        self.wait_until(lambda: not list((self.root / "bob").iterdir()))
        self.assertEqual(list((self.root / "bob").iterdir()), [])

    def test_revoked_session_stops_other_sender(self):
        relay, alice, bob = self.pair(blackhole=True)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                alice.send_file, self.source(b"x" * 10000), "bob", timeout=5
            )
            self.assertTrue(relay.data_seen.wait(2))
            relay.unregister_session("bob")
            with self.assertRaisesRegex(TransferError, "PEER_DISCONNECTED"):
                future.result(timeout=2)
        bob.close()
        self.assertEqual(list((self.root / "bob").iterdir()), [])

    def test_endpoint_cannot_be_rebound_by_replaying_valid_bind(self):
        relay, alice, bob = self.pair()
        captured_proof = relay.proofs[alice.ticket.session_id]
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as attacker:
            attacker.settimeout(0.1)
            bind = encode_packet(
                Packet(Kind.BIND, alice.ticket.session_id), alice.ticket.key
            )
            attacker.sendto(bind, relay.address)
            challenge = decode_packet(attacker.recv(MAX_DATAGRAM), alice.ticket.key)
            self.assertEqual(challenge.kind, Kind.CHALLENGE)
            attacker.sendto(captured_proof, relay.address)
            with self.assertRaises(socket.timeout):
                attacker.recvfrom(MAX_DATAGRAM)
        self.assert_received(alice, bob, b"still bound to the genuine endpoint")

    def test_reconnect_with_same_ticket_uses_fresh_endpoint_proof(self):
        relay, alice, bob = self.pair()
        _, first = self.assert_received(alice, bob, b"first")
        old_endpoint, ticket = alice._socket.getsockname(), alice.ticket
        alice.close()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            occupied.bind(old_endpoint)
            replacement = FileClient(
                ticket,
                relay.address,
                self.root / "replacement",
                initial_rto=0.04,
                max_rto=0.16,
                pacing=0.0002,
            ).start()
            self.addCleanup(replacement.close)
            _, second = self.assert_received(replacement, bob, b"second")
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(first.path.read_bytes(), b"first")

    def test_wrong_key_cannot_register(self):
        relay = FaultRelay().start()
        self.addCleanup(relay.close)
        ticket = relay.register_session("alice")
        invalid = SessionTicket(ticket.username, ticket.session_id, b"x" * 32)
        with self.assertRaisesRegex(TransferError, "registration timed out"):
            FileClient(
                invalid,
                relay.address,
                self.root,
                initial_rto=0.02,
                max_rto=0.02,
                max_retries=1,
            ).start()

    def test_malicious_metadata_does_not_create_files(self):
        relay, _, bob = self.pair()
        ticket = relay.register_session("malicious")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as raw:
            raw.settimeout(1)
            raw.sendto(
                encode_packet(Packet(Kind.BIND, ticket.session_id), ticket.key),
                relay.address,
            )
            challenge = decode_packet(raw.recv(MAX_DATAGRAM), ticket.key)
            self.assertEqual(challenge.kind, Kind.CHALLENGE)
            raw.sendto(
                encode_packet(
                    Packet(Kind.PROVE, ticket.session_id, payload=challenge.payload),
                    ticket.key,
                ),
                relay.address,
            )
            self.assertEqual(
                decode_packet(raw.recv(MAX_DATAGRAM), ticket.key).kind, Kind.BOUND
            )
            metadata = dict(
                recipient="bob",
                filename="../escape.bin",
                size=1,
                sha256="0" * 64,
                chunk_size=1024,
                total_chunks=1,
            )
            raw.sendto(
                encode_packet(
                    Packet(
                        Kind.OFFER,
                        ticket.session_id,
                        uuid.uuid4(),
                        payload=encode_json(metadata),
                    ),
                    ticket.key,
                ),
                relay.address,
            )
            response = decode_packet(raw.recv(MAX_DATAGRAM), ticket.key)
            self.assertEqual(response.payload, b"INVALID_METADATA")
        self.assertFalse((self.root / "bob").exists())
        self.assertEqual(bob.received_files.qsize(), 0)

    def test_twenty_sessions_bind_and_limit_is_enforced(self):
        relay = FaultRelay().start()
        self.addCleanup(relay.close)
        clients = []
        for index in range(20):
            ticket = relay.register_session("user" + str(index))
            client = FileClient(
                ticket,
                relay.address,
                self.root / str(index),
                initial_rto=0.04,
                max_rto=0.16,
            ).start()
            self.addCleanup(client.close)
            clients.append(client)
        with self.assertRaisesRegex(ValueError, "Session limit"):
            relay.register_session("overflow")
        # Explicitly accept on the destination while the other 18 endpoints stay alive.
        clients[19].auto_accept = True
        self.assert_received(clients[0], clients[19], b"twenty clients are bound")

    def test_active_transfer_limit_does_not_block_existing_transfer(self):
        relay, alice, bob = self.pair(auto_accept=False, per_client_limit=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                alice.send_file, self.source(b"first"), "bob", timeout=5
            )
            offer = self.next_offer(bob)
            with self.assertRaisesRegex(TransferError, "TRANSFER_LIMIT"):
                alice.send_file(self.source(b"second", "second.bin"), "bob", timeout=3)
            bob.accept_file(offer["transfer_id"])
            first.result(timeout=3)
        self.assertEqual(bob.received_files.get(timeout=2).path.read_bytes(), b"first")

    def test_stalled_file_does_not_block_another_and_can_be_cancelled(self):
        relay, alice, bob = self.pair(block_first_transfer=True)
        with ThreadPoolExecutor(max_workers=1) as pool:
            stalled = pool.submit(
                alice.send_file, self.source(b"blocked" * 1000), "bob", timeout=5
            )
            self.assertTrue(relay.data_seen.wait(2))
            self.assert_received(
                alice,
                bob,
                b"independent stream",
                self.source(b"independent stream", "other.bin"),
            )
            alice.cancel_file(relay.blocked_transfer)
            with self.assertRaisesRegex(TransferError, "CANCELLED"):
                stalled.result(timeout=2)
        self.wait_until(lambda: len(list((self.root / "bob").iterdir())) == 1)

    def test_overall_deadline_cleans_unaccepted_offer(self):
        _, alice, bob = self.pair(auto_accept=False)
        with self.assertRaisesRegex(TransferError, "deadline exceeded"):
            alice.send_file(self.source(b"pending offer"), "bob", timeout=0.12)
        self.wait_until(lambda: not bob._offers)
        self.assertFalse((self.root / "bob").exists())

    def test_shutdown_releases_owned_sockets_and_threads(self):
        relay, alice, bob = self.pair()
        addresses = [
            relay.address,
            alice._socket.getsockname(),
            bob._socket.getsockname(),
        ]
        threads = [relay._thread, alice._thread, bob._thread]
        alice.close()
        bob.close()
        relay.close()
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        for address in addresses:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(address)


if __name__ == "__main__":
    unittest.main()
