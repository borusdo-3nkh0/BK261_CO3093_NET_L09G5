import concurrent.futures

import pytest

from security.context import Context, SecurityError, new_material
from security.udp import PacketCodec
from shared.protocol import (
    MAX_DATAGRAM,
    MessageType,
    Packet,
    ProtocolError,
    SessionTicket,
)


def test_context_nonce_threads_reorder_replay_and_close():
    material = new_material()
    sender, receiver = Context(material), Context(material, server=True)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        frames = list(
            pool.map(lambda _: sender.seal(b"payload", b"route"), range(1000))
        )
    assert len({frame[:12] for frame in frames}) == 1000
    for frame in reversed(frames):
        assert receiver.open(frame, b"route") == b"payload"
    with pytest.raises(SecurityError):
        receiver.open(frames[0], b"route")
    sender.close()
    with pytest.raises(SecurityError):
        sender.seal(b"x")


@pytest.mark.parametrize("fault", ["key", "tag", "aad", "direction"])
def test_context_rejects_without_consuming_nonce(fault):
    material = new_material()
    sender, receiver = Context(material), Context(material, server=True)
    frame, aad = sender.seal(b"private", b"route"), b"route"
    if fault == "key":
        bad = Context(new_material(), server=True)
    elif fault == "direction":
        bad = Context(material)
    else:
        bad = receiver
    if fault == "tag":
        frame = frame[:-1] + bytes([frame[-1] ^ 1])
    if fault == "aad":
        aad = b"other route"
    with pytest.raises(SecurityError):
        bad.open(frame, aad)
    assert (
        receiver.open(sender.seal(b"still usable", b"route"), b"route")
        == b"still usable"
    )


def test_secure_packet_budget_and_v1_rejection():
    import secrets
    import uuid

    material = new_material()
    ticket = SessionTicket(
        "alice",
        uuid.UUID(material["session_id"]),
        secrets.token_bytes(32),
        2,
        bytes.fromhex(material["c2s"]),
        bytes.fromhex(material["s2c"]),
    )
    client, server = PacketCodec(ticket), PacketCodec(ticket, server=True)
    packet = Packet(
        MessageType.DATA, ticket.session_id, uuid.uuid4(), payload=b"x" * 996
    )
    wire = client.encode(packet)
    assert len(wire) == MAX_DATAGRAM == 1084 and b"x" * 64 not in wire
    assert server.decode(wire) == packet
    with pytest.raises(ProtocolError):
        server.decode(wire)
    from shared.protocol import encode_packet

    with pytest.raises(ProtocolError):
        server.decode(encode_packet(packet, ticket.key))


def test_reports_redact_new_directional_keys():
    from p3 import public, public_text

    assert public({"c2s": "secret-canary", "s2c": "secret-canary"}) == {
        "c2s": "[REDACTED]",
        "s2c": "[REDACTED]",
    }
    assert "secret-canary" not in public_text("c2s='secret-canary' s2c='secret-canary'")
