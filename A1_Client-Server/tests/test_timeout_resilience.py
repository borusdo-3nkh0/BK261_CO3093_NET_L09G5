import socket
import threading
import time
import unittest

from server.socket_server import SocketServer, receive_line


class TestReceiveLineTimeout(unittest.TestCase):
    def setUp(self):
        self.server_socket, self.client_socket = socket.socketpair()

    def tearDown(self):
        self.server_socket.close()
        self.client_socket.close()

    def test_receive_complete_line(self):
        self.client_socket.sendall(b"HELLO\n")

        result = receive_line(self.server_socket, timeout=1.0)

        self.assertEqual(result, b"HELLO\n")

    def test_receive_timeout_without_data(self):
        start = time.monotonic()

        with self.assertRaises(socket.timeout):
            receive_line(self.server_socket, timeout=0.2)

        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0)

    def test_partial_message_timeout(self):
        self.client_socket.sendall(b"HELLO")

        with self.assertRaises(socket.timeout):
            receive_line(self.server_socket, timeout=0.2)

    def test_slow_sender_cannot_extend_deadline(self):
        def slow_sender():
            for byte in b"HELLO":
                try:
                    self.client_socket.sendall(bytes([byte]))
                except OSError:
                    return

                time.sleep(0.08)

        sender_thread = threading.Thread(target=slow_sender)
        sender_thread.start()

        start = time.monotonic()

        try:
            with self.assertRaises(socket.timeout):
                receive_line(self.server_socket, timeout=0.2)

            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.5)
        finally:
            sender_thread.join(timeout=2.0)

    def test_disconnect_returns_none(self):
        self.client_socket.close()

        result = receive_line(self.server_socket, timeout=1.0)

        self.assertIsNone(result)

    def test_message_too_large(self):
        self.client_socket.sendall(b"123456789\n")

        with self.assertRaises(ValueError):
            receive_line(self.server_socket, max_length=5, timeout=1.0)

    def test_invalid_timeout(self):
        for invalid in (0, -1, True, float("inf")):
            with self.subTest(timeout=invalid):
                with self.assertRaises(ValueError):
                    receive_line(self.server_socket, timeout=invalid)


class TestSocketServerTimeoutConfiguration(unittest.TestCase):
    def test_default_configuration(self):
        server = SocketServer(host="127.0.0.1", port=0, udp_port=0)

        self.assertEqual(server.handshake_timeout, 5.0)
        self.assertEqual(server.idle_timeout, 60.0)

    def test_custom_configuration(self):
        server = SocketServer(
            host="127.0.0.1", port=0, handshake_timeout=0.5, idle_timeout=2.0
        )

        self.assertEqual(server.handshake_timeout, 0.5)
        self.assertEqual(server.idle_timeout, 2.0)

    def test_invalid_configuration(self):
        for invalid in (0, -1, True, float("inf")):
            with self.subTest(timeout=invalid):
                with self.assertRaises(ValueError):
                    SocketServer(handshake_timeout=invalid)

                with self.assertRaises(ValueError):
                    SocketServer(idle_timeout=invalid)


if __name__ == "__main__":
    unittest.main()
