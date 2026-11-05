
import hashlib
import hmac
import secrets


class AuthManager:
    """Manage user authentication for the server."""

    def __init__(self):
        self.users = {}

    def register(self, username: str, password: str) -> bool:
        """Register a new user."""

        if not isinstance(username, str) or not username.strip():
            return False

        if not isinstance(password, str) or not password:
            return False

        if username in self.users:
            return False

        salt = secrets.token_bytes(16)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            600_000
        )

        self.users[username] = {
            "salt": salt,
            "password_hash": password_hash
        }

        return True

    def authenticate(self, username: str, password: str) -> bool:
        """Verify username and password."""

        if not isinstance(username, str):
            return False

        if not isinstance(password, str):
            return False

        user = self.users.get(username)

        if user is None:
            return False

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            user["salt"],
            600_000
        )

        return hmac.compare_digest(
            password_hash,
            user["password_hash"]
        )
