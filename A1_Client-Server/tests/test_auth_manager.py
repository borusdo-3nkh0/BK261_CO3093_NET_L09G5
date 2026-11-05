
import unittest

from server.auth_manager import AuthManager


class TestAuthManager(unittest.TestCase):

    def setUp(self):
        """Create a fresh AuthManager for each test."""
        self.auth = AuthManager()

    def test_register_success(self):
        result = self.auth.register("alice", "demo123")
        self.assertTrue(result)

    def test_register_duplicate_username(self):
        self.auth.register("alice", "demo123")

        result = self.auth.register("alice", "other123")
        self.assertFalse(result)

    def test_register_empty_username(self):
        self.assertFalse(
            self.auth.register("", "demo123")
        )

    def test_register_empty_password(self):
        self.assertFalse(
            self.auth.register("alice", "")
        )

    def test_authenticate_success(self):
        self.auth.register("alice", "demo123")

        result = self.auth.authenticate("alice", "demo123")
        self.assertTrue(result)

    def test_authenticate_wrong_password(self):
        self.auth.register("alice", "demo123")

        result = self.auth.authenticate("alice", "wrong")
        self.assertFalse(result)

    def test_authenticate_unknown_user(self):
        result = self.auth.authenticate("bob", "demo123")
        self.assertFalse(result)

    def test_invalid_input_types(self):
        self.assertFalse(self.auth.register(None, "demo123"))
        self.assertFalse(self.auth.register("alice", None))
        self.assertFalse(self.auth.authenticate(None, "demo123"))
        self.assertFalse(self.auth.authenticate("alice", None))

    def test_password_not_stored_as_plaintext(self):
        self.auth.register("alice", "demo123")

        stored = self.auth.users["alice"]

        self.assertNotEqual(
            stored["password_hash"],
            b"demo123"
        )
        self.assertEqual(len(stored["salt"]), 16)
        self.assertEqual(len(stored["password_hash"]), 32)


if __name__ == "__main__":
    unittest.main()
