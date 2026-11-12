import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestTCPResilienceIntegration(unittest.TestCase):
    def setUp(self):
        self.server = SocketServer(
            host="127.0.0.1",
            port=0,
            max_clients=1,
            handshake_timeout=0.3,
            idle_timeout=0.5,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )
        self.server_thread.start()

        deadline = time.monotonic() + 3.0

        while self.server.server_socket is None:
            if time.monotonic() >= deadline:
                self.fail("Server did not start")
            time.sleep(0.01)

        self.port = self.server.server_socket.getsockname()[1]
        self.clients = []

    def tearDown(self):
        self.server.stop()

        for client in self.clients:
            client.close()

        self.server_thread.join(timeout=3.0)
        self.assertFalse(
            self.server_thread.is_alive(),
            "Server thread did not stop",
        )

    def connect_client(self):
        client = socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=2.0,
        )
        client.settimeout(2.0)
        self.clients.append(client)
        return client

    def wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)

        return predicate()

    def test_handshake_timeout(self):
        client = self.connect_client()

        self.assertEqual(client.recv(1), b"")

        self.assertTrue(self.wait_for(lambda: self.server.client_semaphore._value == 1))

    def test_partial_handshake_timeout(self):
        client = self.connect_client()
        client.sendall(b"HELLO")

        self.assertEqual(client.recv(1), b"")

    def test_idle_timeout_after_handshake(self):
        client = self.connect_client()
        client.sendall(b"HELLO\n")

        self.assertEqual(client.recv(8), b"WELCOME\n")
        self.assertEqual(client.recv(1), b"")

    def test_partial_request_timeout(self):
        client = self.connect_client()
        client.sendall(b"HELLO\n")

        self.assertEqual(client.recv(8), b"WELCOME\n")

        client.sendall(b'{"action":"LOGIN"')

        self.assertEqual(client.recv(1), b"")

    def test_connection_slot_released(self):
        first = self.connect_client()

        self.assertEqual(first.recv(1), b"")

        self.assertTrue(self.wait_for(lambda: self.server.client_semaphore._value == 1))

        second = self.connect_client()
        second.sendall(b"HELLO\n")

        self.assertEqual(second.recv(8), b"WELCOME\n")

    def test_abrupt_disconnect_and_reconnect(self):
        first = self.connect_client()
        first.sendall(b"HELLO\n")

        self.assertEqual(first.recv(8), b"WELCOME\n")

        first.shutdown(socket.SHUT_RDWR)
        first.close()

        self.assertTrue(self.wait_for(lambda: self.server.client_semaphore._value == 1))

        second = self.connect_client()
        second.sendall(b"HELLO\n")

        self.assertEqual(second.recv(8), b"WELCOME\n")

    def test_session_cleanup_and_relogin(self):
        import json

        username = "resilience_user"
        password = "demo123"

        first = self.connect_client()
        first.sendall(b"HELLO\n")
        self.assertEqual(first.recv(8), b"WELCOME\n")

        def send_request(client, action):
            request = {
                "action": action,
                "username": username,
                "password": password,
            }
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))

            response = bytearray()
            while not response.endswith(b"\n"):
                chunk = client.recv(1)
                if not chunk:
                    raise AssertionError("Connection closed before response")
                response.extend(chunk)

            return json.loads(response.decode("utf-8"))

        register_response = send_request(first, "REGISTER")
        self.assertEqual(
            register_response["status"],
            "REGISTER_SUCCESS",
        )

        login_response = send_request(first, "LOGIN")
        self.assertEqual(
            login_response["status"],
            "LOGIN_SUCCESS",
        )

        self.assertIsNotNone(self.server.session_manager.get_session(username))

        # Simulate an unexpected client disconnect.
        first.close()

        self.assertTrue(
            self.wait_for(
                lambda: self.server.session_manager.get_session(username) is None
            ),
            "Session was not removed after disconnect",
        )

        self.assertTrue(
            self.wait_for(lambda: self.server.client_semaphore._value == 1),
            "Connection slot was not released",
        )

        # The same user should be able to reconnect and log in.
        second = self.connect_client()
        second.sendall(b"HELLO\n")
        self.assertEqual(second.recv(8), b"WELCOME\n")

        relogin_response = send_request(second, "LOGIN")
        self.assertEqual(
            relogin_response["status"],
            "LOGIN_SUCCESS",
        )

    def test_graceful_shutdown_with_active_clients(self):
        first = self.connect_client()
        first.sendall(b"HELLO\n")
        self.assertEqual(first.recv(8), b"WELCOME\n")

        # Stop the server while a client is connected.
        self.server.stop()

        # The active connection should be closed.
        self.assertEqual(first.recv(1), b"")

        # The client worker must terminate.
        self.assertTrue(
            self.wait_for(
                lambda: all(
                    not thread.is_alive() for thread in self.server.client_threads
                )
            ),
            "Client threads are still running",
        )

        # The active connection must be removed.
        with self.server.clients_lock:
            self.assertEqual(len(self.server.client_sockets), 0)

        # The connection slot must be released.
        self.assertEqual(self.server.client_semaphore._value, 1)

    def test_message_router_cleanup_after_disconnect(self):
        import json

        username = "router_cleanup_user"
        password = "demo123"

        client = self.connect_client()
        client.sendall(b"HELLO\n")

        self.assertEqual(client.recv(8), b"WELCOME\n")

        def send_auth_request(action):
            request = {
                "action": action,
                "username": username,
                "password": password,
            }

            client.sendall((json.dumps(request) + "\n").encode("utf-8"))

            response = bytearray()

            while not response.endswith(b"\n"):
                chunk = client.recv(1)

                if not chunk:
                    self.fail("Connection closed before response")

                response.extend(chunk)

            return json.loads(response.decode("utf-8"))

        # STEP 1: Register and login.
        register_response = send_auth_request("REGISTER")
        self.assertEqual(
            register_response["status"],
            "REGISTER_SUCCESS",
        )

        login_response = send_auth_request("LOGIN")
        self.assertEqual(
            login_response["status"],
            "LOGIN_SUCCESS",
        )

        # STEP 2: Verify session and router registration.
        self.assertIsNotNone(self.server.session_manager.get_session(username))

        self.assertIsNotNone(self.server.message_router.get_client(username))

        self.assertIn(
            username,
            self.server.message_router.get_online_users(),
        )

        # STEP 3: Simulate unexpected disconnect.
        client.close()

        # STEP 4: Verify cleanup.
        self.assertTrue(
            self.wait_for(
                lambda: (
                    self.server.session_manager.get_session(username) is None
                    and self.server.message_router.get_client(username) is None
                )
            ),
            "Session or MessageRouter was not cleaned up",
        )

        self.assertNotIn(
            username,
            self.server.message_router.get_online_users(),
        )

        # STEP 5: Verify connection slot released.
        self.assertTrue(
            self.wait_for(lambda: self.server.client_semaphore._value == 1),
            "Connection slot was not released",
        )

    def test_server_accept_thread_stops(self):
        self.server.stop()

        self.server_thread.join(timeout=3.0)

        self.assertFalse(
            self.server_thread.is_alive(),
            "Server accept thread is still running",
        )

        self.assertIsNone(
            self.server.server_socket,
            "Listening socket reference was not cleared",
        )


if __name__ == "__main__":
    unittest.main()
