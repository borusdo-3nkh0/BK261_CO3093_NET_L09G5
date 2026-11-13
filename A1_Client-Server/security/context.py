"""Small v2 session context shared by chat and UDP. Keys never leave Python/TLS."""

import base64
import json
import secrets
import threading
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecurityError(ValueError):
    pass


def new_material():
    return dict(
        version=2,
        session_id=str(uuid.uuid4()),
        c2s=secrets.token_hex(32),
        s2c=secrets.token_hex(32),
    )


def chat_aad(kind, sender, recipient):
    return json.dumps(
        [kind, sender, recipient], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


class Context:
    """One owner per direction/key. Never reset or clone a live context.

    New sessions get new keys. Counters are locked, 96-bit, fail on exhaustion.
    A 4096-counter receive window allows UDP loss/reorder; retries use new nonces.
    """

    def __init__(self, material, *, server=False, purpose="chat"):
        try:
            if type(material["version"]) is not int or material["version"] != 2:
                raise ValueError()
            self.sid = uuid.UUID(material["session_id"])
            if self.sid.int == 0:
                raise ValueError()
            c2s, s2c = bytes.fromhex(material["c2s"]), bytes.fromhex(material["s2c"])
            if len(c2s) != 32 or len(s2c) != 32 or c2s == s2c:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise SecurityError("Invalid v2 security context") from error
        self.tx, self.rx = (
            (AESGCM(s2c), AESGCM(c2s)) if server else (AESGCM(c2s), AESGCM(s2c))
        )
        prefix = b"Connect-v2/" + purpose.encode("ascii") + b"/" + self.sid.bytes
        self.tx_aad = prefix + (b"/s2c/" if server else b"/c2s/")
        self.rx_aad = prefix + (b"/c2s/" if server else b"/s2c/")
        self.counter, self.highest, self.seen = 0, -1, 0
        self.lock = threading.RLock()

    def seal(self, payload, aad=b""):
        with self.lock:
            if self.tx is None or self.counter >= 1 << 96:
                raise SecurityError("Security context expired")
            nonce = self.counter.to_bytes(12, "big")
            self.counter += 1
            return nonce + self.tx.encrypt(nonce, payload, self.tx_aad + aad)

    def open(self, data, aad=b""):
        with self.lock:
            if self.rx is None or len(data) < 28:
                raise SecurityError("Invalid encrypted payload")
            nonce, ciphertext = data[:12], data[12:]
            try:
                payload = self.rx.decrypt(nonce, ciphertext, self.rx_aad + aad)
            except InvalidTag as error:
                raise SecurityError("Payload authentication failed") from error
            number = int.from_bytes(nonce, "big")
            distance = self.highest - number
            if distance >= 4096 or (distance >= 0 and self.seen & (1 << distance)):
                raise SecurityError("Replayed payload")
            if number > self.highest:
                shift = number - self.highest
                self.seen = (
                    0 if shift >= 4096 else (self.seen << shift) & ((1 << 4096) - 1)
                )
                self.highest = number
            self.seen |= 1 << (self.highest - number)
            return payload

    def encrypt_text(self, text, aad):
        return dict(
            v=2,
            sid=str(self.sid),
            data=base64.b64encode(self.seal(text.encode("utf-8"), aad)).decode("ascii"),
        )

    def decrypt_text(self, value, aad):
        try:
            if (
                set(value) != {"v", "sid", "data"}
                or value["v"] != 2
                or value["sid"] != str(self.sid)
            ):
                raise ValueError()
            return self.open(
                base64.b64decode(value["data"], validate=True), aad
            ).decode("utf-8")
        except (ValueError, TypeError, KeyError, UnicodeError) as error:
            raise SecurityError("Invalid encrypted message") from error

    def close(self):
        with self.lock:
            self.tx = self.rx = None
