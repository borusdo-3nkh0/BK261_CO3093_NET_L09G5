import json
import logging
import socket
import threading
import time

from p1.relay import FileRelay
from server.auth_manager import AuthManager
from server.auth_protocol_adapter import AuthProtocolAdapter
from server.client_handler import ClientHandler
from server.message_router import MessageRouter
from server.request_dispatcher import RequestDispatcher
from server.session_manager import SessionManager

logger = logging.getLogger(__name__)


def receive_line(client_socket, max_length=1024, timeout=None):
    """Receive one newline-terminated TCP message within a deadline."""

    if timeout is not None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout < float("inf")
        ):
            raise ValueError("timeout must be a positive finite number")

        deadline = time.monotonic() + timeout
    else:
        deadline = None

    data = bytearray()

    while True:
        if deadline is not None:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise socket.timeout("Receive deadline exceeded")

            client_socket.settimeout(remaining)

        chunk = client_socket.recv(1)

        if not chunk:
            return None

        data.extend(chunk)

        if len(data) > max_length:
            raise ValueError("Message too large")

        if chunk == b"\n":
            return bytes(data)


class SocketServer:
    """Multi-client TCP server with authentication and sessions."""

    def __init__(
        self,
        host="127.0.0.1",
        port=5000,
        max_clients=20,
        handshake_timeout=5.0,
        idle_timeout=60.0,
        udp_host="127.0.0.1",
        udp_port=5001,
    ):
        self.host = host
        self.port = port
        for name, value in (
            ("handshake_timeout", handshake_timeout),
            ("idle_timeout", idle_timeout),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < value < float("inf")
            ):
                raise ValueError(f"{name} must be a positive finite number")

        self.handshake_timeout = float(handshake_timeout)
        self.idle_timeout = float(idle_timeout)

        if (
            not isinstance(max_clients, int)
            or isinstance(max_clients, bool)
            or max_clients < 1
        ):
            raise ValueError("max_clients must be a positive integer")

        self.max_clients = max_clients
        self.client_semaphore = threading.BoundedSemaphore(value=max_clients)
        self.server_socket = None

        # Authentication components
        self.auth_manager = AuthManager()
        self.client_handler = ClientHandler(self.auth_manager)
        self.session_manager = SessionManager()
        self.message_router = MessageRouter()
        # P1 UDP file transfer relay.
        # The UDP socket will be opened when start() is called.
        self.file_relay = FileRelay(
            host=udp_host,
            port=udp_port,
            max_sessions=max_clients,
        )

        # Multi-client components
        self.client_threads = []
        self.client_sockets = set()

        # Synchronization
        self.clients_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.shutdown_complete = threading.Event()

    def process_auth_data(self, data: bytes) -> bytes:
        """Process an authentication request."""

        try:
            request = AuthProtocolAdapter.decode_request(data)

            status = self.client_handler.process_auth_request(
                request["action"], request["username"], request["password"]
            )

        except ValueError:
            logger.warning("Invalid authentication request")
            status = "INVALID_REQUEST"

        return AuthProtocolAdapter.encode_response(status)

    def send_response(self, client_socket, active_username, data):
        """Send a response using the client's shared send lock."""

        if active_username is not None:
            return self.message_router.send_to_client(active_username, data)

        # Before LOGIN, no other thread can route messages
        # to this socket through MessageRouter.
        try:
            client_socket.sendall(data)
            return True
        except OSError:
            return False

    def handle_client(self, client_socket, client_address):
        """Handle handshake, authentication, and request classification."""

        active_username = None
        file_ticket = None

        try:
            with client_socket:
                logger.info("Client connected: %s", client_address)

                client_socket.settimeout(self.handshake_timeout)

                # STEP 1: HANDSHAKE
                try:
                    data = receive_line(client_socket, timeout=self.handshake_timeout)

                except ValueError:
                    logger.warning("Handshake message too large")
                    client_socket.sendall(b"ERROR\n")
                    return

                except socket.timeout:
                    logger.warning("Client handshake timeout")
                    return

                if data is None:
                    logger.warning("Client disconnected during handshake")
                    return

                if data != b"HELLO\n":
                    logger.warning("Invalid handshake request")
                    client_socket.sendall(b"ERROR\n")
                    return

                logger.info("Handshake request received")
                client_socket.sendall(b"WELCOME\n")
                logger.info("Handshake completed successfully")
                # Switch from handshake timeout to idle timeout.
                client_socket.settimeout(self.idle_timeout)

                logger.info(
                    "Client idle timeout configured: %.1f seconds", self.idle_timeout
                )

                # STEP 2: REQUEST LOOP
                while not self.stop_event.is_set():
                    try:
                        request_data = receive_line(
                            client_socket, timeout=self.idle_timeout
                        )

                    except ValueError:
                        logger.warning("Request message too large")
                        self.send_response(
                            client_socket,
                            active_username,
                            AuthProtocolAdapter.encode_response("INVALID_REQUEST"),
                        )
                        break

                    except socket.timeout:
                        logger.info("Client request timeout")
                        break

                    if request_data is None:
                        logger.info("Client disconnected")
                        break

                    try:
                        request = RequestDispatcher.decode_request(request_data)
                        request_type = RequestDispatcher.get_request_type(request)
                    except ValueError:
                        logger.warning("Invalid client request")
                        self.send_response(
                            client_socket,
                            active_username,
                            AuthProtocolAdapter.encode_response("INVALID_REQUEST"),
                        )
                        continue
                    # Handle heartbeat requests.
                    if request_type == "SYSTEM":
                        if request["action"] == "PING":
                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response("PONG"),
                            )
                            continue
                    # Handle UDP file transfer session requests.
                    if request_type == "FILE":
                        # FILE_SESSION requires successful TCP login.
                        if active_username is None:
                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response("AUTH_REQUIRED"),
                            )
                            continue

                        if request["action"] == "FILE_SESSION":
                            # Reuse the existing ticket for this TCP session.
                            if file_ticket is None:
                                try:
                                    file_ticket = self.file_relay.register_session(
                                        active_username
                                    )

                                except (ValueError, RuntimeError) as exc:
                                    logger.warning(
                                        "Failed to register UDP file session for %s: %s",
                                        active_username,
                                        type(exc).__name__,
                                    )

                                    self.send_response(
                                        client_socket,
                                        active_username,
                                        AuthProtocolAdapter.encode_response(
                                            "FILE_SESSION_FAILED"
                                        ),
                                    )
                                    continue

                            response = {
                                "status": "FILE_SESSION_READY",
                                "ticket": file_ticket.to_dict(),
                                "udp_port": self.file_relay.address[1],
                            }

                            self.send_response(
                                client_socket,
                                active_username,
                                (json.dumps(response) + "\n").encode("utf-8"),
                            )
                            continue
                    # Handle authenticated user requests.
                    if request_type == "USER":
                        if active_username is None:
                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response("AUTH_REQUIRED"),
                            )
                            continue

                        if request["action"] == "LIST_ONLINE":
                            online_users = sorted(
                                self.message_router.get_online_users()
                            )

                            response = {
                                "status": "LIST_ONLINE_SUCCESS",
                                "users": online_users,
                            }

                            self.send_response(
                                client_socket,
                                active_username,
                                (json.dumps(response) + "\n").encode("utf-8"),
                            )
                            continue

                    if request_type == "MESSAGE":
                        # Authentication is required for messaging.
                        if active_username is None:
                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response("AUTH_REQUIRED"),
                            )
                            continue

                        action = request["action"]

                        if action == "UNICAST":
                            recipient = request.get("recipient")
                            message = request.get("message")

                            # Validate message fields.
                            if (
                                not isinstance(recipient, str)
                                or not recipient
                                or not isinstance(message, str)
                                or not message
                            ):
                                status = "INVALID_REQUEST"

                            else:
                                success = self.message_router.send_unicast(
                                    sender=active_username,
                                    recipient=recipient,
                                    message=message,
                                )

                                status = (
                                    "UNICAST_SUCCESS" if success else "UNICAST_FAILED"
                                )

                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response(status),
                            )
                            continue

                        if action == "BROADCAST":
                            message = request.get("message")

                            if not isinstance(message, str) or not message:
                                status = "INVALID_REQUEST"
                            else:
                                delivered_count = self.message_router.send_broadcast(
                                    sender=active_username, message=message
                                )

                                status = "BROADCAST_SUCCESS"

                                logger.info(
                                    "Broadcast from %s delivered to %d clients",
                                    active_username,
                                    delivered_count,
                                )

                            self.send_response(
                                client_socket,
                                active_username,
                                AuthProtocolAdapter.encode_response(status),
                            )
                            continue

                    # Preserve existing authentication validation rules.
                    try:
                        request = AuthProtocolAdapter.decode_request(request_data)
                    except ValueError:
                        logger.warning("Invalid authentication request")
                        self.send_response(
                            client_socket,
                            active_username,
                            AuthProtocolAdapter.encode_response("INVALID_REQUEST"),
                        )
                        continue

                    action = request["action"]
                    username = request["username"]
                    password = request["password"]

                    # STEP 3: SESSION VALIDATION
                    if action == "LOGIN":
                        if active_username is not None:
                            status = "ALREADY_AUTHENTICATED"
                        elif self.session_manager.get_session(username) is not None:
                            status = "ALREADY_LOGGED_IN"
                        else:
                            status = self.client_handler.process_auth_request(
                                action, username, password
                            )

                            if status == "LOGIN_SUCCESS":
                                session_created = self.session_manager.add_session(
                                    username, client_address[0], client_address[1]
                                )

                                if not session_created:
                                    # Another thread may have logged in concurrently.
                                    status = "ALREADY_LOGGED_IN"
                                else:
                                    router_registered = (
                                        self.message_router.register_client(
                                            username, client_socket
                                        )
                                    )
                                    if not router_registered:
                                        self.session_manager.remove_session(username)
                                        status = "LOGIN_FAILED"
                                    else:
                                        active_username = username
                                        logger.info(
                                            "Client registered in MessageRouter: %s",
                                            username,
                                        )
                    else:
                        status = self.client_handler.process_auth_request(
                            action, username, password
                        )

                    # STEP 4: SEND RESPONSE
                    self.send_response(
                        client_socket,
                        active_username,
                        AuthProtocolAdapter.encode_response(status),
                    )

                    logger.info("Authentication request processed")

        except ConnectionResetError as exc:
            if self.stop_event.is_set():
                logger.info(
                    "Client disconnected during server shutdown: %s", client_address
                )
            else:
                logger.warning("Client connection reset: %s", exc)

        except OSError:
            if self.stop_event.is_set():
                logger.info("Client socket closed during shutdown: %s", client_address)
            else:
                logger.exception("Unexpected client socket error: %s", client_address)

        finally:
            # STEP 5: SESSION AND ROUTER CLEANUP
            if active_username is not None:
                # Revoke UDP ticket when TCP connection ends.
                if file_ticket is not None:
                    try:
                        self.file_relay.unregister_session(active_username)
                        logger.info("UDP file session revoked for %s", active_username)
                    except Exception:
                        logger.exception(
                            "Failed to revoke UDP file session for %s", active_username
                        )

                # Remove TCP routing and authentication session.
                self.message_router.unregister_client(active_username)
                removed = self.session_manager.remove_session(active_username)

                if removed:
                    logger.info(
                        "User disconnected and session removed: %s", active_username
                    )

            # Remove socket from active connections.
            with self.clients_lock:
                self.client_sockets.discard(client_socket)

            # Return one connection slot when the client exits.
            self.client_semaphore.release()

    def start(self):
        """Start TCP server and accept multiple clients."""

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                self.server_socket = server_socket

                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                server_socket.bind((self.host, self.port))
                server_socket.listen(5)

                # Start UDP relay after TCP socket is ready.
                self.file_relay.start()

                logger.info(
                    "UDP FileRelay listening on %s:%s",
                    *self.file_relay.address,
                )

                # Periodically check for shutdown.
                server_socket.settimeout(1.0)

                logger.info("Server listening on %s:%s", self.host, self.port)

                # STEP 6: ACCEPT MULTIPLE CLIENTS
                while not self.stop_event.is_set():
                    try:
                        client_socket, client_address = server_socket.accept()

                    except socket.timeout:
                        continue

                    # Register socket and start thread atomically.
                    # This prevents stop() from missing a newly
                    # accepted client during shutdown.

                    with self.clients_lock:
                        if self.stop_event.is_set():
                            client_socket.close()
                            break

                        # Reject connection if all slots are occupied.
                        if not self.client_semaphore.acquire(blocking=False):
                            logger.warning(
                                "Connection limit reached (%s)", self.max_clients
                            )
                            client_socket.close()
                            continue

                        # Remove finished client threads.
                        self.client_threads = [
                            thread
                            for thread in self.client_threads
                            if thread.is_alive()
                        ]

                        self.client_sockets.add(client_socket)

                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(client_socket, client_address),
                        )

                        self.client_threads.append(client_thread)

                        try:
                            client_thread.start()
                        except Exception:
                            self.client_threads.remove(client_thread)
                            self.client_sockets.discard(client_socket)
                            client_socket.close()
                            self.client_semaphore.release()
                            raise

                    logger.info("Client thread started: %s", client_thread.name)

        except OSError:
            if self.stop_event.is_set():
                logger.info("Server stopped during shutdown")
            else:
                logger.exception("Socket server error")

        finally:
            # Stop accepting new clients and signal shutdown.
            with self.clients_lock:
                self.stop_event.set()
                self.server_socket = None

                client_sockets = list(self.client_sockets)
                client_threads = list(self.client_threads)

            # Interrupt blocking TCP operations.
            for client_socket in client_sockets:
                try:
                    client_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            # Wait for client cleanup before closing UDP Relay.
            current_thread = threading.current_thread()

            for client_thread in client_threads:
                if client_thread is current_thread:
                    continue

                if client_thread.ident is None:
                    continue

                client_thread.join()

            # All tracked client threads have finished.
            try:
                self.file_relay.close()
            finally:
                self.shutdown_complete.set()

            logger.info("Server stopped accepting clients")

    def stop(self):
        """Request shutdown and wait for client threads."""

        logger.info("Server shutdown requested")

        # STEP 1: Atomically signal shutdown and snapshot clients.
        with self.clients_lock:
            self.stop_event.set()

            client_sockets = list(self.client_sockets)
            client_threads = list(self.client_threads)

        # STEP 2: Interrupt blocking socket operations.
        # Client threads close their own sockets.
        for client_socket in client_sockets:
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        # STEP 3: Wait for client threads to finish.
        current_thread = threading.current_thread()

        for client_thread in client_threads:
            if client_thread is current_thread:
                continue

            if client_thread.ident is None:
                continue

            client_thread.join(timeout=5)

            if client_thread.is_alive():
                logger.warning("Client thread did not stop: %s", client_thread.name)

        # STEP 4: Remove finished threads from tracking.
        with self.clients_lock:
            self.client_threads = [
                thread for thread in self.client_threads if thread.is_alive()
            ]

        if self.shutdown_complete.wait(timeout=5):
            logger.info("Server shutdown completed")
        else:
            logger.warning("Server shutdown is still in progress")
