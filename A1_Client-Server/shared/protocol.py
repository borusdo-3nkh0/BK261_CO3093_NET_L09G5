"""Version 1 wire codec. See docs/protocol.md for the byte-level contract."""

import hashlib
import hmac
import json
import re
import struct
import uuid
from dataclasses import dataclass, field
from enum import IntEnum

CHUNK_SIZE = 1024
SECURE_CHUNK_SIZE = 996
MAX_FILE_SIZE = 256 * 1024 * 1024
MAX_CONTROL_LINE = 1024
MAX_RESPONSE_LINE = 8192
HEADER = struct.Struct("!4sBB16s16sIH")
TAG_SIZE = 16
MAX_DATAGRAM = HEADER.size + CHUNK_SIZE + TAG_SIZE
ZERO_ID = uuid.UUID(int=0)
MAGIC = b"P1FT"
VERSION = 1


class ProtocolError(ValueError):
    """An untrusted message violates the wire contract."""


class MessageType(IntEnum):
    BIND = 1
    BOUND = 2
    OFFER = 3
    ACCEPT = 4
    REJECT = 5
    DATA = 6
    ACK = 7
    FIN = 8
    COMPLETE = 9
    ERROR = 10
    CANCEL = 11
    PING = 12
    PONG = 13
    CHALLENGE = 14
    PROVE = 15


@dataclass(frozen=True)
class Packet:
    kind: MessageType
    session_id: uuid.UUID
    transfer_id: uuid.UUID = ZERO_ID
    sequence: int = 0
    payload: bytes = b""


def _validate_packet(packet):
    try:
        kind = MessageType(packet.kind)
    except ValueError as exc:
        raise ProtocolError("Unknown message type") from exc
    if not isinstance(packet.session_id, uuid.UUID) or packet.session_id == ZERO_ID:
        raise ProtocolError("Invalid session ID")
    if not isinstance(packet.transfer_id, uuid.UUID):
        raise ProtocolError("Invalid transfer ID")
    session_message = kind in {
        MessageType.BIND,
        MessageType.BOUND,
        MessageType.PING,
        MessageType.PONG,
        MessageType.CHALLENGE,
        MessageType.PROVE,
    }
    if session_message != (packet.transfer_id == ZERO_ID):
        raise ProtocolError("Invalid transfer ID for message type")
    if type(packet.sequence) is not int or not 0 <= packet.sequence <= 0xFFFFFFFF:
        raise ProtocolError("Invalid sequence number")
    if kind not in {MessageType.DATA, MessageType.ACK} and packet.sequence:
        raise ProtocolError("Control sequence must be zero")
    if not isinstance(packet.payload, bytes) or len(packet.payload) > CHUNK_SIZE:
        raise ProtocolError("Invalid payload length")
    if kind in {MessageType.CHALLENGE, MessageType.PROVE}:
        if len(packet.payload) != 16:
            raise ProtocolError("Endpoint proof must contain a 16-byte nonce")
    elif kind == MessageType.DATA:
        if not packet.payload:
            raise ProtocolError("Empty DATA packet")
    elif kind == MessageType.OFFER:
        if not packet.payload:
            raise ProtocolError("Empty OFFER packet")
    elif kind in {MessageType.ERROR, MessageType.REJECT, MessageType.CANCEL}:
        if len(packet.payload) > 256:
            raise ProtocolError("Reason too long")
        try:
            packet.payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Invalid reason encoding") from exc
    elif packet.payload:
        raise ProtocolError("Unexpected payload")


def _validate_key(key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ProtocolError("Session key must contain 32 bytes")


def encode_packet(packet, key):
    _validate_key(key)
    _validate_packet(packet)
    body = (
        HEADER.pack(
            MAGIC,
            VERSION,
            int(packet.kind),
            packet.session_id.bytes,
            packet.transfer_id.bytes,
            packet.sequence,
            len(packet.payload),
        )
        + packet.payload
    )
    return body + hmac.digest(key, body, "sha256")[:TAG_SIZE]


def peek_session_id(data):
    """Select a key, without treating this unauthenticated header as trusted."""
    if (
        not isinstance(data, bytes)
        or not HEADER.size + TAG_SIZE <= len(data) <= MAX_DATAGRAM
    ):
        raise ProtocolError("Invalid datagram size")
    magic, version, _, session, _, _, length = HEADER.unpack_from(data)
    if magic != MAGIC or version not in {VERSION, 2}:
        raise ProtocolError("Unsupported protocol")
    if (
        length > CHUNK_SIZE
        or (version == 2 and length < 28)
        or len(data) != HEADER.size + length + TAG_SIZE
    ):
        raise ProtocolError("Invalid datagram length")
    return uuid.UUID(bytes=session)


def decode_packet(data, key):
    _validate_key(key)
    peek_session_id(data)
    if data[4] != VERSION:
        raise ProtocolError("Secure packet requires a v2 context")
    body, tag = data[:-TAG_SIZE], data[-TAG_SIZE:]
    if not hmac.compare_digest(tag, hmac.digest(key, body, "sha256")[:TAG_SIZE]):
        raise ProtocolError("Invalid authentication tag")
    _, _, kind, session, transfer, sequence, _ = HEADER.unpack_from(body)
    try:
        packet = Packet(
            MessageType(kind),
            uuid.UUID(bytes=session),
            uuid.UUID(bytes=transfer),
            sequence,
            body[HEADER.size :],
        )
    except ValueError as exc:
        raise ProtocolError("Unknown message type") from exc
    _validate_packet(packet)
    return packet


def encode_json(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ProtocolError("Invalid JSON value") from exc


def _invalid_constant(value):
    raise ValueError("Non-finite JSON number")


def decode_json(data):
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, AttributeError, RecursionError) as exc:
        raise ProtocolError("Invalid JSON") from exc
    if not isinstance(value, dict):
        raise ProtocolError("Expected a JSON object")
    return value


def encode_message(message, *, max_length=MAX_CONTROL_LINE):
    """Frame P2-compatible JSON; authentication/routing remain P2's concern."""
    data = encode_json(message) + b"\n"
    decode_message(data, max_length=max_length)
    return data


def decode_message(data, *, max_length=MAX_CONTROL_LINE):
    if type(max_length) is not int or max_length < 1:
        raise ValueError("Message limit must be a positive integer")
    if (
        not isinstance(data, bytes)
        or not data.endswith(b"\n")
        or len(data) > max_length
    ):
        raise ProtocolError("Expected a bounded LF-terminated message")
    message = decode_json(data)
    if not any(
        isinstance(message.get(key), str) for key in ("action", "type", "status")
    ):
        raise ProtocolError("Missing action, type, or status")
    return message


def validate_username(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProtocolError("Invalid username")
    if len(value.encode("utf-8")) > 64 or any(
        ord(c) < 32 or ord(c) == 127 for c in value
    ):
        raise ProtocolError("Invalid username")
    return value


def validate_filename(value):
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ProtocolError("Invalid filename")
    if (
        len(value.encode("utf-8")) > 128
        or value.endswith((".", " "))
        or any(c in '/\\:*?"<>|' or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ProtocolError("Filename must be a portable basename")
    stem = value.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} | {
        prefix + str(i) for prefix in ("COM", "LPT") for i in range(1, 10)
    }:
        raise ProtocolError("Reserved filename")
    return value


@dataclass(frozen=True)
class FileOffer:
    recipient: str
    filename: str
    size: int
    sha256: str
    sender: str = ""
    chunk_size: int = CHUNK_SIZE

    def __post_init__(self):
        if type(self.chunk_size) is not int or self.chunk_size not in {
            CHUNK_SIZE,
            SECURE_CHUNK_SIZE,
        }:
            raise ProtocolError("Unsupported chunk size")
        validate_username(self.recipient)
        validate_filename(self.filename)
        if not isinstance(self.sender, str):
            raise ProtocolError("Invalid sender")
        if self.sender:
            validate_username(self.sender)
        if type(self.size) is not int or not 0 <= self.size <= MAX_FILE_SIZE:
            raise ProtocolError("File exceeds size limit")
        if not isinstance(self.sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.sha256
        ):
            raise ProtocolError("Invalid SHA-256")

    @property
    def total_chunks(self):
        return (self.size + self.chunk_size - 1) // self.chunk_size

    def chunk_length(self, sequence):
        if not 0 <= sequence < self.total_chunks:
            raise ProtocolError("Chunk sequence out of range")
        return min(self.chunk_size, self.size - sequence * self.chunk_size)

    def to_bytes(self):
        fields = dict(
            recipient=self.recipient,
            filename=self.filename,
            size=self.size,
            sha256=self.sha256,
            chunk_size=self.chunk_size,
            total_chunks=self.total_chunks,
        )
        if self.sender:
            fields["sender"] = self.sender
        data = encode_json(fields)
        if len(data) > CHUNK_SIZE:
            raise ProtocolError("Metadata too large")
        return data

    @classmethod
    def from_bytes(cls, data, sender=None):
        value = decode_json(data)
        try:
            offer = cls(
                value["recipient"],
                value["filename"],
                value["size"],
                value["sha256"],
                value.get("sender", "") if sender is None else sender,
                value["chunk_size"],
            )
        except (KeyError, TypeError, UnicodeError) as exc:
            raise ProtocolError("Invalid file metadata") from exc
        if (
            type(value.get("chunk_size")) is not int
            or value["chunk_size"] != offer.chunk_size
            or type(value.get("total_chunks")) is not int
            or value["total_chunks"] != offer.total_chunks
        ):
            raise ProtocolError("Inconsistent chunk metadata")
        return offer


@dataclass(frozen=True)
class SessionTicket:
    username: str
    session_id: uuid.UUID
    key: bytes = field(repr=False)
    version: int = 1
    c2s: bytes = field(default=b"", repr=False)
    s2c: bytes = field(default=b"", repr=False)

    def __post_init__(self):
        validate_username(self.username)
        _validate_key(self.key)
        if self.version not in {1, 2}:
            raise ProtocolError("Unsupported ticket version")
        if self.version == 2:
            _validate_key(self.c2s)
            _validate_key(self.s2c)
            if len({self.key, self.c2s, self.s2c}) != 3:
                raise ProtocolError("HMAC and AES keys must be independent")
        if not isinstance(self.session_id, uuid.UUID) or self.session_id == ZERO_ID:
            raise ProtocolError("Invalid session ID")

    def to_dict(self):
        """Private credentials: return only to the authenticated owner."""
        value = dict(
            username=self.username, session_id=str(self.session_id), key=self.key.hex()
        )
        if self.version == 2:
            value.update(version=2, c2s=self.c2s.hex(), s2c=self.s2c.hex())
        return value

    @classmethod
    def from_dict(cls, value):
        try:
            return cls(
                value["username"],
                uuid.UUID(value["session_id"]),
                bytes.fromhex(value["key"]),
                value.get("version", 1),
                bytes.fromhex(value.get("c2s", "")),
                bytes.fromhex(value.get("s2c", "")),
            )
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ProtocolError("Invalid session ticket") from exc


def file_digest(stream):
    """Hash a seekable binary file with bounded memory, restoring its position."""
    position = stream.tell()
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return size, digest.hexdigest()
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise ProtocolError("File exceeds size limit")
            digest.update(chunk)
    finally:
        stream.seek(position)
