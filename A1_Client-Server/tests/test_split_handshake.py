
import socket
import time


def main():
    host = "127.0.0.1"
    port = 5000

    print("[TEST] Testing split handshake...")

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as client_socket:

            client_socket.settimeout(5)
            client_socket.connect((host, port))

            # Send HELLO in three separate parts
            parts = [b"HE", b"LL", b"O\n"]

            for part in parts:
                client_socket.sendall(part)
                print(f"[TEST] Sent: {part!r}")
                time.sleep(0.2)

            # Receive server response
            response = b""

            while not response.endswith(b"\n"):
                chunk = client_socket.recv(1024)

                if not chunk:
                    raise ConnectionError(
                        "Server disconnected during handshake"
                    )

                response += chunk

                if len(response) > 1024:
                    raise ValueError("Response too large")

            print(f"[TEST] Received: {response!r}")

            if response == b"WELCOME\n":
                print("[PASS] Split handshake handled correctly")
            else:
                print("[FAIL] Unexpected server response")

    except (OSError, ConnectionError, ValueError) as error:
        print(f"[FAIL] {error}")


if __name__ == "__main__":
    main()
