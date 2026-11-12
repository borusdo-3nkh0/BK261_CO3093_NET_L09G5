
import json


class RequestDispatcher:
    """Decode and classify incoming client requests."""

    AUTH_ACTIONS = {"REGISTER", "LOGIN"}
    MESSAGE_ACTIONS = {"UNICAST", "BROADCAST"}
    USER_ACTIONS = {"LIST_ONLINE"}
    FILE_ACTIONS = {"FILE_SESSION"}
    SYSTEM_ACTIONS = {"PING"}

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

        supported_actions = (
            cls.AUTH_ACTIONS
            | cls.MESSAGE_ACTIONS
            | cls.USER_ACTIONS
            | cls.FILE_ACTIONS
            | cls.SYSTEM_ACTIONS
        )

        if action not in supported_actions:
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

        if action in cls.USER_ACTIONS:
            return "USER"

        if action in cls.FILE_ACTIONS:
            return "FILE"

        if action in cls.SYSTEM_ACTIONS:
            return "SYSTEM"

        raise ValueError("Unsupported action")
