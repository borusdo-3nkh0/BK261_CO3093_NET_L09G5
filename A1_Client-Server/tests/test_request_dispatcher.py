import unittest

from server.request_dispatcher import RequestDispatcher


class TestRequestDispatcher(unittest.TestCase):
    # ==============================
    # AUTHENTICATION REQUESTS
    # ==============================

    def test_register_request(self):
        request = RequestDispatcher.decode_request(
            b'{"action":"REGISTER","username":"alice","password":"123"}'
        )

        self.assertEqual(request["action"], "REGISTER")
        self.assertEqual(RequestDispatcher.get_request_type(request), "AUTH")

    def test_login_request(self):
        request = RequestDispatcher.decode_request(
            b'{"action":"LOGIN","username":"alice","password":"123"}'
        )

        self.assertEqual(RequestDispatcher.get_request_type(request), "AUTH")

    # ==============================
    # MESSAGE REQUESTS
    # ==============================

    def test_unicast_request(self):
        request = RequestDispatcher.decode_request(
            b'{"action":"UNICAST","recipient":"bob","message":"Hello"}'
        )

        self.assertEqual(RequestDispatcher.get_request_type(request), "MESSAGE")

    def test_broadcast_request(self):
        request = RequestDispatcher.decode_request(
            b'{"action":"BROADCAST","message":"Hello everyone"}'
        )

        self.assertEqual(RequestDispatcher.get_request_type(request), "MESSAGE")

    # ==============================
    # JSON VALIDATION
    # ==============================

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b'{"action":')

    def test_invalid_utf8(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b"\xff\xfe")

    def test_non_bytes_request(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request('{"action":"LOGIN"}')

    def test_json_array(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b'["LOGIN"]')

    def test_json_null(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b"null")

    # ==============================
    # ACTION VALIDATION
    # ==============================

    def test_missing_action(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b'{"username":"alice"}')

    def test_invalid_action_type(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b'{"action":123}')

    def test_unsupported_action(self):
        with self.assertRaises(ValueError):
            RequestDispatcher.decode_request(b'{"action":"DELETE_ALL"}')


if __name__ == "__main__":
    unittest.main()
