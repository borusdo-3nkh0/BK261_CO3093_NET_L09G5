import json
import unittest

from server.auth_protocol_adapter import AuthProtocolAdapter


class TestAuthProtocolAdapter(unittest.TestCase):
    def test_decode_valid_request(self):
        data = b'{"action":"LOGIN","username":"alice","password":"demo123"}'

        result = AuthProtocolAdapter.decode_request(data)

        self.assertEqual(result["action"], "LOGIN")
        self.assertEqual(result["username"], "alice")
        self.assertEqual(result["password"], "demo123")

    def test_decode_invalid_json(self):
        data = b"not a json message"

        with self.assertRaises(ValueError):
            AuthProtocolAdapter.decode_request(data)

    def test_decode_missing_field(self):
        data = b'{"action":"LOGIN","username":"alice"}'

        with self.assertRaises(ValueError):
            AuthProtocolAdapter.decode_request(data)

    def test_decode_invalid_data_type(self):
        data = b'{"action":"LOGIN","username":123,"password":"demo123"}'

        with self.assertRaises(ValueError):
            AuthProtocolAdapter.decode_request(data)

    def test_decode_non_object(self):
        data = b'["LOGIN", "alice", "demo123"]'

        with self.assertRaises(ValueError):
            AuthProtocolAdapter.decode_request(data)

    def test_encode_response(self):
        result = AuthProtocolAdapter.encode_response("LOGIN_SUCCESS")

        self.assertTrue(result.endswith(b"\n"))

        decoded = json.loads(result.decode("utf-8"))
        self.assertEqual(decoded["status"], "LOGIN_SUCCESS")

    def test_encode_invalid_status(self):
        with self.assertRaises(ValueError):
            AuthProtocolAdapter.encode_response(123)


if __name__ == "__main__":
    unittest.main()
