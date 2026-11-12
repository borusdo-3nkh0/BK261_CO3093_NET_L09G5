"""Nonblocking receive service and synchronous worker-friendly send API."""

import math
import os
import queue
import shutil
import socket
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from shared.protocol import (
    CHUNK_SIZE,
    MAX_DATAGRAM,
    ZERO_ID,
    FileOffer,
    Packet,
    ProtocolError,
    decode_packet,
    encode_packet,
    file_digest,
)
from shared.protocol import (
    MessageType as Kind,
)


class TransferError(RuntimeError):
    """A file was not successfully delivered and verified."""


@dataclass(frozen=True)
class TransferResult:
    transfer_id: uuid.UUID
    filename: str
    recipient: str
    size: int
    sha256: str
    elapsed: float
    retransmissions: int


@dataclass(frozen=True)
class ReceivedFile:
    transfer_id: uuid.UUID
    sender: str
    path: Path
    size: int
    sha256: str


@dataclass
class _SendState:
    condition: threading.Condition = field(default_factory=threading.Condition)
    acks: list = field(default_factory=list)
    accepted: bool = False
    complete: bool = False
    error: str = ""
    retransmissions: int = 0


@dataclass
class _Pending:
    payload: bytes
    sent: float
    retries: int = 0


class _ReceiveState:
    def __init__(self, transfer_id, offer, download_dir):
        self.transfer_id, self.offer = transfer_id, offer
        download_dir.mkdir(parents=True, exist_ok=True)
        self.directory = Path(
            tempfile.mkdtemp(prefix=transfer_id.hex + "-", dir=download_dir)
        )
        self.partial = self.directory / ".p1-partial"
        try:
            self.stream = self.partial.open("x+b")
        except BaseException:
            self.directory.rmdir()
            raise
        self.path = self.directory / offer.filename
        self.bitmap = bytearray(offer.total_chunks)
        self.count, self.received = 0, 0
        self.updated = time.monotonic()
        self.phase = "RECEIVING"
        self.lock = threading.Lock()
        self.last_progress = 0.0

    def write(self, sequence, payload):
        with self.lock:
            if len(payload) != self.offer.chunk_length(sequence):
                raise ProtocolError("Unexpected chunk length")
            if self.phase not in {"RECEIVING", "VERIFYING"}:
                return False
            self.updated = time.monotonic()
            if not self.bitmap[sequence]:
                if self.phase != "RECEIVING":
                    return False
                self.stream.seek(sequence * CHUNK_SIZE)
                if self.stream.write(payload) != len(payload):
                    raise OSError("Short file write")
                self.bitmap[sequence] = 1
                self.count += 1
                self.received += len(payload)
            return True

    def begin_verification(self):
        with self.lock:
            if self.phase == "RECEIVING" and self.count == self.offer.total_chunks:
                self.phase = "VERIFYING"
                return True
        return False

    def verify(self, stopped):
        with self.lock:
            if self.phase != "VERIFYING":
                raise TransferError("Transfer cancelled")
            self.stream.flush()
            size, digest = file_digest(self.stream)
            if size != self.offer.size or digest != self.offer.sha256:
                raise TransferError("INTEGRITY_FAILED")
            if stopped():
                raise TransferError("Client closed")
            os.fsync(self.stream.fileno())
            self.stream.close()
            os.replace(self.partial, self.path)
            self.phase = "COMPLETED"
            return ReceivedFile(
                self.transfer_id, self.offer.sender, self.path, size, digest
            )

    def abort(self):
        with self.lock:
            if self.phase == "COMPLETED":
                return
            self.phase = "FAILED"
            self.stream.close()
            shutil.rmtree(self.directory)


class FileClient:
    def __init__(
        self,
        ticket,
        relay_address,
        download_dir="downloads",
        *,
        auto_accept=False,
        initial_rto=1.0,
        max_rto=4.0,
        max_retries=8,
        idle_timeout=60.0,
        receipt_ttl=60.0,
        pacing=0.002,
        max_transfers=8,
    ):
        for value in (initial_rto, max_rto, idle_timeout, receipt_ttl):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Timeouts must be positive and finite")
        if (
            initial_rto > max_rto
            or type(max_retries) is not int
            or max_retries < 0
            or type(max_transfers) is not int
            or max_transfers < 1
            or not math.isfinite(pacing)
            or not 0 <= pacing <= 1
        ):
            raise ValueError("Invalid transfer limits")
        self.ticket = ticket
        self.relay_address = (socket.gethostbyname(relay_address[0]), relay_address[1])
        self.download_dir = Path(download_dir)
        self.auto_accept = auto_accept
        self.initial_rto, self.max_rto = initial_rto, max_rto
        self.max_retries, self.idle_timeout = max_retries, idle_timeout
        self.receipt_ttl, self.pacing, self.max_transfers = (
            receipt_ttl,
            pacing,
            max_transfers,
        )
        self.events = queue.Queue(maxsize=256)
        self.received_files = queue.Queue()
        self._outgoing, self._incoming, self._offers, self._receipts = {}, {}, {}, {}
        self._lock, self._send_lock = threading.RLock(), threading.Lock()
        self._stop, self._bound = threading.Event(), threading.Event()
        self._socket, self._thread = None, None
        self._workers = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="p1-verify"
        )
        self._next_data_send = 0.0

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise RuntimeError("Client cannot be restarted")
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind(("0.0.0.0", 0))
            self._socket.settimeout(0.1)
            self._thread = threading.Thread(
                target=self._run, name="p1-client", daemon=True
            )
            self._thread.start()
            delay = self.initial_rto
            for _ in range(self.max_retries + 1):
                self._send(Kind.BIND)
                if self._bound.wait(delay):
                    return self
                delay = min(self.max_rto, delay * 2)
            raise TransferError("UDP endpoint registration timed out")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()

    def _emit(self, event, **fields):
        value = dict(type=event, **fields)
        try:
            self.events.put_nowait(value)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(value)
            except queue.Full:
                pass

    def _send(self, kind, transfer_id=ZERO_ID, sequence=0, payload=b""):
        packet = Packet(kind, self.ticket.session_id, transfer_id, sequence, payload)
        data = encode_packet(packet, self.ticket.key)
        with self._send_lock:
            if self._stop.is_set() or self._socket is None:
                raise TransferError("Client closed")
            if kind == Kind.DATA:
                wait = self._next_data_send - time.monotonic()
                while wait > 0 and not self._stop.is_set():
                    # time.sleep uses Windows' high-resolution waitable timer on
                    # modern Python. Event.wait can round a sub-ms pace to 15ms.
                    time.sleep(min(wait, 0.01))
                    wait = self._next_data_send - time.monotonic()
                if self._stop.is_set():
                    raise TransferError("Client closed")
                self._next_data_send = time.monotonic() + self.pacing
            self._socket.sendto(data, self.relay_address)

    def _best_effort(self, kind, transfer_id, payload=b""):
        try:
            self._send(kind, transfer_id, payload=payload)
        except OSError, TransferError:
            pass

    def _run(self):
        last_ping = time.monotonic()
        while not self._stop.is_set():
            try:
                data, endpoint = self._socket.recvfrom(MAX_DATAGRAM + 1)
                if endpoint != self.relay_address:
                    continue
                packet = decode_packet(data, self.ticket.key)
                if packet.session_id != self.ticket.session_id:
                    continue
                self._handle(packet)
            except socket.timeout:
                pass
            except ProtocolError, UnicodeError, TransferError:
                pass
            except OSError:
                if not self._stop.is_set():
                    self._stop.set()
                    self._fail_outgoing("UDP socket failed")
                break
            self._expire()
            if time.monotonic() - last_ping >= 15:
                self._best_effort(Kind.PING, ZERO_ID)
                last_ping = time.monotonic()

    def _handle(self, packet):
        kind, transfer_id = packet.kind, packet.transfer_id
        if kind == Kind.BOUND:
            self._bound.set()
            return
        if kind == Kind.CHALLENGE:
            if not self._bound.is_set():
                self._send(Kind.PROVE, payload=packet.payload)
            return
        if kind == Kind.OFFER:
            self._handle_offer(transfer_id, FileOffer.from_bytes(packet.payload))
            return
        with self._lock:
            outgoing = self._outgoing.get(transfer_id)
            incoming = self._incoming.get(transfer_id)
            receipt = self._receipts.get(transfer_id)
        if outgoing is not None:
            with outgoing.condition:
                if kind == Kind.ACCEPT:
                    outgoing.accepted = True
                elif kind == Kind.ACK:
                    if len(outgoing.acks) < 256:
                        outgoing.acks.append((packet.sequence, time.monotonic()))
                elif kind == Kind.COMPLETE:
                    outgoing.complete = True
                elif kind in {Kind.ERROR, Kind.REJECT, Kind.CANCEL}:
                    outgoing.error = packet.payload.decode("utf-8") or kind.name
                outgoing.condition.notify_all()
        if incoming is not None:
            if kind == Kind.DATA:
                try:
                    if incoming.write(packet.sequence, packet.payload):
                        self._send(Kind.ACK, transfer_id, packet.sequence)
                        if time.monotonic() - incoming.last_progress >= 0.1:
                            incoming.last_progress = time.monotonic()
                            self._emit(
                                "file_progress",
                                transfer_id=str(transfer_id),
                                direction="receive",
                                bytes=incoming.received,
                                total=incoming.offer.size,
                            )
                except OSError:
                    self._discard_incoming(transfer_id, b"DISK_ERROR", notify=True)
            elif kind == Kind.FIN and incoming.begin_verification():
                self._workers.submit(self._verify, transfer_id, incoming)
        elif kind == Kind.FIN and receipt is not None:
            self._best_effort(receipt[0], transfer_id, receipt[1])
        if kind in {Kind.ERROR, Kind.REJECT, Kind.CANCEL}:
            self._discard_incoming(transfer_id, packet.payload, notify=False)

    def _handle_offer(self, transfer_id, offer):
        if offer.recipient != self.ticket.username or not offer.sender:
            raise ProtocolError("Offer has no authenticated sender or wrong recipient")
        with self._lock:
            receipt = self._receipts.get(transfer_id)
            incoming = self._incoming.get(transfer_id)
            pending = self._offers.get(transfer_id)
            if receipt is not None:
                self._best_effort(receipt[0], transfer_id, receipt[1])
                return
            if incoming is not None:
                if incoming.offer == offer:
                    incoming.updated = time.monotonic()
                    self._best_effort(Kind.ACCEPT, transfer_id)
                return
            if pending is not None:
                if pending[0] == offer:
                    self._offers[transfer_id] = (offer, time.monotonic())
                return
            if (
                len(self._incoming) + len(self._offers) + len(self._outgoing)
                >= self.max_transfers
            ):
                self._best_effort(Kind.REJECT, transfer_id, b"TRANSFER_LIMIT")
                return
            self._offers[transfer_id] = (offer, time.monotonic())
        self._emit(
            "file_offer",
            transfer_id=str(transfer_id),
            sender=offer.sender,
            filename=offer.filename,
            size=offer.size,
            sha256=offer.sha256,
        )
        if self.auto_accept:
            try:
                self.accept_file(transfer_id)
            except OSError, TransferError:
                self._discard_incoming(transfer_id, b"DISK_ERROR", notify=True)

    def accept_file(self, transfer_id):
        transfer_id = uuid.UUID(str(transfer_id))
        with self._lock:
            if transfer_id in self._incoming:
                incoming = self._incoming[transfer_id]
            else:
                pending = self._offers.get(transfer_id)
                if pending is None:
                    raise TransferError("No pending offer")
                incoming = _ReceiveState(transfer_id, pending[0], self.download_dir)
                self._incoming[transfer_id] = incoming
                del self._offers[transfer_id]
        self._send(Kind.ACCEPT, transfer_id)

    def reject_file(self, transfer_id, reason="REJECTED"):
        transfer_id = uuid.UUID(str(transfer_id))
        payload = reason.encode("utf-8")[:256].decode("utf-8", "ignore").encode("utf-8")
        with self._lock:
            if self._offers.pop(transfer_id, None) is None:
                raise TransferError("No pending offer")
            self._remember(transfer_id, Kind.REJECT, payload)
        self._best_effort(Kind.REJECT, transfer_id, payload)

    def cancel_file(self, transfer_id):
        """Cancel one transfer without disconnecting or affecting other files."""
        transfer_id = uuid.UUID(str(transfer_id))
        with self._lock:
            outgoing = self._outgoing.get(transfer_id)
            incoming = transfer_id in self._incoming or transfer_id in self._offers
        if outgoing is None and not incoming:
            raise TransferError("No active transfer")
        if outgoing is not None:
            with outgoing.condition:
                outgoing.error = "CANCELLED"
                outgoing.condition.notify_all()
        self._discard_incoming(transfer_id, b"CANCELLED", notify=False)
        self._best_effort(Kind.CANCEL, transfer_id, b"CANCELLED")

    def _remember(self, transfer_id, kind, payload=b""):
        with self._lock:
            self._receipts[transfer_id] = (kind, payload, time.monotonic())
            while len(self._receipts) > 128:
                del self._receipts[next(iter(self._receipts))]

    def _verify(self, transfer_id, incoming):
        try:
            result = incoming.verify(self._stop.is_set)
        except OSError, TransferError:
            self._discard_incoming(transfer_id, b"INTEGRITY_OR_DISK_ERROR", notify=True)
            return
        with self._lock:
            self._incoming.pop(transfer_id, None)
            self._remember(transfer_id, Kind.COMPLETE)
        self.received_files.put(result)
        self._emit(
            "file_received",
            transfer_id=str(transfer_id),
            sender=result.sender,
            path=str(result.path),
            size=result.size,
            sha256=result.sha256,
        )
        self._best_effort(Kind.COMPLETE, transfer_id)

    def _discard_incoming(self, transfer_id, reason, *, notify):
        with self._lock:
            incoming = self._incoming.get(transfer_id)
            if incoming is not None:
                incoming.abort()
                self._incoming.pop(transfer_id, None)
            offered = self._offers.pop(transfer_id, None)
        if incoming is not None or offered is not None:
            self._remember(transfer_id, Kind.ERROR, reason)
            self._emit(
                "file_failed",
                transfer_id=str(transfer_id),
                reason=reason.decode("utf-8", "replace"),
            )
            if notify:
                self._best_effort(Kind.ERROR, transfer_id, reason)

    def _expire(self):
        now = time.monotonic()
        with self._lock:
            expired = [
                key
                for key, state in self._incoming.items()
                if state.phase == "RECEIVING"
                and now - state.updated >= self.idle_timeout
            ]
            expired += [
                key
                for key, (_, updated) in self._offers.items()
                if now - updated >= self.idle_timeout
            ]
            for key, (_, _, updated) in list(self._receipts.items()):
                if now - updated >= self.receipt_ttl:
                    del self._receipts[key]
        for key in expired:
            self._discard_incoming(key, b"TRANSFER_EXPIRED", notify=True)

    def _check_sender(self, state, deadline):
        if state.error:
            raise TransferError(state.error)
        if self._stop.is_set():
            raise TransferError("Client closed")
        if time.monotonic() >= deadline:
            raise TransferError("Transfer deadline exceeded")

    def _control_exchange(self, state, transfer_id, kind, payload, predicate, deadline):
        delay = self.initial_rto
        for attempt in range(self.max_retries + 1):
            with state.condition:
                self._check_sender(state, deadline)
                if predicate():
                    return
            self._send(kind, transfer_id, payload=payload)
            state.retransmissions += bool(attempt)
            with state.condition:
                state.condition.wait_for(
                    lambda: predicate() or bool(state.error) or self._stop.is_set(),
                    timeout=min(delay, max(0, deadline - time.monotonic())),
                )
                self._check_sender(state, deadline)
                if predicate():
                    return
            delay = min(self.max_rto, delay * 2)
        raise TransferError(kind.name + " retry limit exceeded")

    def send_file(self, path, recipient, *, timeout=300.0):
        """Run on an application worker. Success means the recipient verified it."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Send timeout must be positive and finite")
        if not self._bound.is_set() or self._stop.is_set():
            raise TransferError("Client is not connected")
        started, transfer_id = time.monotonic(), uuid.uuid4()
        deadline, state = started + timeout, _SendState()
        path = Path(path)
        with path.open("rb") as stream:
            size, digest = file_digest(stream)
            offer = FileOffer(recipient, path.name, size, digest)
            with self._lock:
                if (
                    len(self._outgoing) + len(self._incoming) + len(self._offers)
                    >= self.max_transfers
                ):
                    raise TransferError("TRANSFER_LIMIT")
                self._outgoing[transfer_id] = state
            try:
                self._emit(
                    "file_sending",
                    transfer_id=str(transfer_id),
                    filename=path.name,
                    recipient=recipient,
                    size=size,
                )
                self._control_exchange(
                    state,
                    transfer_id,
                    Kind.OFFER,
                    offer.to_bytes(),
                    lambda: state.accepted,
                    deadline,
                )
                self._send_chunks(stream, offer, transfer_id, state, deadline)
                self._control_exchange(
                    state, transfer_id, Kind.FIN, b"", lambda: state.complete, deadline
                )
                result = TransferResult(
                    transfer_id,
                    path.name,
                    recipient,
                    size,
                    digest,
                    time.monotonic() - started,
                    state.retransmissions,
                )
                self._emit(
                    "file_sent",
                    transfer_id=str(transfer_id),
                    size=size,
                    sha256=digest,
                    retransmissions=result.retransmissions,
                )
                return result
            except (OSError, TransferError, ProtocolError) as exc:
                self._best_effort(Kind.CANCEL, transfer_id, b"SENDER_FAILED")
                self._emit("file_failed", transfer_id=str(transfer_id), reason=str(exc))
                raise TransferError(str(exc)) from exc
            finally:
                with self._lock:
                    self._outgoing.pop(transfer_id, None)

    def _send_chunks(self, stream, offer, transfer_id, state, deadline):
        pending, next_sequence, acknowledged = {}, 0, 0
        cwnd, rto, srtt, rttvar = 4.0, self.initial_rto, None, None
        last_progress = 0.0
        while pending or next_sequence < offer.total_chunks:
            with state.condition:
                self._check_sender(state, deadline)
                acks, state.acks = state.acks, []
            for sequence, received_at in acks:
                chunk = pending.pop(sequence, None)
                if chunk is None:
                    continue
                acknowledged += len(chunk.payload)
                cwnd = min(32.0, cwnd + 1.0 / cwnd)
                sample = received_at - chunk.sent
                if chunk.retries == 0 and sample > 0:
                    if srtt is None:
                        srtt, rttvar = sample, sample / 2
                    else:
                        rttvar = 0.75 * rttvar + 0.25 * abs(srtt - sample)
                        srtt = 0.875 * srtt + 0.125 * sample
                    rto = min(
                        self.max_rto, max(self.initial_rto / 2, srtt + 4 * rttvar)
                    )
            now = time.monotonic()
            expired = [seq for seq, chunk in pending.items() if now - chunk.sent >= rto]
            if expired:
                cwnd, rto = max(2.0, cwnd / 2), min(self.max_rto, rto * 2)
                for sequence in expired:
                    chunk = pending[sequence]
                    if chunk.retries >= self.max_retries:
                        raise TransferError("DATA retry limit exceeded")
                    self._send(Kind.DATA, transfer_id, sequence, chunk.payload)
                    chunk.sent, chunk.retries = time.monotonic(), chunk.retries + 1
                    state.retransmissions += 1
            while next_sequence < offer.total_chunks and len(pending) < int(cwnd):
                self._check_sender(state, deadline)
                stream.seek(next_sequence * CHUNK_SIZE)
                payload = stream.read(offer.chunk_length(next_sequence))
                if len(payload) != offer.chunk_length(next_sequence):
                    raise TransferError("Source file changed during transfer")
                sent = time.monotonic()
                self._send(Kind.DATA, transfer_id, next_sequence, payload)
                pending[next_sequence] = _Pending(payload, sent)
                next_sequence += 1
            if now - last_progress >= 0.1:
                last_progress = now
                self._emit(
                    "file_progress",
                    transfer_id=str(transfer_id),
                    direction="send",
                    bytes=acknowledged,
                    total=offer.size,
                )
            if pending:
                wait = (
                    min(chunk.sent + rto for chunk in pending.values())
                    - time.monotonic()
                )
                with state.condition:
                    if not state.acks and not state.error:
                        state.condition.wait(timeout=max(0.001, min(0.05, wait)))

    def _fail_outgoing(self, reason):
        with self._lock:
            states = list(self._outgoing.values())
        for state in states:
            with state.condition:
                state.error = reason
                state.condition.notify_all()

    def close(self):
        if not self._stop.is_set():
            with self._lock:
                active = (
                    list(self._outgoing) + list(self._incoming) + list(self._offers)
                )
            for transfer_id in active:
                self._best_effort(Kind.CANCEL, transfer_id, b"CLIENT_CLOSED")
        self._stop.set()
        self._fail_outgoing("Client closed")
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._workers.shutdown(wait=True)
        with self._lock:
            incoming = list(self._incoming.values())
            self._incoming.clear()
            self._offers.clear()
        for state in incoming:
            state.abort()
