
import json
import unittest

from server.auth_manager import AuthManager
from server.client_handler import ClientHandler
from server.auth_protocol_adapter import AuthProtocolAdapter


class TestAuthIntegration(unittest.TestCase):

    def setUp(self):
        self.auth_manager = AuthManager()
        self.client_handler = ClientHandler(self.auth_manager)

    def process_request(self, request):
        data = json.dumps(request).encode("utf-8")

        decoded = AuthProtocolAdapter.decode_request(data)

        status = self.client_handler.process_auth_request(
            decoded["action"],
            decoded["username"],
            decoded["password"]
        )

        response = AuthProtocolAdapter.encode_response(status)

        return json.loads(response.decode("utf-8"))["status"]

    def test_register_and_login(self):
        register = self.process_request({
            "action": "REGISTER",
            "username": "alice",
            "password": "demo123"
        })

        login = self.process_request({
            "action": "LOGIN",
            "username": "alice",
            "password": "demo123"
        })

        self.assertEqual(register, "REGISTER_SUCCESS")
        self.assertEqual(login, "LOGIN_SUCCESS")

    def test_login_wrong_password(self):
        self.process_request({
            "action": "REGISTER",
            "username": "alice",
            "password": "demo123"
        })

        result = self.process_request({
            "action": "LOGIN",
            "username": "alice",
            "password": "wrong"
        })

        self.assertEqual(result, "LOGIN_FAILED")

    def test_unknown_action(self):
        result = self.process_request({
            "action": "DELETE",
            "username": "alice",
            "password": "demo123"
        })

        self.assertEqual(result, "UNKNOWN_ACTION")


if __name__ == "__main__":
    unittest.main()
