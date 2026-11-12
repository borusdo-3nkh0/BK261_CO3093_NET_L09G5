from unittest.mock import patch
import json
import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestFileSessionIntegration(unittest.TestCase):

    def setUp(self):
        self.server = SocketServer(
            host="127.0.0.1",
            port=0,
            udp_port=0,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )
        self.server_thread.start()

        deadline = time.monotonic() + 3.0

        while time.monotonic() < deadline:
            relay = self.server.file_relay
            tcp_socket = self.server.server_socket

            if tcp_socket is not None:
                try:
                    self.port = tcp_socket.getsockname()[1]
                    relay.address

                    with socket.create_connection(
                        ("127.0.0.1", self.port),
                        timeout=0.2,
                    ) as probe:
                        probe.sendall(b"HELLO\n")
                        if probe.recv(1024) == b"WELCOME\n":
                            return

                except (OSError, RuntimeError):
                    pass

            time.sleep(0.02)

        self.server.stop()
        self.server_thread.join(timeout=3)
        self.fail("TCP server or UDP relay did not start")

    def tearDown(self):
        self.server.stop()
        self.server_thread.join(timeout=3)
        self.assertFalse(self.server_thread.is_alive())

    def connect(self):
        client = socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=3,
        )
        client.settimeout(3)
        client.sendall(b"HELLO\n")
        self.assertEqual(self.read_line(client), b"WELCOME\n")
        return client

    @staticmethod
    def read_line(client):
        data = bytearray()
        while not data.endswith(b"\n"):
            chunk = client.recv(1)
            if not chunk:
                raise ConnectionError("Connection closed")
            data.extend(chunk)
        return bytes(data)

    def request(self, client, payload):
        client.sendall(
            (json.dumps(payload) + "\n").encode("utf-8")
        )
        return json.loads(self.read_line(client))

    def login(self, client):
        result = self.request(
            client,
            {
                "action": "REGISTER",
                "username": "alice",
                "password": "pass123",
            },
        )
        self.assertEqual(result["status"], "REGISTER_SUCCESS")

        result = self.request(
            client,
            {
                "action": "LOGIN",
                "username": "alice",
                "password": "pass123",
            },
        )
        self.assertEqual(result["status"], "LOGIN_SUCCESS")

    def test_file_session_requires_login(self):
        with self.connect() as client:
            response = self.request(
                client, {"action": "FILE_SESSION"}
            )
            self.assertEqual(
                response["status"], "AUTH_REQUIRED"
            )

    def test_file_session_ready(self):
        with self.connect() as client:
            self.login(client)

            response = self.request(
                client, {"action": "FILE_SESSION"}
            )

            self.assertEqual(
                response["status"], "FILE_SESSION_READY"
            )
            self.assertIn("ticket", response)
            self.assertEqual(
                response["udp_port"],
                self.server.file_relay.address[1],
            )

    def test_file_session_is_idempotent(self):
        with self.connect() as client:
            self.login(client)

            first = self.request(
                client, {"action": "FILE_SESSION"}
            )
            second = self.request(
                client, {"action": "FILE_SESSION"}
            )

            self.assertEqual(
                first["status"], "FILE_SESSION_READY"
            )
            self.assertEqual(first["ticket"], second["ticket"])

    def test_ticket_revoked_after_disconnect(self):
        client = self.connect()
        self.login(client)

        response = self.request(
            client, {"action": "FILE_SESSION"}
        )
        self.assertEqual(
            response["status"], "FILE_SESSION_READY"
        )

        client.close()

        deadline = time.monotonic() + 3.0

        while time.monotonic() < deadline:
            if (
                self.server.session_manager.get_session("alice")
                is None
            ):
                break
            time.sleep(0.02)

        self.assertIsNone(
            self.server.session_manager.get_session("alice")
        )
        self.assertNotIn(
            "alice",
            self.server.file_relay._usernames,
        )

    def test_ping_before_login(self):
        """PING should work after handshake without login."""
        with self.connect() as client:
            response = self.request(
                client,
                {"action": "PING"}
            )

            self.assertEqual(
                response["status"],
                "PONG"
            )

    def test_ping_after_login(self):
        """PING should work after successful login."""
        with self.connect() as client:
            self.login(client)

            response = self.request(
                client,
                {"action": "PING"}
            )

            self.assertEqual(
                response["status"],
                "PONG"
            )
    def test_file_session_registration_failure(self):
        """Relay failure must not terminate TCP connection."""
        with self.connect() as client:
            self.login(client)

            with patch.object(
                self.server.file_relay,
                "register_session",
                side_effect=RuntimeError("Relay unavailable"),
            ):
                response = self.request(
                    client,
                    {"action": "FILE_SESSION"}
                )

            self.assertEqual(
                response["status"],
                "FILE_SESSION_FAILED"
            )

            # TCP connection must remain usable.
            response = self.request(
                client,
                {"action": "PING"}
            )

            self.assertEqual(response["status"], "PONG")
    def test_cleanup_continues_when_udp_revoke_fails(self):
        """TCP session must be cleaned up even if UDP revoke fails."""
        client = self.connect()
        self.login(client)

        response = self.request(
            client,
            {"action": "FILE_SESSION"}
        )
        self.assertEqual(response["status"], "FILE_SESSION_READY")

        with patch.object(
            self.server.file_relay,
            "unregister_session",
            side_effect=RuntimeError("Simulated cleanup failure"),
        ):
            client.close()

            deadline = time.monotonic() + 3.0

            while time.monotonic() < deadline:
                if self.server.session_manager.get_session("alice") is None:
                    break
                time.sleep(0.02)

            self.assertIsNone(
                self.server.session_manager.get_session("alice")
            )

    def test_relay_closes_after_client_cleanup(self):
        """UDP Relay must close after TCP client cleanup."""

        client = self.connect()
        self.login(client)

        response = self.request(
            client,
            {"action": "FILE_SESSION"}
        )
        self.assertEqual(
            response["status"],
            "FILE_SESSION_READY"
        )

        cleanup_started = threading.Event()
        allow_cleanup = threading.Event()
        relay_closed = threading.Event()

        original_unregister = (
            self.server.file_relay.unregister_session
        )
        original_close = self.server.file_relay.close

        def delayed_unregister(username):
            cleanup_started.set()

            if not allow_cleanup.wait(timeout=5):
                raise RuntimeError("Cleanup was not released")

            return original_unregister(username)

        def tracked_close():
            relay_closed.set()
            return original_close()

        try:
            with patch.object(
                self.server.file_relay,
                "unregister_session",
                side_effect=delayed_unregister,
            ), patch.object(
                self.server.file_relay,
                "close",
                side_effect=tracked_close,
            ):
                # Trigger TCP client cleanup.
                client.close()

                self.assertTrue(
                    cleanup_started.wait(timeout=3),
                    "Client cleanup did not start",
                )

                # Request shutdown while cleanup is blocked.
                shutdown_thread = threading.Thread(
                    target=self.server.stop,
                    daemon=True,
                )
                shutdown_thread.start()

                # Wait for the accept loop to observe shutdown.
                shutdown_thread.join(timeout=0.2)

                # Relay must remain open during client cleanup.
                self.assertFalse(
                    relay_closed.is_set(),
                    "UDP Relay closed before client cleanup",
                )

                allow_cleanup.set()

                shutdown_thread.join(timeout=6)
                self.server_thread.join(timeout=6)

                self.assertFalse(
                    shutdown_thread.is_alive()
                )
                self.assertFalse(
                    self.server_thread.is_alive()
                )
                self.assertTrue(relay_closed.is_set())

        finally:
            allow_cleanup.set()
            client.close()

if __name__ == "__main__":
    unittest.main()
