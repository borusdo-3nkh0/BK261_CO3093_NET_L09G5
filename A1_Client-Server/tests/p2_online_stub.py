"""Test-only TCP server for the unapproved LIST_ONLINE proposal; never P2 code."""

import argparse
import json
import socket
import socketserver
import threading


class OnlineServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, *, supports_online=True, file_relay=None):
        super().__init__(address, Client)
        self.supports_online = supports_online
        self.lock = threading.RLock()
        self.accounts = {}
        self.clients = {}
        self.file_relay, self.file_tickets = file_relay, {}

    def send(self, username, packet):
        with self.lock:
            target = self.clients.get(username)
        if target is None:
            return False
        sock, lock = target
        try:
            with lock:
                sock.sendall((json.dumps(packet, ensure_ascii=False) + "\n").encode())
            return True
        except OSError:
            return False

    def server_close(self):
        with self.lock:
            for sock, _ in self.clients.values():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        super().server_close()


class Client(socketserver.StreamRequestHandler):
    def handle(self):
        username = None
        send_lock = threading.Lock()

        def reply(status, **extra):
            with send_lock:
                self.request.sendall(
                    (json.dumps({"status": status, **extra}) + "\n").encode()
                )

        try:
            self.request.settimeout(60)
            if self.rfile.readline(1025) != b"HELLO\n":
                return
            self.request.sendall(b"WELCOME\n")
            while line := self.rfile.readline(1025):
                try:
                    request = json.loads(line)
                    if len(line) > 1024 or not isinstance(request, dict):
                        raise ValueError
                except ValueError, UnicodeError:
                    reply("INVALID_REQUEST")
                    continue
                action = request.get("action")
                name, password = request.get("username"), request.get("password")
                if action == "REGISTER":
                    with self.server.lock:
                        valid = (
                            isinstance(name, str)
                            and bool(name.strip())
                            and isinstance(password, str)
                            and bool(password)
                            and name not in self.server.accounts
                        )
                        if valid:
                            self.server.accounts[name] = password
                    reply("REGISTER_SUCCESS" if valid else "REGISTER_FAILED")
                elif action == "LOGIN":
                    with self.server.lock:
                        valid = (
                            isinstance(name, str)
                            and name in self.server.accounts
                            and self.server.accounts[name] == password
                            and name not in self.server.clients
                            and username is None
                        )
                        if valid:
                            username = name
                            self.server.clients[name] = (self.request, send_lock)
                    reply("LOGIN_SUCCESS" if valid else "LOGIN_FAILED")
                elif username is None:
                    reply("AUTH_REQUIRED")
                elif action == "LIST_ONLINE":
                    if not self.server.supports_online:
                        reply("INVALID_REQUEST")
                        continue
                    with self.server.lock:
                        users = list(self.server.clients)
                    reply("LIST_ONLINE_SUCCESS", users=users)
                elif action == "FILE_SESSION" and self.server.file_relay:
                    with self.server.lock:
                        if username not in self.server.file_tickets:
                            self.server.file_tickets[username] = (
                                self.server.file_relay.register_session(username)
                            )
                        ticket = self.server.file_tickets[username]
                    reply(
                        "FILE_SESSION_READY",
                        ticket=ticket.to_dict(),
                        udp_port=self.server.file_relay.address[1],
                    )
                elif action in {"BROADCAST", "UNICAST"}:
                    text = request.get("message")
                    if not isinstance(text, str) or not text:
                        reply("INVALID_REQUEST")
                        continue
                    packet = {"type": action, "sender": username, "message": text}
                    if action == "UNICAST":
                        recipient = request.get("recipient")
                        if not isinstance(recipient, str) or not recipient:
                            reply("INVALID_REQUEST")
                            continue
                        packet["recipient"] = recipient
                        success = self.server.send(recipient, packet)
                        reply("UNICAST_SUCCESS" if success else "UNICAST_FAILED")
                    else:
                        with self.server.lock:
                            recipients = [
                                name for name in self.server.clients if name != username
                            ]
                        for recipient in recipients:
                            self.server.send(recipient, packet)
                        reply("BROADCAST_SUCCESS")
                else:
                    reply("INVALID_REQUEST")
        except OSError:
            pass
        finally:
            if username:
                with self.server.lock:
                    if self.server.file_relay:
                        self.server.file_relay.unregister_session(username)
                        self.server.file_tickets.pop(username, None)
                    self.server.clients.pop(username, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--without-online", action="store_true")
    args = parser.parse_args()
    with OnlineServer(
        ("127.0.0.1", args.port), supports_online=not args.without_online
    ) as server:
        print(
            f"TEST STUB (draft LIST_ONLINE): 127.0.0.1:{server.server_address[1]}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
