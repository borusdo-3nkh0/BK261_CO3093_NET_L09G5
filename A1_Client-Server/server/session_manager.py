
import logging
import threading

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage active user sessions safely across threads."""

    def __init__(self):
        self.sessions = {}
        self._lock = threading.Lock()

    def add_session(self, username: str, ip: str, port: int) -> bool:
        """Add a session if the username is not already online."""

        if not isinstance(username, str) or not username.strip():
            return False

        if not isinstance(ip, str) or not ip.strip():
            return False

        if not isinstance(port, int) or isinstance(port, bool):
            return False

        if not (1 <= port <= 65535):
            return False

        with self._lock:
            if username in self.sessions:
                logger.warning(
                    "User already has an active session"
                )
                return False

            self.sessions[username] = {
                "username": username,
                "ip": ip,
                "port": port,
                "status": "online"
            }

        logger.info("Session created for user: %s", username)
        return True

    def remove_session(self, username: str) -> bool:
        """Remove an existing session safely."""

        with self._lock:
            if username not in self.sessions:
                return False

            del self.sessions[username]

        logger.info("Session removed for user: %s", username)
        return True

    def get_session(self, username: str):
        """Return a copy of a session or None."""

        with self._lock:
            session = self.sessions.get(username)

            if session is None:
                return None

            return session.copy()
