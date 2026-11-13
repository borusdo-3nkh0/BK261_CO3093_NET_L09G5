import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestConnectionLimit(unittest.TestCase):
    def setUp(self):
        self.server = SocketServer(host="127.0.0.1", port=0, udp_port=0, max_clients=2)

        # Reserve a free port for the test.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as temp_socket:
            temp_socket.bind(("127.0.0.1", 0))
            self.server.port = temp_socket.getsockname()[1]

        self.server_thread = threading.Thread(target=self.server.start)
        self.server_thread.start()

        # Wait for server to accept connections.
        deadline = time.monotonic() + 3

        while self.server.server_socket is None:
            if time.monotonic() >= deadline:
                self.fail("Server did not start")
            time.sleep(0.01)

        self.clients = []

    def tearDown(self):
        for client in self.clients:
            try:
                client.close()
            except OSError:
                pass

        self.server.stop()
        self.server_thread.join(timeout=5)

    def connect_client(self):
        client = socket.create_connection(("127.0.0.1", self.server.port), timeout=3)
        client.settimeout(3)
        self.clients.append(client)
        return client

    def handshake(self, client):
        client.sendall(b"HELLO\n")
        return client.recv(1024)

    def test_reject_client_when_limit_reached(self):
        client1 = self.connect_client()
        self.assertEqual(self.handshake(client1), b"WELCOME\n")

        client2 = self.connect_client()
        self.assertEqual(self.handshake(client2), b"WELCOME\n")

        # Both connection slots are occupied.
        client3 = self.connect_client()

        try:
            response = self.handshake(client3)

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            response = b""

        self.assertEqual(
            response, b"", "Client exceeding connection limit must be rejected"
        )

    def test_slot_released_after_disconnect(self):
        client1 = self.connect_client()
        self.assertEqual(self.handshake(client1), b"WELCOME\n")

        client2 = self.connect_client()
        self.assertEqual(self.handshake(client2), b"WELCOME\n")

        # Disconnect client 1.
        client1.close()

        # Wait until the server releases the slot.
        deadline = time.monotonic() + 3

        while time.monotonic() < deadline:
            with self.server.clients_lock:
                active_count = len(self.server.client_sockets)

            if active_count == 1:
                break

            time.sleep(0.01)
        else:
            self.fail("Connection slot was not released")

        # A new client should now be accepted.
        client3 = self.connect_client()

        self.assertEqual(self.handshake(client3), b"WELCOME\n")


if __name__ == "__main__":
    unittest.main()
