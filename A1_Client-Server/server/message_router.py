import json
import socket
import threading

from security.context import chat_aad


class MessageRouter:
    """Manage online clients for message routing."""

    def __init__(self):
        self.clients = {}
        self.lock = threading.Lock()
        self.send_locks = {}
        self.crypto = {}

    def register_client(self, username, client_socket, *, crypto=None, welcome=None):
        """Register an authenticated client."""

        if not isinstance(username, str) or not username:
            return False

        if client_socket is None:
            return False

        with self.lock:
            if username in self.clients:
                return False

            if welcome is not None:
                try:
                    client_socket.sendall(welcome)
                except OSError:
                    return False
            self.crypto[username] = crypto
            self.clients[username] = client_socket
            self.send_locks[username] = threading.Lock()
            return True

    def unregister_client(self, username):
        """Remove a client and its send lock."""

        with self.lock:
            removed = self.clients.pop(username, None)
            self.send_locks.pop(username, None)
            crypto = self.crypto.pop(username, None)
            if crypto:
                crypto.close()

            return removed is not None

    def get_client(self, username):
        """Find a client's socket by username."""

        with self.lock:
            return self.clients.get(username)

    def get_online_users(self):
        """Return a snapshot of online usernames."""

        with self.lock:
            return list(self.clients.keys())

    def send_to_client(self, username, data, *, expected_socket=None):
        """Send bytes using the recipient's dedicated lock."""

        if not isinstance(data, bytes):
            return False

        with self.lock:
            client_socket = self.clients.get(username)
            send_lock = self.send_locks.get(username)

        if (
            client_socket is None
            or send_lock is None
            or (expected_socket is not None and client_socket is not expected_socket)
        ):
            return False

        try:
            with send_lock:
                # Avoid sending to a client that was unregistered
                # while waiting to acquire its send lock.
                with self.lock:
                    if (
                        self.clients.get(username) is not client_socket
                        or self.send_locks.get(username) is not send_lock
                    ):
                        return False

                client_socket.sendall(data)

            return True

        except (OSError, socket.timeout):
            return False

    def _send_chat(self, username, payload):
        with self.lock:
            expected = self.clients.get(username)
            if expected is None:
                return False
            crypto = self.crypto.get(username)
            if crypto:
                payload = dict(
                    payload,
                    message=crypto.encrypt_text(
                        payload["message"],
                        chat_aad(
                            payload["type"], payload["sender"], payload.get("recipient")
                        ),
                    ),
                )
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        return self.send_to_client(username, data, expected_socket=expected)

    def send_unicast(self, sender, recipient, message):
        """Send a message to one online recipient."""

        if not isinstance(sender, str) or not sender:
            return False

        if not isinstance(recipient, str) or not recipient:
            return False

        if not isinstance(message, str) or not message:
            return False

        payload = {
            "type": "UNICAST",
            "sender": sender,
            "recipient": recipient,
            "message": message,
        }

        return self._send_chat(recipient, payload)

    def send_broadcast(self, sender, message):
        """Send a message to all online clients except sender."""

        if not isinstance(sender, str) or not sender:
            return 0

        if not isinstance(message, str) or not message:
            return 0

        payload = {"type": "BROADCAST", "sender": sender, "message": message}

        # Snapshot recipients without holding the lock during I/O.
        with self.lock:
            recipients = [username for username in self.clients if username != sender]

        success_count = 0

        for username in recipients:
            if self._send_chat(username, payload):
                success_count += 1

        return success_count
