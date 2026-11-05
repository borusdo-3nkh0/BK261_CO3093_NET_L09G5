
import unittest

from server.session_manager import SessionManager


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.manager = SessionManager()

    def test_add_session_success(self):
        result = self.manager.add_session(
            "alice", "127.0.0.1", 50001
        )

        self.assertTrue(result)

        session = self.manager.get_session("alice")

        self.assertEqual(session["username"], "alice")
        self.assertEqual(session["ip"], "127.0.0.1")
        self.assertEqual(session["port"], 50001)
        self.assertEqual(session["status"], "online")

    def test_add_duplicate_session(self):
        self.manager.add_session(
            "alice", "127.0.0.1", 50001
        )

        result = self.manager.add_session(
            "alice", "127.0.0.1", 50002
        )

        self.assertFalse(result)

    def test_remove_session_success(self):
        self.manager.add_session(
            "alice", "127.0.0.1", 50001
        )

        result = self.manager.remove_session("alice")

        self.assertTrue(result)
        self.assertIsNone(
            self.manager.get_session("alice")
        )

    def test_remove_nonexistent_session(self):
        result = self.manager.remove_session("unknown")

        self.assertFalse(result)

    def test_get_nonexistent_session(self):
        session = self.manager.get_session("unknown")

        self.assertIsNone(session)

    def test_invalid_username(self):
        result = self.manager.add_session(
            "", "127.0.0.1", 50001
        )

        self.assertFalse(result)

    def test_invalid_ip(self):
        result = self.manager.add_session(
            "alice", "", 50001
        )

        self.assertFalse(result)

    def test_invalid_port(self):
        self.assertFalse(
            self.manager.add_session(
                "alice", "127.0.0.1", 0
            )
        )

        self.assertFalse(
            self.manager.add_session(
                "alice", "127.0.0.1", 70000
            )
        )

    def test_session_copy(self):
        self.manager.add_session(
            "alice", "127.0.0.1", 50001
        )

        session = self.manager.get_session("alice")
        session["status"] = "offline"

        original = self.manager.get_session("alice")

        self.assertEqual(
            original["status"], "online"
        )


if __name__ == "__main__":
    unittest.main()
