
import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestSessionIntegration(unittest.TestCase):

    def setUp(self):
        self.server = SocketServer(
            host="127.0.0.1",
            port=0,
            max_clients=1,
            handshake_timeout=0.3,
            idle_timeout=0.5,
            udp_port=0,
        )

    def test_session_lifecycle(self):
        # Use an available local port
        with socket.socket() as temp_socket:
            temp_socket.bind(("127.0.0.1", 0))
            port = temp_socket.getsockname()[1]

        self.server.port = port

        server_thread = threading.Thread(
            target=self.server.start,
            daemon=True
        )
        server_thread.start()

        # Wait for server to start
        time.sleep(0.2)

        with socket.create_connection(
            ("127.0.0.1", port),
            timeout=3
        ) as client:

            client.settimeout(3)

            # Handshake
            client.sendall(b"HELLO\n")
            response = client.recv(1024)
            self.assertEqual(response, b"WELCOME\n")

            # Register
            client.sendall(
                b'{"action":"REGISTER",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )

            response = client.recv(1024)
            self.assertIn(b"REGISTER_SUCCESS", response)

            # Login
            client.sendall(
                b'{"action":"LOGIN",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )

            response = client.recv(1024)
            self.assertIn(b"LOGIN_SUCCESS", response)

            # Session must exist
            session = self.server.session_manager.get_session(
                "alice"
            )

            self.assertIsNotNone(session)
            self.assertEqual(
                session["status"],
                "online"
            )
            self.assertEqual(
                session["ip"],
                "127.0.0.1"
            )

        # Client connection has closed
        server_thread.join(timeout=3)

        # Session must be removed
        session = self.server.session_manager.get_session(
            "alice"
        )

        self.assertIsNone(session)

    def test_login_twice_same_connection(self):
        # Find an available local port
        with socket.socket() as temp_socket:
            temp_socket.bind(("127.0.0.1", 0))
            port = temp_socket.getsockname()[1]

        self.server.port = port

        server_thread = threading.Thread(
            target=self.server.start,
            daemon=True
        )
        server_thread.start()

        time.sleep(0.2)

        with socket.create_connection(
            ("127.0.0.1", port),
            timeout=3
        ) as client:

            client.settimeout(3)

            # Handshake
            client.sendall(b"HELLO\n")
            self.assertEqual(
                client.recv(1024),
                b"WELCOME\n"
            )

            # Register alice
            client.sendall(
                b'{"action":"REGISTER",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )
            self.assertIn(
                b"REGISTER_SUCCESS",
                client.recv(1024)
            )

            # Register bob
            client.sendall(
                b'{"action":"REGISTER",'
                b'"username":"bob",'
                b'"password":"pass456"}\n'
            )
            self.assertIn(
                b"REGISTER_SUCCESS",
                client.recv(1024)
            )

            # First login: alice
            client.sendall(
                b'{"action":"LOGIN",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )
            self.assertIn(
                b"LOGIN_SUCCESS",
                client.recv(1024)
            )

            # Second login: bob on same connection
            client.sendall(
                b'{"action":"LOGIN",'
                b'"username":"bob",'
                b'"password":"pass456"}\n'
            )
            self.assertIn(
                b"ALREADY_AUTHENTICATED",
                client.recv(1024)
            )

            # Alice remains online
            self.assertIsNotNone(
                self.server.session_manager.get_session(
                    "alice"
                )
            )

            # Bob must not have a session
            self.assertIsNone(
                self.server.session_manager.get_session(
                    "bob"
                )
            )

        server_thread.join(timeout=3)

        # Alice's session is removed after disconnect
        self.assertIsNone(
            self.server.session_manager.get_session(
                "alice"
            )
        )

    def test_session_cleanup_on_connection_reset(self):
        # Find an available local port
        with socket.socket() as temp_socket:
            temp_socket.bind(("127.0.0.1", 0))
            port = temp_socket.getsockname()[1]

        self.server.port = port

        server_thread = threading.Thread(
            target=self.server.start,
            daemon=True
        )
        server_thread.start()

        time.sleep(0.2)

        client = socket.create_connection(
            ("127.0.0.1", port),
            timeout=3
        )

        try:
            client.settimeout(3)

            # Handshake
            client.sendall(b"HELLO\n")
            self.assertEqual(
                client.recv(1024),
                b"WELCOME\n"
            )

            # Register
            client.sendall(
                b'{"action":"REGISTER",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )
            self.assertIn(
                b"REGISTER_SUCCESS",
                client.recv(1024)
            )

            # Login
            client.sendall(
                b'{"action":"LOGIN",'
                b'"username":"alice",'
                b'"password":"pass123"}\n'
            )
            self.assertIn(
                b"LOGIN_SUCCESS",
                client.recv(1024)
            )

            # Verify active session
            self.assertIsNotNone(
                self.server.session_manager.get_session(
                    "alice"
                )
            )

            # Force TCP connection reset (RST)
            import struct

            client.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_LINGER,
                struct.pack("ii", 1, 0)
            )

        finally:
            client.close()


        # Wait for the server to clean up the disconnected session.
        deadline = time.monotonic() + 5

        while time.monotonic() < deadline:
            if (
                self.server.session_manager.get_session("alice")
                is None
            ):
                break

            time.sleep(0.01)

        # Verify session cleanup before stopping the server.
        try:
            self.assertIsNone(
                self.server.session_manager.get_session("alice"),
                "Session was not removed after connection reset"
            )
        finally:
            # A client disconnect must not automatically stop
            # a multi-client server.
            self.server.stop()
            server_thread.join(timeout=10)

        self.assertFalse(
            server_thread.is_alive(),
            "Server thread did not stop after stop()"
        )





if __name__ == "__main__":
    unittest.main()
