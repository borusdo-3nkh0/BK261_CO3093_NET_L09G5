
import socket
import logging

logger = logging.getLogger(__name__)


class SocketServer:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.server_socket = None

    def start(self):
        """Start TCP server and wait for a client."""

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

                    
                    # Receive a complete newline-terminated handshake
                    data = b""

                    while not data.endswith(b"\n"):
                        chunk = client_socket.recv(1)

                        if not chunk:
                            logger.warning(
                                "Client disconnected during handshake"
                            )
                            return

                        data += chunk

                        if len(data) > 1024:
                            logger.warning("Handshake message too large")
                            client_socket.sendall(b"ERROR\n")
                            return


                    if data == b"HELLO\n":
                        logger.info("Handshake request received")

                        client_socket.sendall(b"WELCOME\n")

                        logger.info("Handshake completed successfully")

                    else:
                        logger.warning("Invalid handshake request")

                        client_socket.sendall(b"ERROR\n")


        except OSError:
            logger.exception("Socket server error")

        finally:
            self.server_socket = None
            logger.info("Server stopped")
