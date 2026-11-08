
import json
import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestRequestDispatcherIntegration(unittest.TestCase):

    def test_unicast_requires_authentication(self):
        server = SocketServer(host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            with socket.create_connection(
                ("127.0.0.1", port), timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    request = {
                        "action": "UNICAST",
                        "recipient": "bob",
                        "message": "Hello Bob!"
                    }

                    client.sendall(
                        (json.dumps(request) + "\n").encode("utf-8")
                    )

                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        response["status"],
                        "AUTH_REQUIRED"
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_broadcast_requires_authentication(self):
        """Unauthenticated clients cannot broadcast messages."""

        server = SocketServer(host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect without logging in.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Complete handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Send BROADCAST without login.
                    request = {
                        "action": "BROADCAST",
                        "message": "Hello everyone!"
                    }

                    client.sendall(
                        (json.dumps(request) + "\n").encode("utf-8")
                    )

                    # STEP 5: Verify response.
                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        response["status"],
                        "AUTH_REQUIRED"
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_register_request_through_dispatcher(self):
        """REGISTER should work through RequestDispatcher."""

        server = SocketServer(host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect to server.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Send REGISTER request.
                    request = {
                        "action": "REGISTER",
                        "username": "register_test_user",
                        "password": "demo123"
                    }

                    client.sendall(
                        (json.dumps(request) + "\n").encode("utf-8")
                    )

                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        response["status"],
                        "REGISTER_SUCCESS"
                    )

                    # STEP 5: Verify that the connection
                    # remains usable by sending LOGIN.
                    login_request = {
                        "action": "LOGIN",
                        "username": "register_test_user",
                        "password": "demo123"
                    }

                    client.sendall(
                        (
                            json.dumps(login_request) + "\n"
                        ).encode("utf-8")
                    )

                    login_response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        login_response["status"],
                        "LOGIN_SUCCESS"
                    )

                    # STEP 6: Verify session creation.
                    self.assertIsNotNone(
                        server.session_manager.get_session(
                            "register_test_user"
                        )
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_login_request_through_dispatcher(self):
        """LOGIN should create session and router registration."""

        server = SocketServer(host="127.0.0.1", port=0)

        username = "login_test_user"
        password = "demo123"

        # STEP 1: Create account before server startup.
        self.assertTrue(
            server.auth_manager.register(username, password)
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        client = None

        try:
            # STEP 2: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 3: Connect to server.
            client = socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            )
            client.settimeout(5)

            # Read one complete TCP response.
            def read_line():
                data = bytearray()

                while not data.endswith(b"\n"):
                    chunk = client.recv(1)

                    if not chunk:
                        raise ConnectionError(
                            "Client disconnected unexpectedly"
                        )

                    data.extend(chunk)

                return bytes(data)

            # STEP 4: Handshake.
            client.sendall(b"HELLO\n")

            self.assertEqual(
                read_line(),
                b"WELCOME\n"
            )

            # STEP 5: Send LOGIN request.
            request = {
                "action": "LOGIN",
                "username": username,
                "password": password
            }

            client.sendall(
                (json.dumps(request) + "\n").encode("utf-8")
            )

            response = json.loads(
                read_line().decode("utf-8")
            )

            self.assertEqual(
                response["status"],
                "LOGIN_SUCCESS"
            )

            # STEP 6: Verify SessionManager.
            self.assertIsNotNone(
                server.session_manager.get_session(username),
                "Session was not created after LOGIN"
            )

            # STEP 7: Verify MessageRouter.
            self.assertIs(
                server.message_router.get_client(username),
                server.message_router.get_client(username)
            )

            self.assertIsNotNone(
                server.message_router.get_client(username),
                "Client was not registered in MessageRouter"
            )

            self.assertIn(
                username,
                server.message_router.get_online_users()
            )

            # STEP 8: Disconnect client.
            client.close()
            client = None

            # STEP 9: Wait for cleanup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                session_removed = (
                    server.session_manager.get_session(username)
                    is None
                )

                router_removed = (
                    server.message_router.get_client(username)
                    is None
                )

                if session_removed and router_removed:
                    break

                time.sleep(0.01)

            # STEP 10: Verify cleanup.
            self.assertIsNone(
                server.session_manager.get_session(username),
                "Session was not removed"
            )

            self.assertIsNone(
                server.message_router.get_client(username),
                "Router registration was not removed"
            )

        finally:
            if client is not None:
                client.close()

            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_unicast_to_offline_user(self):
        """Authenticated UNICAST to offline Bob returns UNICAST_FAILED."""

        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect to server.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Login.
                    login_request = {
                        "action": "LOGIN",
                        "username": "alice",
                        "password": "demo123"
                    }

                    client.sendall(
                        (
                            json.dumps(login_request) + "\n"
                        ).encode("utf-8")
                    )

                    login_response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        login_response["status"],
                        "LOGIN_SUCCESS"
                    )

                    # STEP 5: Send UNICAST request.
                    unicast_request = {
                        "action": "UNICAST",
                        "recipient": "bob",
                        "message": "Hello Bob!"
                    }

                    client.sendall(
                        (
                            json.dumps(unicast_request) + "\n"
                        ).encode("utf-8")
                    )

                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    # STEP 6: Verify response.
                    self.assertEqual(
                        response["status"],
                        "UNICAST_FAILED"
                    )

                    # STEP 7: Verify session is still active.
                    self.assertIsNotNone(
                        server.session_manager.get_session("alice")
                    )

                    self.assertIsNotNone(
                        server.message_router.get_client("alice")
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_broadcast_after_login_without_recipients(self):
        """Authenticated BROADCAST returns MESSAGE_NOT_IMPLEMENTED."""

        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect to server.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Login.
                    login_request = {
                        "action": "LOGIN",
                        "username": "alice",
                        "password": "demo123"
                    }

                    client.sendall(
                        (
                            json.dumps(login_request) + "\n"
                        ).encode("utf-8")
                    )

                    login_response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        login_response["status"],
                        "LOGIN_SUCCESS"
                    )

                    # STEP 5: Send BROADCAST request.
                    broadcast_request = {
                        "action": "BROADCAST",
                        "message": "Hello everyone!"
                    }

                    client.sendall(
                        (
                            json.dumps(broadcast_request) + "\n"
                        ).encode("utf-8")
                    )

                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    # STEP 6: Verify response.
                    self.assertEqual(
                        response["status"],
                        "BROADCAST_SUCCESS"
                    )

                    # STEP 7: Verify active session.
                    self.assertIsNotNone(
                        server.session_manager.get_session("alice"),
                        "Session was unexpectedly removed"
                    )

                    self.assertIsNotNone(
                        server.message_router.get_client("alice"),
                        "Router registration was unexpectedly removed"
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_invalid_json_request(self):
        """Server should reject malformed JSON without crashing."""

        server = SocketServer(host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect to server.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Send malformed JSON.
                    client.sendall(
                        b'{"action": "LOGIN", invalid_json}\n'
                    )

                    # STEP 5: Verify error response.
                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        response["status"],
                        "INVALID_REQUEST"
                    )

                    # STEP 6: Verify no client was authenticated.
                    self.assertEqual(
                        server.message_router.get_online_users(),
                        []
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )
    
    def test_unsupported_action_request(self):
        """Server should reject unsupported actions."""

        server = SocketServer(host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket

                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect to server.
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            ) as client:
                client.settimeout(5)

                with client.makefile("rb") as reader:
                    # STEP 3: Handshake.
                    client.sendall(b"HELLO\n")

                    self.assertEqual(
                        reader.readline(),
                        b"WELCOME\n"
                    )

                    # STEP 4: Send unsupported action.
                    request = {
                        "action": "DELETE_ALL_USERS"
                    }

                    client.sendall(
                        (json.dumps(request) + "\n").encode("utf-8")
                    )

                    # STEP 5: Verify response.
                    response = json.loads(
                        reader.readline().decode("utf-8")
                    )

                    self.assertEqual(
                        response["status"],
                        "INVALID_REQUEST"
                    )

                    # STEP 6: Verify no client authenticated.
                    self.assertEqual(
                        server.message_router.get_online_users(),
                        []
                    )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )


    def test_unicast_between_two_authenticated_clients(self):
        """Alice sends a UNICAST and Bob receives the exact payload."""
        server = SocketServer(host="127.0.0.1", port=0)
        self.assertTrue(server.auth_manager.register("alice", "demo123"))
        self.assertTrue(server.auth_manager.register("bob", "demo123"))

        server_thread = threading.Thread(target=server.start)
        server_thread.start()
        clients = []
        readers = []

        def read_json(reader):
            line = reader.readline()
            self.assertTrue(line, "Connection closed before JSON response")
            return json.loads(line.decode("utf-8"))

        def login(username, port):
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            clients.append(client)
            client.settimeout(5)
            reader = client.makefile("rb")
            readers.append(reader)
            client.sendall(b"HELLO\n")
            self.assertEqual(reader.readline(), b"WELCOME\n")
            request = {
                "action": "LOGIN",
                "username": username,
                "password": "demo123",
            }
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            self.assertEqual(read_json(reader)["status"], "LOGIN_SUCCESS")
            return client, reader

        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                sock = server.server_socket
                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass
                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            alice_socket, alice_reader = login("alice", port)
            _, bob_reader = login("bob", port)
            self.assertCountEqual(
                server.message_router.get_online_users(), ["alice", "bob"]
            )

            request = {
                "action": "UNICAST",
                "recipient": "bob",
                "message": "Hello Bob!",
            }
            alice_socket.sendall((json.dumps(request) + "\n").encode("utf-8"))
            self.assertEqual(read_json(alice_reader)["status"], "UNICAST_SUCCESS")
            self.assertEqual(
                read_json(bob_reader),
                {
                    "type": "UNICAST",
                    "sender": "alice",
                    "recipient": "bob",
                    "message": "Hello Bob!",
                },
            )
        finally:
            # Shutdown first to unblock readers, then close their file handles.
            for client in clients:
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            for reader in readers:
                reader.close()
            for client in clients:
                client.close()
            server.stop()
            server_thread.join(timeout=10)
            self.assertFalse(server_thread.is_alive(), "Server thread did not stop")

    
    def test_broadcast_between_three_authenticated_clients(self):
        """Alice broadcasts to Bob and Charlie."""

        server = SocketServer(host="127.0.0.1", port=0)

        for username in ("alice", "bob", "charlie"):
            self.assertTrue(
                server.auth_manager.register(username, "demo123")
            )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        clients = []
        readers = []

        def read_json(reader):
            line = reader.readline()
            self.assertTrue(line, "Unexpected client disconnection")
            return json.loads(line.decode("utf-8"))

        def connect_and_login(username, port):
            client = socket.create_connection(
                ("127.0.0.1", port), timeout=5
            )
            client.settimeout(5)
            clients.append(client)

            reader = client.makefile("rb")
            readers.append(reader)

            client.sendall(b"HELLO\n")
            self.assertEqual(reader.readline(), b"WELCOME\n")

            request = {
                "action": "LOGIN",
                "username": username,
                "password": "demo123"
            }
            client.sendall(
                (json.dumps(request) + "\n").encode("utf-8")
            )
            self.assertEqual(
                read_json(reader)["status"],
                "LOGIN_SUCCESS"
            )
            return client, reader

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                sock = server.server_socket
                if sock is not None:
                    try:
                        port = sock.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass
                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            alice, alice_reader = connect_and_login("alice", port)
            bob, bob_reader = connect_and_login("bob", port)
            charlie, charlie_reader = connect_and_login(
                "charlie", port
            )

            self.assertCountEqual(
                server.message_router.get_online_users(),
                ["alice", "bob", "charlie"]
            )

            request = {
                "action": "BROADCAST",
                "message": "Hello everyone!"
            }
            alice.sendall(
                (json.dumps(request) + "\n").encode("utf-8")
            )

            self.assertEqual(
                read_json(alice_reader)["status"],
                "BROADCAST_SUCCESS"
            )

            for reader in (bob_reader, charlie_reader):
                received = read_json(reader)
                self.assertEqual(received["type"], "BROADCAST")
                self.assertEqual(received["sender"], "alice")
                self.assertEqual(
                    received["message"], "Hello everyone!"
                )

        finally:
            for client in clients:
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            for reader in readers:
                reader.close()

            for client in clients:
                client.close()

            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )

if __name__ == "__main__":
    unittest.main()
