
import json
import socket


HOST = "127.0.0.1"
PORT = 5000


def receive_line(sock):
    data = bytearray()

    while True:
        chunk = sock.recv(1)

        if not chunk:
            return bytes(data)

        data.extend(chunk)

        if chunk == b"\n":
            return bytes(data)


def main():
    with socket.create_connection((HOST, PORT), timeout=5) as client:
        client.settimeout(5)

        # Step 1: Handshake
        client.sendall(b"HELLO\n")

        handshake_response = receive_line(client)
        print("Handshake:", handshake_response.decode().strip())

        if handshake_response != b"WELCOME\n":
            print("Handshake FAILED")
            return

        # Step 2: Register a test account
        request = {
            "action": "REGISTER",
            "username": "alice",
            "password": "demo123"
        }

        message = json.dumps(request).encode("utf-8") + b"\n"
        client.sendall(message)

        # Step 3: Receive authentication result
        response = receive_line(client)
        print("Authentication:", response.decode().strip())

        result = json.loads(response.decode("utf-8"))

        if result.get("status") == "REGISTER_SUCCESS":
            print("TCP Authentication Test: PASS")
        else:
            print("TCP Authentication Test: FAIL")


if __name__ == "__main__":
    main()
