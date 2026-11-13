import threading
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
        self.assertFalse(self.auth.register("", "demo123"))

    def test_register_empty_password(self):
        self.assertFalse(self.auth.register("alice", ""))

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

        self.assertNotEqual(stored["password_hash"], b"demo123")
        self.assertEqual(len(stored["salt"]), 16)
        self.assertEqual(len(stored["password_hash"]), 32)

    def test_concurrent_duplicate_registration(self):
        """Only one thread can register the same username."""

        thread_count = 20
        barrier = threading.Barrier(thread_count)

        results = []
        results_lock = threading.Lock()

        def register_user():
            barrier.wait()

            success = self.auth.register("alice", "password123")

            with results_lock:
                results.append(success)

        threads = [threading.Thread(target=register_user) for _ in range(thread_count)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=30)

        self.assertTrue(all(not thread.is_alive() for thread in threads))

        self.assertEqual(len(results), thread_count)
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 19)

        self.assertEqual(len(self.auth.users), 1)

        self.assertTrue(self.auth.authenticate("alice", "password123"))


if __name__ == "__main__":
    unittest.main()
