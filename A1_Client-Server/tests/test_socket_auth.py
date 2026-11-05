
import json
import unittest

from server.socket_server import SocketServer


class TestSocketAuth(unittest.TestCase):

    def setUp(self):
        self.server = SocketServer()

    def send_request(self, action, username, password):
        request = {
            "action": action,
            "username": username,
            "password": password
        }

        data = json.dumps(request).encode("utf-8")
        response = self.server.process_auth_data(data)

        return json.loads(response.decode("utf-8"))["status"]

    def test_register_success(self):
        result = self.send_request(
            "REGISTER", "alice", "demo123"
        )
        self.assertEqual(result, "REGISTER_SUCCESS")

    def test_register_duplicate(self):
        self.send_request("REGISTER", "alice", "demo123")

        result = self.send_request(
            "REGISTER", "alice", "demo123"
        )
        self.assertEqual(result, "REGISTER_FAILED")

    def test_login_success(self):
        self.send_request("REGISTER", "alice", "demo123")

        result = self.send_request(
            "LOGIN", "alice", "demo123"
        )
        self.assertEqual(result, "LOGIN_SUCCESS")

    def test_login_wrong_password(self):
        self.send_request("REGISTER", "alice", "demo123")

        result = self.send_request(
            "LOGIN", "alice", "wrong"
        )
        self.assertEqual(result, "LOGIN_FAILED")

    def test_invalid_json(self):
        response = self.server.process_auth_data(
            b"invalid json"
        )

        result = json.loads(response.decode("utf-8"))

        self.assertEqual(
            result["status"],
            "INVALID_REQUEST"
        )

    def test_missing_field(self):
        data = json.dumps({
            "action": "LOGIN",
            "username": "alice"
        }).encode("utf-8")

        response = self.server.process_auth_data(data)
        result = json.loads(response.decode("utf-8"))

        self.assertEqual(
            result["status"],
            "INVALID_REQUEST"
        )

    def test_unknown_action(self):
        result = self.send_request(
            "DELETE", "alice", "demo123"
        )
        self.assertEqual(result, "UNKNOWN_ACTION")


if __name__ == "__main__":
    unittest.main()
