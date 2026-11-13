import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from security.payload import decrypt_payload, encrypt_payload


@pytest.fixture
def key():
    # Ephemeral test key: never read keys from disk or log them.
    return AESGCM.generate_key(bit_length=256)


@pytest.mark.parametrize("bit_length", [128, 192, 256])
@pytest.mark.parametrize(
    "payload",
    [b"", b"hello", "Tin nhắn tiếng Việt".encode(), bytes(range(256)) * 8],
    ids=["empty", "ascii", "utf8", "binary"],
)
def test_round_trip(bit_length, payload):
    key = AESGCM.generate_key(bit_length=bit_length)
    nonce, ciphertext = encrypt_payload(payload, key=key)

    assert isinstance(nonce, bytes) and len(nonce) == 12
    assert isinstance(ciphertext, bytes) and len(ciphertext) == len(payload) + 16
    assert decrypt_payload(nonce, ciphertext, key=key) == payload


def test_wrong_key_fails(key):
    nonce, ciphertext = encrypt_payload(b"payload", key=key)
    wrong_key = bytes([key[0] ^ 1]) + key[1:]

    with pytest.raises(InvalidTag):
        decrypt_payload(nonce, ciphertext, key=wrong_key)


@pytest.mark.parametrize("change", ["ciphertext", "tag", "nonce", "truncated"])
def test_tampering_fails(key, change):
    nonce, ciphertext = encrypt_payload(b"binary\x00\xffpayload", key=key)
    if change == "ciphertext":
        ciphertext = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
    elif change == "tag":
        ciphertext = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    elif change == "nonce":
        nonce = bytes([nonce[0] ^ 1]) + nonce[1:]
    else:
        ciphertext = ciphertext[:8]

    with pytest.raises(InvalidTag):
        decrypt_payload(nonce, ciphertext, key=key)


def test_each_encryption_has_a_fresh_nonce(key):
    first_nonce, first_ciphertext = encrypt_payload(b"same payload", key=key)
    second_nonce, second_ciphertext = encrypt_payload(b"same payload", key=key)

    assert first_nonce != second_nonce
    assert first_ciphertext != second_ciphertext


@pytest.mark.parametrize("key_length", [0, 15, 17, 31])
def test_invalid_key_length_is_rejected(key_length):
    invalid_key = bytes(key_length)
    with pytest.raises(ValueError):
        encrypt_payload(b"payload", key=invalid_key)
    with pytest.raises(ValueError):
        decrypt_payload(bytes(12), bytes(16), key=invalid_key)


@pytest.mark.parametrize("nonce_length", [0, 8, 13])
def test_decryption_requires_96_bit_nonce(key, nonce_length):
    with pytest.raises(ValueError, match="nonce must be exactly 12 bytes"):
        decrypt_payload(bytes(nonce_length), bytes(16), key=key)


@pytest.mark.parametrize("field", ["payload", "key", "nonce", "ciphertext"])
def test_non_bytes_input_is_rejected(key, field):
    if field == "payload":
        with pytest.raises(TypeError, match="payload must be bytes"):
            encrypt_payload("not bytes", key=key)
    elif field == "key":
        with pytest.raises(TypeError, match="key must be bytes"):
            encrypt_payload(b"payload", key="not bytes")
        with pytest.raises(TypeError, match="key must be bytes"):
            decrypt_payload(bytes(12), bytes(16), key="not bytes")
    else:
        arguments = {"nonce": bytes(12), "ciphertext": bytes(16), "key": key}
        arguments[field] = "not bytes"
        with pytest.raises(TypeError, match=f"{field} must be bytes"):
            decrypt_payload(**arguments)
