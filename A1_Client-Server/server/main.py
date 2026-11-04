
import logging

from server.socket_server import SocketServer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the Server Core."""

    logger.info("===================================")
    logger.info("Assignment 1 - Collaboration App")
    logger.info("P2 - Server Core")
    logger.info("===================================")

    server = SocketServer(
        host="127.0.0.1",
        port=5000
    )

    server.start()


if __name__ == "__main__":
    main()
