
import socket


def main():
    host = "127.0.0.1"
    port = 5000

    print("[TEST] Testing invalid handshake...")

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as client_socket:

            client_socket.settimeout(5)
            client_socket.connect((host, port))

            # Send invalid handshake request
            client_socket.sendall(b"INVALID\n")
            print("[TEST] Sent: INVALID")

            # Read one newline-terminated response
            response = b""

            while not response.endswith(b"\n"):
                chunk = client_socket.recv(1024)

                if not chunk:
                    raise ConnectionError(
                        "Server closed connection unexpectedly"
                    )

                response += chunk

                if len(response) > 1024:
                    raise ValueError("Response is too large")

            print(f"[TEST] Received: {response!r}")

            if response == b"ERROR\n":
                print("[PASS] Invalid handshake rejected correctly")
            else:
                print("[FAIL] Unexpected server response")

    except (OSError, ConnectionError, ValueError) as error:
        print(f"[FAIL] {error}")


if __name__ == "__main__":
    main()
