import json
import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestListOnlineIntegration(unittest.TestCase):
    def setUp(self):
        self.server = SocketServer(
            host="127.0.0.1",
            port=0,
            udp_port=0,
            max_clients=5,
            handshake_timeout=2.0,
            idle_timeout=10.0,
        )

        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )
        self.server_thread.start()

        deadline = time.monotonic() + 3.0

        while True:
            server_socket = self.server.server_socket

            if server_socket is not None:
                try:
                    port = server_socket.getsockname()[1]

                    if port != 0:
                        self.port = port
                        break

                except OSError:
                    pass

            if time.monotonic() >= deadline:
                self.fail("Server did not start")

            time.sleep(0.01)

        self.clients = []

    def tearDown(self):
        # STEP 1: Close client connections first.
        for client in self.clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                client.close()

        # STEP 2: Request server shutdown.
        self.server.stop()

        # STEP 3: Wait for the server accept thread.
        self.server_thread.join(timeout=3.0)

        self.assertFalse(
            self.server_thread.is_alive(),
            "Server accept thread did not stop",
        )

        # STEP 4: Verify that no client worker remains alive.
        alive_threads = [
            thread.name for thread in self.server.client_threads if thread.is_alive()
        ]

        self.assertEqual(
            alive_threads,
            [],
            f"Client worker threads still running: {alive_threads}",
        )

        # STEP 5: Verify that active connections were removed.
        with self.server.clients_lock:
            self.assertEqual(
                len(self.server.client_sockets),
                0,
                "Client sockets were not cleaned up",
            )

        # STEP 6: Verify that connection slots were released.
        self.assertEqual(
            self.server.client_semaphore._value,
            self.server.max_clients,
            "Connection slots were not fully released",
        )

    def connect_client(self):
        client = socket.create_connection(
            ("127.0.0.1", self.port),
            timeout=2.0,
        )

        client.settimeout(3.0)
        self.clients.append(client)

        client.sendall(b"HELLO\n")

        self.assertEqual(
            self.read_line(client),
            b"WELCOME\n",
        )

        return client

    @staticmethod
    def read_line(client):
        data = bytearray()

        while not data.endswith(b"\n"):
            chunk = client.recv(1)

            if not chunk:
                raise AssertionError("Connection closed unexpectedly")

            data.extend(chunk)

        return bytes(data)

    def send_request(self, client, request):
        payload = (json.dumps(request) + "\n").encode("utf-8")

        client.sendall(payload)

        response = self.read_line(client)

        return json.loads(response.decode("utf-8"))

    def register_and_login(self, client, username):
        for action, expected in (
            ("REGISTER", "REGISTER_SUCCESS"),
            ("LOGIN", "LOGIN_SUCCESS"),
        ):
            response = self.send_request(
                client,
                {
                    "action": action,
                    "username": username,
                    "password": "demo123",
                },
            )

            self.assertEqual(
                response["status"],
                expected,
            )

    def wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if predicate():
                return True

            time.sleep(0.01)

        return predicate()

    def test_list_online_requires_authentication(self):
        client = self.connect_client()

        response = self.send_request(
            client,
            {"action": "LIST_ONLINE"},
        )

        self.assertEqual(
            response["status"],
            "AUTH_REQUIRED",
        )

    def test_list_online_single_user(self):
        alice = self.connect_client()

        self.register_and_login(
            alice,
            "alice",
        )

        response = self.send_request(
            alice,
            {"action": "LIST_ONLINE"},
        )

        self.assertEqual(
            response,
            {
                "status": "LIST_ONLINE_SUCCESS",
                "users": ["alice"],
            },
        )

    def test_list_online_multiple_users(self):
        alice = self.connect_client()
        bob = self.connect_client()

        self.register_and_login(
            alice,
            "alice",
        )

        self.register_and_login(
            bob,
            "bob",
        )

        response = self.send_request(
            alice,
            {"action": "LIST_ONLINE"},
        )

        self.assertEqual(
            response,
            {
                "status": "LIST_ONLINE_SUCCESS",
                "users": ["alice", "bob"],
            },
        )

    def test_list_online_after_disconnect(self):
        alice = self.connect_client()
        bob = self.connect_client()

        self.register_and_login(
            alice,
            "alice",
        )

        self.register_and_login(
            bob,
            "bob",
        )

        # Simulate Bob disconnecting.
        bob.shutdown(socket.SHUT_RDWR)
        bob.close()

        # Wait for MessageRouter cleanup.
        self.assertTrue(
            self.wait_for(lambda: self.server.message_router.get_client("bob") is None),
            "Bob was not removed from MessageRouter",
        )

        response = self.send_request(
            alice,
            {"action": "LIST_ONLINE"},
        )

        self.assertEqual(
            response,
            {
                "status": "LIST_ONLINE_SUCCESS",
                "users": ["alice"],
            },
        )


if __name__ == "__main__":
    unittest.main()
