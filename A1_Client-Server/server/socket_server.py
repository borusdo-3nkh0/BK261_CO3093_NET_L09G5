
import json
import logging
import socket
import threading

from server.auth_manager import AuthManager
from server.client_handler import ClientHandler
from server.auth_protocol_adapter import AuthProtocolAdapter
from server.session_manager import SessionManager



logger = logging.getLogger(__name__)


def receive_line(client_socket, max_length=1024):
    """Receive one newline-terminated TCP message."""

    data = bytearray()

    while True:
        chunk = client_socket.recv(1)

        if not chunk:
            return None

        data.extend(chunk)

        if len(data) > max_length:
            raise ValueError("Message too large")

        if chunk == b"\n":
            return bytes(data)


class SocketServer:
    """TCP server with handshake, authentication and sessions."""

    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_threads = []

        self.auth_manager = AuthManager()
        self.client_handler = ClientHandler(self.auth_manager)
        self.session_manager = SessionManager()

    def process_auth_data(self, data: bytes) -> bytes:
        """Process an authentication request."""

        try:
            request = AuthProtocolAdapter.decode_request(data)

            status = self.client_handler.process_auth_request(
                request["action"],
                request["username"],
                request["password"]
            )

        except ValueError:
            logger.warning("Invalid authentication request")
            status = "INVALID_REQUEST"

        return AuthProtocolAdapter.encode_response(status)

    def start(self):
        """Start TCP server and handle one client connection."""

        try:
            with socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            ) as server_socket:

                self.server_socket = server_socket

                server_socket.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_REUSEADDR,
                    1
                )

                server_socket.bind((self.host, self.port))
                server_socket.listen(5)

                logger.info(
                    "Server listening on %s:%s",
                    self.host,
                    self.port
                )

                client_socket, client_address = (
                    server_socket.accept()
                )

                with client_socket:
                    logger.info(
                        "Client connected: %s",
                        client_address
                    )

                    client_socket.settimeout(5)

                    active_username = None

                    try:
                        # -----------------------------
                        # STEP 1: TCP HANDSHAKE
                        # -----------------------------
                        try:
                            data = receive_line(client_socket)

                        except ValueError:
                            logger.warning(
                                "Handshake message too large"
                            )
                            client_socket.sendall(b"ERROR\n")
                            return

                        except socket.timeout:
                            logger.warning(
                                "Client handshake timeout"
                            )
                            return

                        if data is None:
                            logger.warning(
                                "Client disconnected during handshake"
                            )
                            return

                        if data != b"HELLO\n":
                            logger.warning(
                                "Invalid handshake request"
                            )
                            client_socket.sendall(b"ERROR\n")
                            return

                        logger.info(
                            "Handshake request received"
                        )

                        client_socket.sendall(b"WELCOME\n")

                        logger.info(
                            "Handshake completed successfully"
                        )

                        # -----------------------------
                        # STEP 2: AUTHENTICATION LOOP
                        # -----------------------------
                        while True:
                            try:
                                auth_data = receive_line(
                                    client_socket
                                )

                            except ValueError:
                                logger.warning(
                                    "Authentication message too large"
                                )

                                client_socket.sendall(
                                    AuthProtocolAdapter.encode_response(
                                        "INVALID_REQUEST"
                                    )
                                )
                                break

                            except socket.timeout:
                                logger.info(
                                    "Client authentication timeout"
                                )
                                break

                            if auth_data is None:
                                logger.info(
                                    "Client disconnected"
                                )
                                break

                            # Decode the incoming request
                            try:
                                request = (
                                    AuthProtocolAdapter.decode_request(
                                        auth_data
                                    )
                                )

                            except ValueError:
                                logger.warning(
                                    "Invalid authentication request"
                                )

                                client_socket.sendall(
                                    AuthProtocolAdapter.encode_response(
                                        "INVALID_REQUEST"
                                    )
                                )
                                continue

                            action = request["action"]
                            username = request["username"]
                            password = request["password"]

                            # -----------------------------
                            # STEP 3: SESSION VALIDATION
                            # -----------------------------
                            if action == "LOGIN":

                                # One TCP connection can have only
                                # one active authenticated user.
                                if active_username is not None:
                                    status = "ALREADY_AUTHENTICATED"

                                # Reject login if this username
                                # already has an active session.
                                elif (
                                    self.session_manager.get_session(
                                        username
                                    ) is not None
                                ):
                                    status = "ALREADY_LOGGED_IN"

                                else:
                                    status = (
                                        self.client_handler
                                        .process_auth_request(
                                            action,
                                            username,
                                            password
                                        )
                                    )

                                    # Create session only after
                                    # successful authentication.
                                    if status == "LOGIN_SUCCESS":
                                        ip, port = client_address

                                        created = (
                                            self.session_manager
                                            .add_session(
                                                username,
                                                ip,
                                                port
                                            )
                                        )

                                        if created:
                                            active_username = username

                                            logger.info(
                                                "User session created: %s",
                                                username
                                            )

                                        else:
                                            status = "ALREADY_LOGGED_IN"

                            else:
                                # Handle REGISTER or unknown actions
                                status = (
                                    self.client_handler
                                    .process_auth_request(
                                        action,
                                        username,
                                        password
                                    )
                                )

                            # -----------------------------
                            # STEP 4: SEND RESPONSE
                            # -----------------------------
                            auth_response = (
                                AuthProtocolAdapter.encode_response(
                                    status
                                )
                            )

                            client_socket.sendall(
                                auth_response
                            )

                            logger.info(
                                "Authentication request processed"
                            )

                    finally:
                        # -----------------------------
                        # STEP 5: SESSION CLEANUP
                        # -----------------------------
                        if active_username is not None:
                            removed = (
                                self.session_manager.remove_session(
                                    active_username
                                )
                            )

                            if removed:
                                logger.info(
                                    "User disconnected and "
                                    "session removed: %s",
                                    active_username
                                )

                            active_username = None


        except ConnectionResetError as exc:
            logger.warning(
                "Client connection reset: %s",
                exc
            )

        except OSError:
            logger.exception(
                "Socket server error"
            )

        finally:
            self.server_socket = None
            logger.info("Server stopped")
