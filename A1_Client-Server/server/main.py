import argparse
import logging
from pathlib import Path

from security.tls import server_context
from server.socket_server import SocketServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the Server Core."""

    logger.info("===================================")
    logger.info("Assignment 1 - Collaboration App")
    logger.info("P2 - Server Core")
    logger.info("===================================")

    parser = argparse.ArgumentParser(
        description="Connect TLS/AES-GCM server (no plaintext fallback)"
    )
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--udp-port", type=int, default=5001)
    parser.add_argument("--cert", type=Path, default=Path("runtime/tls/server.pem"))
    parser.add_argument("--key", type=Path, default=Path("runtime/tls/server.key"))
    args = parser.parse_args()
    server = SocketServer(
        host="127.0.0.1",
        port=args.port,
        udp_port=args.udp_port,
        tls_context=server_context(args.cert, args.key),
    )

    server.start()


if __name__ == "__main__":
    main()
