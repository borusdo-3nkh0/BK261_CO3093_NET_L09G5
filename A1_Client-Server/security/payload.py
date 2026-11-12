"""AES-GCM for bytes, with caller-supplied keys and no packet serialization.

Never reuse a nonce with the same key. Encryption generates a random 96-bit
nonce per call; randomness does not guarantee global uniqueness. Key lifecycle,
usage limits and coordination across clients remain integration decisions.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_payload(payload: bytes, *, key: bytes) -> tuple[bytes, bytes]:
    """Return (12-byte nonce, ciphertext with the library's 16-byte tag).

    key must be 16, 24 or 32 bytes. No key generation/storage is performed.
    No associated data is used; packet headers are outside this module's scope.
    """
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if not isinstance(key, bytes):
        raise TypeError("key must be bytes")
    cipher = AESGCM(key)
    nonce = os.urandom(12)
    return nonce, cipher.encrypt(nonce, payload, associated_data=None)


def decrypt_payload(nonce: bytes, ciphertext: bytes, *, key: bytes) -> bytes:
    """Return authenticated plaintext, or propagate cryptography's InvalidTag.

    A wrong key, nonce, modified ciphertext/tag or truncated ciphertext fails
    authentication. Invalid input types/lengths raise TypeError/ValueError.
    No unauthenticated plaintext is returned and no input data is logged.
    """
    if not isinstance(nonce, bytes):
        raise TypeError("nonce must be bytes")
    if not isinstance(ciphertext, bytes):
        raise TypeError("ciphertext must be bytes")
    if not isinstance(key, bytes):
        raise TypeError("key must be bytes")
    if len(nonce) != 12:
        raise ValueError("nonce must be exactly 12 bytes")
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
