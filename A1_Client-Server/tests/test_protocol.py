import hashlib
import hmac
import struct
import unittest
import uuid

from shared.protocol import (
    CHUNK_SIZE,
    HEADER,
    MAX_DATAGRAM,
    MAX_FILE_SIZE,
    MAX_RESPONSE_LINE,
    FileOffer,
    MessageType,
    Packet,
    ProtocolError,
    SessionTicket,
    ZERO_ID,
    decode_message,
    decode_packet,
    encode_json,
    encode_message,
    encode_packet,
    validate_filename,
)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))
        self.session = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        self.transfer = uuid.UUID("ffeeddcc-bbaa-9988-7766-554433221100")

    def test_independent_wire_fixture_has_documented_offsets_and_tag(self):
        # Construct from the published layout, independently of the production encoder.
        header = b"P1FT\x01\x06" + self.session.bytes + self.transfer.bytes
        body = header + struct.pack("!IH", 0x01020304, 3) + b"abc"
        fixture = body + hmac.new(self.key, body, hashlib.sha256).digest()[:16]
        packet = decode_packet(fixture, self.key)
        self.assertEqual(
            packet,
            Packet(MessageType.DATA, self.session, self.transfer, 0x01020304, b"abc"),
        )
        self.assertEqual(encode_packet(packet, self.key), fixture)
        self.assertEqual(HEADER.size, 44)

    def test_maximum_datagram_size(self):
        packet = Packet(
            MessageType.DATA, self.session, self.transfer, 0, b"a" * CHUNK_SIZE
        )
        self.assertEqual(len(encode_packet(packet, self.key)), MAX_DATAGRAM)

    def test_corruption_wrong_key_truncation_and_trailing_bytes_rejected(self):
        data = encode_packet(
            Packet(MessageType.DATA, self.session, self.transfer, payload=b"data"),
            self.key,
        )
        corrupt = bytearray(data)
        corrupt[44] ^= 1
        for candidate, key in (
            (bytes(corrupt), self.key),
            (data, b"x" * 32),
            (data[:-1], self.key),
            (data + b"x", self.key),
        ):
            with (
                self.subTest(candidate=candidate, key=key),
                self.assertRaises(ProtocolError),
            ):
                decode_packet(candidate, key)

    def test_authenticated_unsupported_version_type_and_length_rejected(self):
        data = encode_packet(
            Packet(MessageType.ACK, self.session, self.transfer), self.key
        )
        for offset, value in ((4, 2), (5, 255), (43, 1)):
            body = bytearray(data[:-16])
            body[offset] = value
            wire = bytes(body) + hmac.digest(self.key, bytes(body), "sha256")[:16]
            with self.subTest(offset=offset), self.assertRaises(ProtocolError):
                decode_packet(wire, self.key)

    def test_message_semantics_reject_invalid_control_and_sequences(self):
        packets = [
            Packet(MessageType.CHALLENGE, self.session),
            Packet(MessageType.PROVE, self.session, payload=b"short"),
            Packet(MessageType.BIND, self.session, self.transfer),
            Packet(MessageType.ACK, self.session),
            Packet(MessageType.FIN, self.session, self.transfer, 1),
            Packet(MessageType.ACK, self.session, self.transfer, payload=b"bad"),
            Packet(MessageType.DATA, self.session, self.transfer),
            Packet(MessageType.DATA, self.session, self.transfer, -1, b"a"),
        ]
        for packet in packets:
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                encode_packet(packet, self.key)

    def test_offer_empty_and_partial_chunk_arithmetic(self):
        empty = FileOffer("bob", "empty.bin", 0, "0" * 64)
        self.assertEqual(empty.total_chunks, 0)
        offer = FileOffer("bob", "file.bin", 2053, "0" * 64)
        self.assertEqual([offer.chunk_length(i) for i in range(3)], [1024, 1024, 5])
        self.assertEqual(FileOffer.from_bytes(offer.to_bytes()), offer)
        with self.assertRaises(ProtocolError):
            offer.chunk_length(3)

    def test_inconsistent_or_hostile_metadata_is_rejected(self):
        base = dict(
            recipient="bob",
            filename="file.bin",
            size=1025,
            sha256="0" * 64,
            chunk_size=1024,
            total_chunks=2,
        )
        for changes in (
            {"size": True},
            {"size": MAX_FILE_SIZE + 1},
            {"total_chunks": 1},
            {"chunk_size": 4096},
            {"filename": "../escape"},
            {"sha256": "invalid"},
            {"recipient": ""},
            {"sender": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                FileOffer.from_bytes(encode_json(dict(base, **changes)))

    def test_relay_overrides_untrusted_sender(self):
        offer = FileOffer("bob", "file.bin", 0, "0" * 64, sender="forged")
        self.assertEqual(
            FileOffer.from_bytes(offer.to_bytes(), sender="alice").sender, "alice"
        )

    def test_portable_filename_safety(self):
        for name in (
            "..",
            ".",
            "/tmp/file",
            "a/b",
            "a\\b",
            "a\x00b",
            "CON.txt",
            "NUL",
            "x:",
            "x.",
            "x ",
            "a" * 129,
        ):
            with self.subTest(name=name), self.assertRaises(ProtocolError):
                validate_filename(name)
        self.assertEqual(validate_filename("bài tập.pdf"), "bài tập.pdf")

    def test_p2_compatible_tcp_framing(self):
        message = dict(action="UNICAST", recipient="bob", message="xin chào\nnext line")
        wire = encode_message(message)
        self.assertEqual(wire.count(b"\n"), 1)
        self.assertEqual(decode_message(wire), message)
        for wire in (
            b"{}\n",
            b'{"action":"LOGIN"}',
            b"[]\n",
            b'{"action":NaN}\n',
            b'{"action":"LOGIN"}\n{}\n',
            b"x" * 1025 + b"\n",
        ):
            with self.subTest(wire=wire), self.assertRaises(ProtocolError):
                decode_message(wire)

    def test_twenty_unicode_users_fit_response_limit_without_relaxing_requests(self):
        message = {
            "status": "LIST_ONLINE_SUCCESS",
            "users": ["用" * 20 + str(i) for i in range(20)],
        }
        wire = encode_message(message, max_length=MAX_RESPONSE_LINE)
        self.assertGreater(len(wire), 1024)
        self.assertEqual(decode_message(wire, max_length=MAX_RESPONSE_LINE), message)
        with self.assertRaises(ProtocolError):
            decode_message(wire)

    def test_ticket_validation_and_private_serialization(self):
        ticket = SessionTicket("alice", self.session, self.key)
        self.assertEqual(SessionTicket.from_dict(ticket.to_dict()), ticket)
        for changes in ({"key": "00"}, {"session_id": str(ZERO_ID)}, {"username": ""}):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                SessionTicket.from_dict(dict(ticket.to_dict(), **changes))


if __name__ == "__main__":
    unittest.main()
