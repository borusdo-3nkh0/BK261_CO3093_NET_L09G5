
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


def send_auth_request(sock, action, username, password):
    request = {
        "action": action,
        "username": username,
        "password": password
    }

    message = json.dumps(request).encode("utf-8") + b"\n"
    sock.sendall(message)

    response = receive_line(sock)

    if not response:
        raise ConnectionError("Server closed the connection")

    return json.loads(response.decode("utf-8"))["status"]


def main():
    with socket.create_connection((HOST, PORT), timeout=5) as client:
        client.settimeout(5)

        # Step 1: Handshake
        client.sendall(b"HELLO\n")

        handshake = receive_line(client)
        print("Handshake:", handshake.decode().strip())

        if handshake != b"WELCOME\n":
            print("Handshake FAILED")
            return

        # Step 2: Register
        register = send_auth_request(
            client, "REGISTER", "alice", "demo123"
        )
        print("REGISTER:", register)

        # Step 3: Login with correct password
        login_success = send_auth_request(
            client, "LOGIN", "alice", "demo123"
        )
        print("LOGIN correct password:", login_success)

        # Step 4: Login with wrong password
        login_failed = send_auth_request(
            client, "LOGIN", "alice", "wrong"
        )
        print("LOGIN wrong password:", login_failed)

        # Step 5: Verify results
        if (
            register == "REGISTER_SUCCESS"
            and login_success == "LOGIN_SUCCESS"
            and login_failed == "LOGIN_FAILED"
        ):
            print("TCP Authentication Flow: PASS")
        else:
            print("TCP Authentication Flow: FAIL")


if __name__ == "__main__":
    main()
