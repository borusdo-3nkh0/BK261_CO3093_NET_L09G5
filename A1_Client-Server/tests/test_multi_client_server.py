
import socket
import threading
import time
import unittest

from server.socket_server import SocketServer


class TestMultiClientServer(unittest.TestCase):

    def test_multiple_clients_handshake(self):
        """Server should handle multiple clients concurrently."""

        server = SocketServer(
            host="127.0.0.1",
            port=0
        )

        server_thread = threading.Thread(
            target=server.start
        )

        server_thread.start()

        try:
            # Wait until the server has bound its port.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if (
                    server_socket is not None
                    and server_socket.fileno() != -1
                ):
                    port = server_socket.getsockname()[1]

                    if port != 0:
                        break

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            results = []
            results_lock = threading.Lock()

            def connect_client():
                with socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=5
                ) as client:
                    client.settimeout(5)
                    client.sendall(b"HELLO\n")

                    response = bytearray()

                    while not response.endswith(b"\n"):
                        chunk = client.recv(1)

                        if not chunk:
                            break

                        response.extend(chunk)

                    with results_lock:
                        results.append(bytes(response))

            clients = [
                threading.Thread(target=connect_client)
                for _ in range(5)
            ]

            for client in clients:
                client.start()

            for client in clients:
                client.join(timeout=10)

            self.assertTrue(
                all(not client.is_alive() for client in clients)
            )

            self.assertEqual(len(results), 5)
            self.assertEqual(
                results.count(b"WELCOME\n"),
                5
            )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )

    def test_twenty_concurrent_clients(self):
        """Server should handle 20 concurrent handshakes."""

        server = SocketServer(
            host="127.0.0.1",
            port=0
        )

        server_thread = threading.Thread(
            target=server.start
        )
        server_thread.start()

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if (
                    server_socket is not None
                    and server_socket.fileno() != -1
                ):
                    port = server_socket.getsockname()[1]

                    if port != 0:
                        break

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            client_count = 20
            barrier = threading.Barrier(client_count)

            results = []
            errors = []
            results_lock = threading.Lock()

            def connect_client():
                try:
                    barrier.wait(timeout=10)

                    with socket.create_connection(
                        ("127.0.0.1", port),
                        timeout=10
                    ) as client:

                        client.settimeout(10)
                        client.sendall(b"HELLO\n")

                        response = bytearray()

                        while not response.endswith(b"\n"):
                            chunk = client.recv(1)

                            if not chunk:
                                break

                            response.extend(chunk)

                        with results_lock:
                            results.append(bytes(response))

                except Exception as exc:
                    with results_lock:
                        errors.append(repr(exc))

            clients = [
                threading.Thread(target=connect_client)
                for _ in range(client_count)
            ]

            for client in clients:
                client.start()

            for client in clients:
                client.join(timeout=15)

            self.assertTrue(
                all(not client.is_alive() for client in clients),
                "Some client threads did not finish"
            )

            self.assertEqual(errors, [])
            self.assertEqual(len(results), client_count)
            self.assertEqual(
                results.count(b"WELCOME\n"),
                client_count
            )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )

    def test_concurrent_login_same_account(self):
        """Only one client can log in with the same account."""

        server = SocketServer(host="127.0.0.1", port=0)

        # Create the account before starting the server.
        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if (
                    server_socket is not None
                    and server_socket.fileno() != -1
                ):
                    port = server_socket.getsockname()[1]

                    if port != 0:
                        break

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            barrier = threading.Barrier(2)
            results = []
            errors = []
            results_lock = threading.Lock()
            release_clients = threading.Event()

            def login_client():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", port),
                        timeout=10
                    ) as client:
                        client.settimeout(10)

                        client.sendall(b"HELLO\n")

                        handshake = bytearray()

                        while not handshake.endswith(b"\n"):
                            chunk = client.recv(1)
                            if not chunk:
                                raise ConnectionError(
                                    "Disconnected during handshake"
                                )
                            handshake.extend(chunk)

                        if bytes(handshake) != b"WELCOME\n":
                            raise AssertionError(
                                "Unexpected handshake response"
                            )

                        barrier.wait(timeout=10)

                        request = (
                            b'{"action":"LOGIN",'
                            b'"username":"alice",'
                            b'"password":"demo123"}\n'
                        )

                        client.sendall(request)

                        response = bytearray()

                        while not response.endswith(b"\n"):
                            chunk = client.recv(1)
                            if not chunk:
                                raise ConnectionError(
                                    "Disconnected during login"
                                )
                            response.extend(chunk)

                        with results_lock:
                            results.append(bytes(response))

                        # Keep the successful session active
                        # until both clients have responded.
                        release_clients.wait(timeout=10)

                except Exception as exc:
                    with results_lock:
                        errors.append(repr(exc))

            clients = [
                threading.Thread(target=login_client)
                for _ in range(2)
            ]

            for client in clients:
                client.start()

            deadline = time.monotonic() + 15

            while time.monotonic() < deadline:
                with results_lock:
                    completed = len(results) + len(errors)

                if completed == 2:
                    break

                time.sleep(0.01)

            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)

            self.assertEqual(
                sum(b"LOGIN_SUCCESS" in r for r in results),
                1
            )

            self.assertEqual(
                sum(b"ALREADY_LOGGED_IN" in r for r in results),
                1
            )

            self.assertIsNotNone(
                server.session_manager.get_session("alice")
            )

        finally:
            release_clients.set()
            server.stop()

            for client in locals().get("clients", []):
                client.join(timeout=10)

            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )

    def test_session_cleanup_after_disconnect(self):
        """Session must be removed after a client disconnects."""

        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        client = None

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if server_socket is not None:
                    try:
                        port = server_socket.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 1: Connect and complete handshake.
            client = socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            )
            client.settimeout(5)

            client.sendall(b"HELLO\n")
            handshake = bytearray()

            while not handshake.endswith(b"\n"):
                chunk = client.recv(1)
                if not chunk:
                    self.fail("Disconnected during handshake")
                handshake.extend(chunk)

            self.assertEqual(bytes(handshake), b"WELCOME\n")

            # STEP 2: Log in.
            request = (
                b'{"action":"LOGIN",'
                b'"username":"alice",'
                b'"password":"demo123"}\n'
            )

            client.sendall(request)

            response = bytearray()

            while not response.endswith(b"\n"):
                chunk = client.recv(1)
                if not chunk:
                    self.fail("Disconnected during login")
                response.extend(chunk)

            self.assertIn(b"LOGIN_SUCCESS", bytes(response))

            # STEP 3: Verify active session.
            self.assertIsNotNone(
                server.session_manager.get_session("alice")
            )

            # STEP 4: Disconnect client.
            client.close()
            client = None

            # STEP 5: Wait for session cleanup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                if server.session_manager.get_session("alice") is None:
                    break
                time.sleep(0.01)

            self.assertIsNone(
                server.session_manager.get_session("alice"),
                "Session was not removed after disconnect"
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

    def test_relogin_after_disconnect(self):
        """User can log in again after previous session ends."""

        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        try:
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if server_socket is not None:
                    try:
                        port = server_socket.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            def login():
                with socket.create_connection(
                    ("127.0.0.1", port), timeout=5
                ) as client:
                    client.settimeout(5)
                    reader = client.makefile("rb")

                    try:
                        client.sendall(b"HELLO\n")
                        self.assertEqual(
                            reader.readline(),
                            b"WELCOME\n"
                        )

                        client.sendall(
                            b'{"action":"LOGIN",'
                            b'"username":"alice",'
                            b'"password":"demo123"}\n'
                        )

                        return reader.readline()
                    finally:
                        reader.close()

            # STEP 1: First login succeeds.
            first_response = login()

            self.assertIn(
                b"LOGIN_SUCCESS",
                first_response
            )

            # STEP 2: Wait until first session is removed.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                if server.session_manager.get_session("alice") is None:
                    break
                time.sleep(0.01)

            self.assertIsNone(
                server.session_manager.get_session("alice"),
                "First session was not cleaned up"
            )

            # STEP 3: Second login with same account succeeds.
            second_response = login()

            self.assertIn(
                b"LOGIN_SUCCESS",
                second_response
            )

        finally:
            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )


    def test_message_router_register_and_cleanup(self):
        """Router must register and remove authenticated clients."""

        import json

        username = "router_test_user"
        password = "router_test_password"

        # STEP 1: Initialize server and register account.
        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register(username, password)
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        client = None

        try:
            # STEP 2: Wait until server starts listening.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if server_socket is not None:
                    try:
                        port = server_socket.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 3: Connect client.
            client = socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            )
            client.settimeout(5)

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

            # STEP 5: Login.
            request = {
                "action": "LOGIN",
                "username": username,
                "password": password
            }

            client.sendall(
                (json.dumps(request) + "\n").encode("utf-8")
            )

            response = read_line()

            self.assertIn(
                b"LOGIN_SUCCESS",
                response
            )

            # STEP 6: Verify SessionManager.
            self.assertIsNotNone(
                server.session_manager.get_session(username),
                "Session was not created after login"
            )

            # STEP 7: Verify MessageRouter.
            self.assertIsNotNone(
                server.message_router.get_client(username),
                "Client socket was not registered"
            )

            self.assertIn(
                username,
                server.message_router.get_online_users()
            )

            # STEP 8: Disconnect client.
            client.close()
            client = None

            # STEP 9: Wait for complete cleanup.
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
                "Session was not removed after disconnect"
            )

            self.assertIsNone(
                server.message_router.get_client(username),
                "Router still contains disconnected client"
            )

            self.assertNotIn(
                username,
                server.message_router.get_online_users()
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

    def test_unicast_between_two_tcp_clients(self):
        """Route a unicast message to a real TCP client."""

        import json

        server = SocketServer(host="127.0.0.1", port=0)

        self.assertTrue(
            server.auth_manager.register("alice", "demo123")
        )
        self.assertTrue(
            server.auth_manager.register("bob", "demo456")
        )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        alice = None
        bob = None

        def read_line(client):
            data = bytearray()

            while not data.endswith(b"\n"):
                chunk = client.recv(1)

                if not chunk:
                    raise ConnectionError(
                        "Client disconnected unexpectedly"
                    )

                data.extend(chunk)

            return bytes(data)

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if server_socket is not None:
                    try:
                        port = server_socket.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect two clients.
            alice = socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            )
            bob = socket.create_connection(
                ("127.0.0.1", port),
                timeout=5
            )

            alice.settimeout(5)
            bob.settimeout(5)

            # STEP 3: Complete handshakes.
            for client in (alice, bob):
                client.sendall(b"HELLO\n")
                self.assertEqual(
                    read_line(client),
                    b"WELCOME\n"
                )

            # STEP 4: Authenticate Alice.
            alice.sendall(
                b'{"action":"LOGIN",'
                b'"username":"alice",'
                b'"password":"demo123"}\n'
            )

            self.assertIn(
                b"LOGIN_SUCCESS",
                read_line(alice)
            )

            # STEP 5: Authenticate Bob.
            bob.sendall(
                b'{"action":"LOGIN",'
                b'"username":"bob",'
                b'"password":"demo456"}\n'
            )

            self.assertIn(
                b"LOGIN_SUCCESS",
                read_line(bob)
            )

            # STEP 6: Verify router registrations.
            self.assertIsNotNone(
                server.message_router.get_client("alice")
            )
            self.assertIsNotNone(
                server.message_router.get_client("bob")
            )

            # STEP 7: Send unicast through the server router.
            result = server.message_router.send_unicast(
                "alice",
                "bob",
                "Hello Bob!"
            )

            self.assertTrue(result)

            # STEP 8: Bob receives the message.
            received = json.loads(
                read_line(bob).decode("utf-8")
            )

            self.assertEqual(
                received,
                {
                    "type": "UNICAST",
                    "sender": "alice",
                    "recipient": "bob",
                    "message": "Hello Bob!"
                }
            )

            # STEP 9: Alice must not receive this message.
            alice.settimeout(0.2)

            with self.assertRaises(socket.timeout):
                read_line(alice)

        finally:
            if alice is not None:
                alice.close()

            if bob is not None:
                bob.close()

            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )

    def test_broadcast_between_multiple_tcp_clients(self):
        """Broadcast to real TCP clients except sender."""

        import json

        server = SocketServer(host="127.0.0.1", port=0)

        accounts = {
            "alice": "demo123",
            "bob": "demo456",
            "charlie": "demo789",
            "david": "demo999"
        }

        for username, password in accounts.items():
            self.assertTrue(
                server.auth_manager.register(username, password)
            )

        server_thread = threading.Thread(target=server.start)
        server_thread.start()

        clients = {}

        def read_line(client):
            data = bytearray()

            while not data.endswith(b"\n"):
                chunk = client.recv(1)

                if not chunk:
                    raise ConnectionError(
                        "Client disconnected unexpectedly"
                    )

                data.extend(chunk)

            return bytes(data)

        try:
            # STEP 1: Wait for server startup.
            deadline = time.monotonic() + 5

            while time.monotonic() < deadline:
                server_socket = server.server_socket

                if server_socket is not None:
                    try:
                        port = server_socket.getsockname()[1]
                        if port != 0:
                            break
                    except OSError:
                        pass

                time.sleep(0.01)
            else:
                self.fail("Server did not start in time")

            # STEP 2: Connect and authenticate clients.
            for username, password in accounts.items():
                client = socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=5
                )
                client.settimeout(5)
                clients[username] = client

                client.sendall(b"HELLO\n")

                self.assertEqual(
                    read_line(client),
                    b"WELCOME\n"
                )

                request = {
                    "action": "LOGIN",
                    "username": username,
                    "password": password
                }

                client.sendall(
                    (
                        json.dumps(request) + "\n"
                    ).encode("utf-8")
                )

                response = json.loads(
                    read_line(client).decode("utf-8")
                )

                self.assertEqual(
                    response["status"],
                    "LOGIN_SUCCESS"
                )

            # STEP 3: Verify all clients are registered.
            self.assertCountEqual(
                server.message_router.get_online_users(),
                list(accounts.keys())
            )

            # STEP 4: Send broadcast from Alice.
            success_count = (
                server.message_router.send_broadcast(
                    "alice",
                    "Hello everyone!"
                )
            )

            self.assertEqual(success_count, 3)

            # STEP 5: Verify recipients.
            expected_message = {
                "type": "BROADCAST",
                "sender": "alice",
                "message": "Hello everyone!"
            }

            for username in ("bob", "charlie", "david"):
                received = json.loads(
                    read_line(clients[username]).decode("utf-8")
                )

                self.assertEqual(
                    received,
                    expected_message,
                    f"Incorrect broadcast received by {username}"
                )

            # STEP 6: Alice must not receive the broadcast.
            alice = clients["alice"]
            alice.settimeout(0.2)

            with self.assertRaises(socket.timeout):
                read_line(alice)

        finally:
            # STEP 7: Close all client connections.
            for client in clients.values():
                client.close()

            server.stop()
            server_thread.join(timeout=10)

            self.assertFalse(
                server_thread.is_alive(),
                "Server thread did not stop"
            )




if __name__ == "__main__":
    unittest.main()
