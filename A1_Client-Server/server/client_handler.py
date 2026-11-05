
import logging

from server.auth_manager import AuthManager


logger = logging.getLogger(__name__)


class ClientHandler:
    """Handle client authentication requests."""

    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager

    def handle_register(self, username: str, password: str) -> bool:
        """Process a user registration request."""

        result = self.auth_manager.register(username, password)

        if result:
            logger.info("User registered successfully: %s", username)
        else:
            logger.warning("User registration failed")

        return result

    def handle_login(self, username: str, password: str) -> bool:
        """Process a user login request."""

        result = self.auth_manager.authenticate(username, password)

        if result:
            logger.info("User authenticated successfully: %s", username)
        else:
            logger.warning("User authentication failed")

        return result

    def process_auth_request(
        self,
        action: str,
        username: str,
        password: str
    ) -> str:
        """Process an authentication request."""

        if action == "REGISTER":
            success = self.handle_register(username, password)

            if success:
                return "REGISTER_SUCCESS"

            return "REGISTER_FAILED"

        if action == "LOGIN":
            success = self.handle_login(username, password)

            if success:
                return "LOGIN_SUCCESS"

            return "LOGIN_FAILED"

        return "UNKNOWN_ACTION"
