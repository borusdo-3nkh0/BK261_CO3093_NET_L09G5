"""Authenticated, bounded UDP relay. Session provisioning is an in-process API."""

import logging
import math
import secrets
import socket
import threading
import time
import uuid
from dataclasses import dataclass, replace

from shared.protocol import (
    FileOffer,
    MAX_DATAGRAM,
    MessageType as Kind,
    Packet,
    ProtocolError,
    SessionTicket,
    decode_packet,
    encode_packet,
    peek_session_id,
)

logger = logging.getLogger(__name__)


@dataclass
class _Peer:
    ticket: SessionTicket
    endpoint: object = None
    challenge: object = None


@dataclass
class _Transfer:
    sender: uuid.UUID
    recipient: uuid.UUID
    offer: FileOffer
    updated: float
    state: str = "OFFERED"
    reason: bytes = b""
    fin_seen: bool = False


class FileRelay:
    def __init__(
        self,
        host="127.0.0.1",
        port=5001,
        *,
        idle_timeout=60.0,
        receipt_ttl=60.0,
        max_sessions=20,
        max_transfers=64,
        per_client_limit=8,
    ):
        if any(not math.isfinite(t) or t <= 0 for t in (idle_timeout, receipt_ttl)):
            raise ValueError("Timeouts must be positive and finite")
        if any(
            type(n) is not int or n < 1
            for n in (max_sessions, max_transfers, per_client_limit)
        ):
            raise ValueError("Limits must be positive")
        self.host, self.port = host, port
        self.idle_timeout, self.receipt_ttl = idle_timeout, receipt_ttl
        self.max_sessions, self.max_transfers = max_sessions, max_transfers
        self.per_client_limit = per_client_limit
        self._peers, self._usernames, self._transfers = {}, {}, {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._socket = None
        self._thread = None

    @property
    def address(self):
        if self._socket is None:
            raise RuntimeError("Relay has not started")
        return self._socket.getsockname()

    def register_session(self, username, *, ticket=None):
        """Call only after P2 authenticates the user. Never expose other tickets."""
        ticket = ticket or SessionTicket(
            username, uuid.uuid4(), secrets.token_bytes(32)
        )
        if ticket.username != username:
            raise ValueError("Ticket owner mismatch")
        with self._lock:
            if username in self._usernames or ticket.session_id in self._peers:
                raise ValueError("Session already registered")
            if len(self._peers) >= self.max_sessions:
                raise ValueError("Session limit reached")
            self._peers[ticket.session_id] = _Peer(ticket)
            self._usernames[username] = ticket.session_id
        return ticket

    def unregister_session(self, username):
        with self._lock:
            session = self._usernames.pop(username, None)
            if session is None:
                return
            self._peers.pop(session)
            outputs = []
            for transfer_id, transfer in self._transfers.items():
                if session in (
                    transfer.sender,
                    transfer.recipient,
                ) and not self._terminal(transfer):
                    transfer.state, transfer.reason = "FAILED", b"PEER_DISCONNECTED"
                    transfer.updated = time.monotonic()
                    other = (
                        transfer.recipient
                        if session == transfer.sender
                        else transfer.sender
                    )
                    outputs.append(
                        (
                            other,
                            Packet(
                                Kind.ERROR, other, transfer_id, payload=transfer.reason
                            ),
                        )
                    )
        self._deliver(outputs)

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Relay already started")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
            sock.settimeout(0.1)
        except BaseException:
            sock.close()
            raise
        self._socket = sock
        self._thread = threading.Thread(target=self._run, name="p1-relay", daemon=True)
        self._thread.start()
        return self

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def _terminal(transfer):
        return transfer.state in {"COMPLETED", "REJECTED", "FAILED"}

    def _run(self):
        while not self._stop.is_set():
            try:
                data, endpoint = self._socket.recvfrom(MAX_DATAGRAM + 1)
                with self._lock:
                    session = peek_session_id(data)
                    peer = self._peers.get(session)
                    if peer is None:
                        continue
                    packet = decode_packet(data, peer.ticket.key)
                    outputs = self._handle(peer, packet, endpoint)
                self._deliver(outputs)
            except socket.timeout:
                pass
            except (ProtocolError, UnicodeError):
                # Invalid/unauthenticated datagrams get no response or disk allocation.
                pass
            except OSError:
                if not self._stop.is_set():
                    logger.exception("UDP relay socket error")
            self._expire()

    def _send_datagram(self, data, endpoint):
        """Small override point for deterministic network-fault tests."""
        self._socket.sendto(data, endpoint)

    def _deliver(self, outputs):
        for output in outputs:
            session, packet = output[:2]
            with self._lock:
                peer = self._peers.get(session)
                if peer is None:
                    continue
                endpoint = output[2] if len(output) == 3 else peer.endpoint
                if endpoint is None:
                    continue
                data = encode_packet(
                    replace(packet, session_id=session), peer.ticket.key
                )
            try:
                if self._socket is not None:
                    self._send_datagram(data, endpoint)
            except OSError:
                # UDP failure is recovered by endpoint retry or inactivity expiry.
                logger.debug("UDP forwarding failed", exc_info=True)

    def _handle(self, peer, packet, endpoint):
        session, transfer_id, kind = packet.session_id, packet.transfer_id, packet.kind

        def reply(kind, payload=b""):
            return [(session, Packet(kind, session, transfer_id, payload=payload))]

        if kind == Kind.BIND:
            if peer.endpoint == endpoint:
                return reply(Kind.BOUND)
            if (
                peer.challenge is None
                or peer.challenge[0] != endpoint
                or peer.challenge[2] <= time.monotonic()
            ):
                peer.challenge = (
                    endpoint,
                    secrets.token_bytes(16),
                    time.monotonic() + 5,
                )
            challenge = Packet(Kind.CHALLENGE, session, payload=peer.challenge[1])
            return [(session, challenge, endpoint)]
        if kind == Kind.PROVE:
            challenge = peer.challenge
            if (
                challenge is None
                or challenge[0] != endpoint
                or challenge[1] != packet.payload
                or challenge[2] <= time.monotonic()
            ):
                return []
            peer.endpoint, peer.challenge = endpoint, None
            outputs = reply(Kind.BOUND)
            # Reconnection starts fresh; old file state cannot be resumed safely.
            for old_id, transfer in self._transfers.items():
                if session in (
                    transfer.sender,
                    transfer.recipient,
                ) and not self._terminal(transfer):
                    transfer.state, transfer.reason = "FAILED", b"ENDPOINT_CHANGED"
                    transfer.updated = time.monotonic()
                    other = (
                        transfer.recipient
                        if session == transfer.sender
                        else transfer.sender
                    )
                    outputs.append(
                        (
                            other,
                            Packet(Kind.ERROR, other, old_id, payload=transfer.reason),
                        )
                    )
            return outputs
        if peer.endpoint != endpoint:
            return []
        if kind == Kind.PING:
            return reply(Kind.PONG)
        if kind == Kind.OFFER:
            try:
                offer = FileOffer.from_bytes(
                    packet.payload, sender=peer.ticket.username
                )
            except ProtocolError:
                return reply(Kind.ERROR, b"INVALID_METADATA")
            transfer = self._transfers.get(transfer_id)
            if transfer is not None:
                if transfer.sender != session or transfer.offer != offer:
                    return reply(Kind.ERROR, b"TRANSFER_ID_CONFLICT")
                if self._terminal(transfer):
                    outcome = (
                        Kind.COMPLETE
                        if transfer.state == "COMPLETED"
                        else (
                            Kind.REJECT if transfer.state == "REJECTED" else Kind.ERROR
                        )
                    )
                    return reply(outcome, transfer.reason)
                transfer.updated = time.monotonic()
                if transfer.state == "ACTIVE":
                    return reply(Kind.ACCEPT)
                return [(transfer.recipient, replace(packet, payload=offer.to_bytes()))]
            recipient = self._usernames.get(offer.recipient)
            if recipient == session:
                return reply(Kind.ERROR, b"SELF_TRANSFER")
            if recipient is None or self._peers[recipient].endpoint is None:
                return reply(Kind.ERROR, b"RECIPIENT_OFFLINE")
            active = [t for t in self._transfers.values() if not self._terminal(t)]
            if len(active) >= self.max_transfers or any(
                sum(s in (t.sender, t.recipient) for t in active)
                >= self.per_client_limit
                for s in (session, recipient)
            ):
                return reply(Kind.ERROR, b"TRANSFER_LIMIT")
            self._transfers[transfer_id] = _Transfer(
                session, recipient, offer, time.monotonic()
            )
            return [(recipient, replace(packet, payload=offer.to_bytes()))]

        transfer = self._transfers.get(transfer_id)
        if transfer is None or session not in (transfer.sender, transfer.recipient):
            return []
        from_sender = session == transfer.sender
        other = transfer.recipient if from_sender else transfer.sender
        if self._terminal(transfer):
            if from_sender and kind == Kind.FIN and transfer.state == "COMPLETED":
                return reply(Kind.COMPLETE)
            return []
        if kind == Kind.ACCEPT and not from_sender:
            transfer.state = "ACTIVE"
        elif kind == Kind.REJECT and not from_sender and transfer.state == "OFFERED":
            transfer.state, transfer.reason = "REJECTED", packet.payload
        elif kind in {Kind.ERROR, Kind.CANCEL}:
            transfer.state, transfer.reason = "FAILED", packet.payload or b"CANCELLED"
        elif transfer.state != "ACTIVE":
            return []
        elif kind == Kind.DATA and from_sender:
            try:
                if len(packet.payload) != transfer.offer.chunk_length(packet.sequence):
                    return []
            except ProtocolError:
                return []
        elif kind == Kind.ACK and not from_sender:
            if packet.sequence >= transfer.offer.total_chunks:
                return []
        elif kind == Kind.FIN and from_sender:
            transfer.fin_seen = True
        elif kind == Kind.COMPLETE and not from_sender and transfer.fin_seen:
            transfer.state = "COMPLETED"
        else:
            return []
        transfer.updated = time.monotonic()
        return [(other, packet)]

    def _expire(self):
        now, outputs = time.monotonic(), []
        with self._lock:
            for transfer_id, transfer in list(self._transfers.items()):
                if self._terminal(transfer):
                    if now - transfer.updated >= self.receipt_ttl:
                        del self._transfers[transfer_id]
                elif now - transfer.updated >= self.idle_timeout:
                    transfer.state, transfer.reason = "FAILED", b"TRANSFER_EXPIRED"
                    transfer.updated = now
                    for session in (transfer.sender, transfer.recipient):
                        outputs.append(
                            (
                                session,
                                Packet(
                                    Kind.ERROR,
                                    session,
                                    transfer_id,
                                    payload=transfer.reason,
                                ),
                            )
                        )
            terminal = [
                (key, t) for key, t in self._transfers.items() if self._terminal(t)
            ]
            for key, _ in sorted(terminal, key=lambda pair: pair[1].updated)[:-256]:
                del self._transfers[key]
        self._deliver(outputs)
