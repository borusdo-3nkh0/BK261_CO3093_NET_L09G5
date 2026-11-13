import json
import threading
import unittest
from unittest.mock import Mock

from server.message_router import MessageRouter


class TestMessageRouter(unittest.TestCase):
    def setUp(self):
        self.router = MessageRouter()

    def test_register_client_success(self):
        """Register a new client successfully."""

        client_socket = Mock()

        result = self.router.register_client("alice", client_socket)

        self.assertTrue(result)
        self.assertIs(self.router.get_client("alice"), client_socket)

    def test_register_duplicate_client(self):
        """Reject duplicate usernames."""

        socket1 = Mock()
        socket2 = Mock()

        self.router.register_client("alice", socket1)

        result = self.router.register_client("alice", socket2)

        self.assertFalse(result)
        self.assertIs(self.router.get_client("alice"), socket1)

    def test_register_invalid_client(self):
        """Reject invalid registration data."""

        self.assertFalse(self.router.register_client("", Mock()))

        self.assertFalse(self.router.register_client(None, Mock()))

        self.assertFalse(self.router.register_client("alice", None))

    def test_unregister_client_success(self):
        """Remove an existing client."""

        self.router.register_client("alice", Mock())

        result = self.router.unregister_client("alice")

        self.assertTrue(result)
        self.assertIsNone(self.router.get_client("alice"))

    def test_unregister_unknown_client(self):
        """Return False when username does not exist."""

        result = self.router.unregister_client("unknown")

        self.assertFalse(result)

    def test_get_online_users(self):
        """Return all registered usernames."""

        self.router.register_client("alice", Mock())
        self.router.register_client("bob", Mock())

        online_users = self.router.get_online_users()

        self.assertCountEqual(online_users, ["alice", "bob"])

    def test_concurrent_registration(self):
        """Register multiple clients concurrently."""

        threads = []
        client_count = 20

        def register(index):
            self.router.register_client(f"user{index}", Mock())

        for i in range(client_count):
            thread = threading.Thread(target=register, args=(i,))

            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(len(self.router.get_online_users()), client_count)

    def test_unicast_success(self):
        """Send a message to an online recipient."""

        recipient_socket = Mock()
        self.router.register_client("bob", recipient_socket)

        result = self.router.send_unicast("alice", "bob", "Hello Bob!")

        self.assertTrue(result)
        recipient_socket.sendall.assert_called_once()

    def test_unicast_recipient_offline(self):
        """Reject messages to offline recipients."""

        result = self.router.send_unicast("alice", "unknown", "Hello!")

        self.assertFalse(result)

    def test_unicast_invalid_sender(self):
        """Reject invalid sender usernames."""

        recipient_socket = Mock()
        self.router.register_client("bob", recipient_socket)

        self.assertFalse(self.router.send_unicast("", "bob", "Hello"))

        self.assertFalse(self.router.send_unicast(None, "bob", "Hello"))

        recipient_socket.sendall.assert_not_called()

    def test_unicast_invalid_recipient(self):
        """Reject invalid recipient usernames."""

        self.assertFalse(self.router.send_unicast("alice", "", "Hello"))

        self.assertFalse(self.router.send_unicast("alice", None, "Hello"))

    def test_unicast_invalid_message(self):
        """Reject invalid message contents."""

        recipient_socket = Mock()
        self.router.register_client("bob", recipient_socket)

        self.assertFalse(self.router.send_unicast("alice", "bob", ""))

        self.assertFalse(self.router.send_unicast("alice", "bob", None))

        recipient_socket.sendall.assert_not_called()

    def test_unicast_socket_failure(self):
        """Handle socket errors without crashing."""

        recipient_socket = Mock()
        recipient_socket.sendall.side_effect = OSError("Connection lost")

        self.router.register_client("bob", recipient_socket)

        result = self.router.send_unicast("alice", "bob", "Hello Bob!")

        self.assertFalse(result)

    def test_unicast_json_format(self):
        """Verify JSON payload and newline delimiter."""

        recipient_socket = Mock()
        self.router.register_client("bob", recipient_socket)

        result = self.router.send_unicast("alice", "bob", "Xin chào Bob!")

        self.assertTrue(result)

        sent_data = recipient_socket.sendall.call_args.args[0]

        self.assertIsInstance(sent_data, bytes)
        self.assertTrue(sent_data.endswith(b"\n"))

        decoded_data = json.loads(sent_data.decode("utf-8"))

        self.assertEqual(
            decoded_data,
            {
                "type": "UNICAST",
                "sender": "alice",
                "recipient": "bob",
                "message": "Xin chào Bob!",
            },
        )

    def test_broadcast_success(self):
        """Send broadcast to all recipients."""

        alice = Mock()
        bob = Mock()
        charlie = Mock()
        david = Mock()

        self.router.register_client("alice", alice)
        self.router.register_client("bob", bob)
        self.router.register_client("charlie", charlie)
        self.router.register_client("david", david)

        result = self.router.send_broadcast("alice", "Hello everyone!")

        self.assertEqual(result, 3)

        bob.sendall.assert_called_once()
        charlie.sendall.assert_called_once()
        david.sendall.assert_called_once()

    def test_broadcast_excludes_sender(self):
        """Do not send a broadcast back to sender."""

        alice = Mock()
        bob = Mock()

        self.router.register_client("alice", alice)
        self.router.register_client("bob", bob)

        result = self.router.send_broadcast("alice", "Hello Bob!")

        self.assertEqual(result, 1)
        alice.sendall.assert_not_called()
        bob.sendall.assert_called_once()

    def test_broadcast_no_recipients(self):
        """Return zero when no recipients exist."""

        self.router.register_client("alice", Mock())

        result = self.router.send_broadcast("alice", "Hello!")

        self.assertEqual(result, 0)

    def test_broadcast_invalid_sender(self):
        """Reject invalid sender usernames."""

        bob = Mock()
        self.router.register_client("bob", bob)

        self.assertEqual(self.router.send_broadcast("", "Hello"), 0)

        self.assertEqual(self.router.send_broadcast(None, "Hello"), 0)

        bob.sendall.assert_not_called()

    def test_broadcast_invalid_message(self):
        """Reject invalid message contents."""

        bob = Mock()
        self.router.register_client("bob", bob)

        self.assertEqual(self.router.send_broadcast("alice", ""), 0)

        self.assertEqual(self.router.send_broadcast("alice", None), 0)

        bob.sendall.assert_not_called()

    def test_broadcast_socket_failure(self):
        """Continue sending when one socket fails."""

        bob = Mock()
        charlie = Mock()
        david = Mock()

        bob.sendall.side_effect = OSError("Connection lost")

        self.router.register_client("bob", bob)
        self.router.register_client("charlie", charlie)
        self.router.register_client("david", david)

        result = self.router.send_broadcast("alice", "Hello everyone!")

        self.assertEqual(result, 2)

        bob.sendall.assert_called_once()
        charlie.sendall.assert_called_once()
        david.sendall.assert_called_once()

    def test_broadcast_json_format(self):
        """Verify JSON format and UTF-8 encoding."""

        alice = Mock()
        bob = Mock()

        self.router.register_client("alice", alice)
        self.router.register_client("bob", bob)

        result = self.router.send_broadcast("alice", "Xin chào mọi người!")

        self.assertEqual(result, 1)

        sent_data = bob.sendall.call_args.args[0]

        self.assertIsInstance(sent_data, bytes)
        self.assertTrue(sent_data.endswith(b"\n"))

        decoded_data = json.loads(sent_data.decode("utf-8"))

        self.assertEqual(
            decoded_data,
            {"type": "BROADCAST", "sender": "alice", "message": "Xin chào mọi người!"},
        )

        alice.sendall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
