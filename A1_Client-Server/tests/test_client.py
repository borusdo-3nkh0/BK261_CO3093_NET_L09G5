import socket


def main():
    host = "127.0.0.1"
    port = 5000

    print("[CLIENT] Starting TCP client...")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.settimeout(5)

            print(f"[CLIENT] Connecting to {host}:{port}...")
            client_socket.connect((host, port))

            print("[CLIENT] Connected successfully!")

            # Send handshake request
            client_socket.sendall(b"HELLO\n")
            print("[CLIENT] Sent: HELLO")

            # Receive handshake response
            response = b""

            while not response.endswith(b"\n"):
                chunk = client_socket.recv(1024)

                if not chunk:
                    raise ConnectionError("Server disconnected during handshake")

                response += chunk

                if len(response) > 1024:
                    raise ValueError("Handshake response is too large")

            if response == b"WELCOME\n":
                print("[CLIENT] Received: WELCOME")
                print("[CLIENT] Handshake successful!")

            else:
                print(f"[CLIENT] Unexpected response: {response!r}")

    except (OSError, ConnectionError, ValueError) as error:
        print(f"[ERROR] {error}")

    print("[CLIENT] Client stopped.")


if __name__ == "__main__":
    main()
