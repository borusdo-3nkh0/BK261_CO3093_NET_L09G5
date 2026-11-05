
import unittest

from server.auth_manager import AuthManager
from server.client_handler import ClientHandler


class TestClientHandler(unittest.TestCase):

    def setUp(self):
        self.auth_manager = AuthManager()
        self.handler = ClientHandler(self.auth_manager)

    def test_register_success(self):
        result = self.handler.handle_register(
            "alice", "demo123"
        )
        self.assertTrue(result)

    def test_register_duplicate(self):
        self.handler.handle_register("alice", "demo123")

        result = self.handler.handle_register(
            "alice", "other123"
        )
        self.assertFalse(result)

    def test_register_invalid_username(self):
        result = self.handler.handle_register(
            "", "demo123"
        )
        self.assertFalse(result)

    def test_login_success(self):
        self.handler.handle_register("alice", "demo123")

        result = self.handler.handle_login(
            "alice", "demo123"
        )
        self.assertTrue(result)

    def test_login_wrong_password(self):
        self.handler.handle_register("alice", "demo123")

        result = self.handler.handle_login(
            "alice", "wrong"
        )
        self.assertFalse(result)

    def test_login_unknown_user(self):
        result = self.handler.handle_login(
            "bob", "demo123"
        )
        self.assertFalse(result)

    def test_process_register_success(self):
        result = self.handler.process_auth_request(
            "REGISTER", "alice", "demo123"
        )
        self.assertEqual(result, "REGISTER_SUCCESS")

    def test_process_register_failed(self):
        self.handler.process_auth_request(
            "REGISTER", "alice", "demo123"
        )

        result = self.handler.process_auth_request(
            "REGISTER", "alice", "other123"
        )
        self.assertEqual(result, "REGISTER_FAILED")

    def test_process_login_success_and_failed(self):
        self.handler.process_auth_request(
            "REGISTER", "alice", "demo123"
        )

        success = self.handler.process_auth_request(
            "LOGIN", "alice", "demo123"
        )

        failed = self.handler.process_auth_request(
            "LOGIN", "alice", "wrong"
        )

        self.assertEqual(success, "LOGIN_SUCCESS")
        self.assertEqual(failed, "LOGIN_FAILED")

    def test_process_unknown_action(self):
        result = self.handler.process_auth_request(
            "DELETE", "alice", "demo123"
        )
        self.assertEqual(result, "UNKNOWN_ACTION")



if __name__ == "__main__":
    unittest.main()
