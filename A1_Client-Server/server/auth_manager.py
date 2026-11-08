
import hashlib
import hmac
import secrets
import threading


class AuthManager:
    """Manage user authentication safely across threads."""

    def __init__(self):
        self.users = {}
        self._lock = threading.Lock()

    def register(self, username: str, password: str) -> bool:
        """Register a new user safely."""

        if not isinstance(username, str) or not username.strip():
            return False

        if not isinstance(password, str) or not password:
            return False

        # Generate salt and hash the password.
        salt = secrets.token_bytes(16)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            600_000
        )

        # Check and insert atomically.
        with self._lock:
            if username in self.users:
                return False

            self.users[username] = {
                "salt": salt,
                "password_hash": password_hash
            }

        return True

    def authenticate(self, username: str, password: str) -> bool:
        """Verify username and password safely."""

        if not isinstance(username, str):
            return False

        if not isinstance(password, str):
            return False

        # Read shared user data under the lock.
        with self._lock:
            user = self.users.get(username)

            if user is None:
                return False

            salt = user["salt"]
            stored_hash = user["password_hash"]

        # Perform expensive hashing outside the lock.
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            600_000
        )

        return hmac.compare_digest(
            password_hash,
            stored_hash
        )
