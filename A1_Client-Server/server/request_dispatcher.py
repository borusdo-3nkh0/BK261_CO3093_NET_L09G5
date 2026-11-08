
import json


class RequestDispatcher:
    """Decode and classify incoming client requests."""

    AUTH_ACTIONS = {"REGISTER", "LOGIN"}
    MESSAGE_ACTIONS = {"UNICAST", "BROADCAST"}

    @classmethod
    def decode_request(cls, data: bytes) -> dict:
        """Decode one newline-terminated JSON request."""

        if not isinstance(data, bytes):
            raise ValueError("Request must be bytes")

        try:
            request = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON request") from exc

        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")

        action = request.get("action")

        if not isinstance(action, str):
            raise ValueError("Invalid action")

        if action not in cls.AUTH_ACTIONS | cls.MESSAGE_ACTIONS:
            raise ValueError("Unsupported action")

        return request

    @classmethod
    def get_request_type(cls, request: dict) -> str:
        """Classify a decoded request."""

        if not isinstance(request, dict):
            raise ValueError("Request must be a dictionary")

        action = request.get("action")

        if action in cls.AUTH_ACTIONS:
            return "AUTH"

        if action in cls.MESSAGE_ACTIONS:
            return "MESSAGE"

        raise ValueError("Unsupported action")
