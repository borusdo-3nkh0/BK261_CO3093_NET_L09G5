"""V2 UDP codec: unchanged header/HMAC, authenticated encrypted payload."""

import hmac

from security.context import Context, SecurityError
from shared.protocol import (
    HEADER,
    MAGIC,
    SECURE_CHUNK_SIZE,
    TAG_SIZE,
    MessageType,
    Packet,
    ProtocolError,
    _validate_packet,
    peek_session_id,
)


class PacketCodec:
    def __init__(self, ticket, *, server=False):
        self.ticket = ticket
        self.context = Context(
            dict(
                version=2,
                session_id=str(ticket.session_id),
                c2s=ticket.c2s.hex(),
                s2c=ticket.s2c.hex(),
            ),
            server=server,
            purpose="file",
        )

    def encode(self, packet):
        _validate_packet(packet)
        if (
            packet.session_id != self.ticket.session_id
            or len(packet.payload) > SECURE_CHUNK_SIZE
        ):
            raise ProtocolError("Invalid secure packet")
        header = HEADER.pack(
            MAGIC,
            2,
            int(packet.kind),
            packet.session_id.bytes,
            packet.transfer_id.bytes,
            packet.sequence,
            len(packet.payload) + 28,
        )
        body = header + self.context.seal(packet.payload, header)
        return body + hmac.digest(self.ticket.key, body, "sha256")[:TAG_SIZE]

    def decode(self, data):
        if peek_session_id(data) != self.ticket.session_id or data[4] != 2:
            raise ProtocolError("Secure packet version/session mismatch")
        body, tag = data[:-TAG_SIZE], data[-TAG_SIZE:]
        if not hmac.compare_digest(
            tag, hmac.digest(self.ticket.key, body, "sha256")[:TAG_SIZE]
        ):
            raise ProtocolError("Invalid authentication tag")
        try:
            payload = self.context.open(body[HEADER.size :], body[: HEADER.size])
            _, _, kind, session, transfer, sequence, _ = HEADER.unpack_from(body)
            import uuid

            packet = Packet(
                MessageType(kind),
                uuid.UUID(bytes=session),
                uuid.UUID(bytes=transfer),
                sequence,
                payload,
            )
            _validate_packet(packet)
            if len(payload) > SECURE_CHUNK_SIZE:
                raise ValueError()
            return packet
        except (SecurityError, ValueError) as error:
            raise ProtocolError("Invalid encrypted datagram") from error
