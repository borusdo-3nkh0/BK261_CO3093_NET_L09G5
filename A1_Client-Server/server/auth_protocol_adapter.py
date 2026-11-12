import json


class AuthProtocolAdapter:
    """Temporary JSON adapter for authentication messages."""

    @staticmethod
    def decode_request(data: bytes) -> dict:
        """Convert JSON bytes into an authentication request."""

        if not isinstance(data, bytes):
            raise ValueError("Request must be bytes")

        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON request") from exc

        if not isinstance(message, dict):
            raise ValueError("Request must be a JSON object")

        action = message.get("action")
        username = message.get("username")
        password = message.get("password")

        if not isinstance(action, str):
            raise ValueError("Invalid action")

        if not isinstance(username, str):
            raise ValueError("Invalid username")

        if not isinstance(password, str):
            raise ValueError("Invalid password")

        return {"action": action, "username": username, "password": password}

    @staticmethod
    def encode_response(status: str) -> bytes:
        """Convert authentication status into JSON bytes."""

        if not isinstance(status, str):
            raise ValueError("Status must be a string")

        message = {"status": status}

        return json.dumps(message).encode("utf-8") + b"\n"
