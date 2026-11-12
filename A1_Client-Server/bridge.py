"""Loopback HTTP client for the current P2 newline JSON TCP server."""

import argparse
import json
import secrets
import select
import socket
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from bridge_files import FileService, load_p1

WEB = Path(__file__).resolve().parent / "web"
TIMEOUT = 10
MAX_FRAME = 1024  # P2 receive_line limit, including the terminating newline.
ONLINE_INTERVAL = 5
MAX_RESPONSE = 8192
STORAGE = Path(__file__).resolve().parent / "runtime" / "files"


def encode(data):
    frame = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
    if len(frame) > MAX_FRAME:
        raise ValueError("Yêu cầu vượt giới hạn 1.024 byte của máy chủ.")
    return frame


def read_line(sock):
    data = bytearray()
    while len(data) < MAX_RESPONSE:
        part = sock.recv(1)
        if not part:
            raise ConnectionError("TCP closed")
        data.extend(part)
        if part == b"\n":
            return bytes(data)
    raise ValueError("Invalid server frame")


class Session:
    def __init__(self, session_id, file_factory=None, storage=STORAGE):
        self.session_id = session_id
        self.condition = threading.Condition(threading.RLock())
        self.events = deque(maxlen=256)
        self.sequence = 0
        self.connection_revision = 1
        self.users_revision = 0
        self.users = {}
        self.username = None
        self.sock = None
        self.connected = False
        self.pending = None
        self.message_ids = set()
        self.last_poll = time.monotonic()
        self.online_status = "loading"
        self.next_online = 0
        self.file_factory, self.storage = file_factory, storage
        self.files, self.file_thread = None, None
        self.file_requested = False

    def emit(self, kind, data):
        self.sequence += 1
        event = {
            "eventId": str(uuid.uuid4()),
            "sessionId": self.session_id,
            "type": kind,
            "data": data,
        }
        self.events.append((self.sequence, event))
        self.condition.notify_all()

    def connection(self, state, error=None):
        self.connection_revision += 1
        self.emit(
            "connection.changed",
            {
                "sessionId": self.session_id,
                "revision": self.connection_revision,
                "mode": "live",
                "state": state,
                "selfUserId": self.username,
                "error": error,
            },
        )

    def snapshot(self):
        self.users_revision += 1
        self.emit(
            "users.snapshot",
            {
                "revision": self.users_revision,
                "users": list(self.users.values()),
                "onlineStatus": self.online_status,
            },
        )

    def refresh_online(self):
        with self.condition:
            if (
                not self.connected
                or self.pending
                or time.monotonic() < self.next_online
            ):
                return False
            self.pending = ({"action": "LIST_ONLINE"}, time.monotonic() + TIMEOUT)
            self.sock.sendall(encode({"action": "LIST_ONLINE"}))
            return True

    def refresh_files(self):
        if (
            self.connected
            and self.file_factory
            and not self.file_requested
            and not self.pending
        ):
            self.file_requested = True
            self.pending = ({"action": "FILE_SESSION"}, time.monotonic() + TIMEOUT)
            self.sock.sendall(encode({"action": "FILE_SESSION"}))

    def file_publish(self, kind, data):
        with self.condition:
            if not self.connected:
                return
            if kind == "transfer.upsert" and data["senderId"] not in self.users:
                sender = data["senderId"]
                self.users[sender] = {
                    "userId": sender,
                    "displayName": sender,
                    "presence": "unknown",
                }
                self.snapshot()
            self.emit(kind, data)

    def start_files(self, ticket, relay):
        service = None
        try:
            service = FileService(
                self.username,
                self.file_factory,
                ticket,
                relay,
                self.storage,
                self.file_publish,
            )
            with self.condition:
                if not self.connected:
                    service.close_async()
                    return
                self.files = service
            service.start()
            with self.condition:
                if self.connected and not service.stopped.is_set():
                    self.emit("files.changed", {"state": "ready", "userMessage": ""})
        except Exception:
            if service:
                service.close_async()
            self.file_publish(
                "files.changed",
                {
                    "state": "unavailable",
                    "userMessage": "Chưa thể khởi động dịch vụ file.",
                },
            )

    def file_service(self):
        with self.condition:
            service = self.files
            if (
                not self.connected
                or not service
                or service.stopped.is_set()
                or not service.thread
                or not service.thread.is_alive()
            ):
                raise ValueError("Dịch vụ file chưa sẵn sàng; cần FILE_SESSION từ P2.")
            return service

    def open(self, target, username, password):
        with self.condition:
            try:
                frame = encode(
                    {"action": "LOGIN", "username": username, "password": password}
                )
                self.sock = socket.create_connection(target, timeout=TIMEOUT)
                self.sock.sendall(b"HELLO\n")
                if read_line(self.sock) != b"WELCOME\n":
                    raise ValueError("Invalid handshake")
                self.sock.sendall(frame)
                reply = json.loads(read_line(self.sock))
                if reply.get("status") != "LOGIN_SUCCESS":
                    code = reply.get("status", "LOGIN_FAILED")
                    self.end("disconnected", code, "Đăng nhập không thành công.")
                    return
                self.username = username
                self.connected = True
                self.users[username] = {
                    "userId": username,
                    "displayName": username,
                    "presence": "online",
                }
                self.connection("connected")
                self.snapshot()
                self.emit(
                    "files.changed",
                    {
                        "state": "loading" if self.file_factory else "unavailable",
                        "userMessage": "Đang chuẩn bị dịch vụ file…"
                        if self.file_factory
                        else "Dịch vụ file chưa được cấu hình.",
                    },
                )
                self.refresh_online()
                threading.Thread(target=self.receive, daemon=True).start()
            except OSError, ValueError, TypeError, AttributeError:
                self.end(
                    "disconnected",
                    "CONNECT_FAILED",
                    "Không thể kết nối hoặc đăng nhập.",
                )

    def end(self, state, code=None, message=None):
        with self.condition:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.sock.close()
                self.sock = None
            self.connected = False
            self.pending = None
            if self.files:
                self.files.close_async()
            self.online_status = "unavailable"
            self.users = {
                key: {**user, "presence": "unknown"} for key, user in self.users.items()
            }
            self.connection(
                state, {"code": code, "userMessage": message} if code else None
            )

    def send_message(self, request):
        text = request.get("text")
        conversation_id = request.get("conversationId")
        recipient = request.get("recipient")
        if (
            not isinstance(conversation_id, str)
            or not 0 < len(conversation_id) <= 128
            or (conversation_id == "global" and recipient is not None)
            or (
                conversation_id != "global"
                and (
                    not isinstance(recipient, str)
                    or not recipient.strip()
                    or recipient == self.username
                )
            )
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 4000
            or not all(
                isinstance(request.get(key), str) and 0 < len(request[key]) <= 128
                for key in ("messageId", "requestId")
            )
        ):
            raise ValueError("Tin nhắn hoặc người nhận không hợp lệ.")
        frame = encode(
            {"action": "BROADCAST", "message": text}
            if recipient is None
            else {"action": "UNICAST", "recipient": recipient, "message": text}
        )
        with self.condition:
            # Automatic refresh waits ahead of this send; no second TCP request.
            if self.pending and self.pending[0].get("action") in {
                "LIST_ONLINE",
                "FILE_SESSION",
            }:
                self.condition.wait_for(
                    lambda: (
                        not self.connected
                        or not self.pending
                        or self.pending[0].get("action")
                        not in {"LIST_ONLINE", "FILE_SESSION"}
                    ),
                    timeout=TIMEOUT + 0.5,
                )
            if (
                not self.connected
                or self.pending
                or request["messageId"] in self.message_ids
            ):
                return False
            message = {
                "messageId": request["messageId"],
                "revision": 1,
                "conversationId": conversation_id,
                "senderId": self.username,
                "recipientId": recipient,
                "text": text,
                "createdAt": datetime.now(UTC).isoformat(),
                "status": "sending",
                "error": None,
            }
            # P2 has no request IDs: one in-flight command prevents ambiguous ACKs.
            self.pending = (message, time.monotonic() + TIMEOUT)
            self.message_ids.add(request["messageId"])
            self.emit("message.upsert", message)
            try:
                self.sock.sendall(frame)
            except OSError:
                self.end("lost", "TCP_LOST", "Mất kết nối; chưa xác định kết quả gửi.")
            return True

    def packet(self, packet):
        if not self.connected:
            return  # A reply from a closed TCP session cannot restore presence.
        if not isinstance(packet, dict):
            raise ValueError("Invalid server response")
        if packet.get("type") in {"BROADCAST", "UNICAST"}:
            sender, text = packet.get("sender"), packet.get("message")
            private = packet["type"] == "UNICAST"
            if (
                not isinstance(sender, str)
                or not sender
                or not isinstance(text, str)
                or len(text) > 4000
                or sender == self.username
                or (private and packet.get("recipient") != self.username)
            ):
                raise ValueError("Invalid broadcast")
            if sender not in self.users:
                # A received message is no substitute for P2's missing presence feed.
                self.users[sender] = {
                    "userId": sender,
                    "displayName": sender,
                    "presence": "unknown",
                }
                self.snapshot()
            self.emit(
                "message.upsert",
                {
                    "messageId": str(uuid.uuid4()),
                    "revision": 1,
                    "conversationId": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            json.dumps(
                                sorted([self.username, sender]), ensure_ascii=False
                            ),
                        )
                    )
                    if private
                    else "global",
                    "senderId": sender,
                    "recipientId": self.username if private else None,
                    "text": text,
                    "createdAt": datetime.now(UTC).isoformat(),
                    "status": "sent",
                    "error": None,
                },
            )
        elif self.pending:
            message, _ = self.pending
            if message.get("action") == "FILE_SESSION":
                status = packet.get("status")
                if status == "FILE_SESSION_READY":
                    ticket, port = packet.get("ticket"), packet.get("udp_port")
                    if (
                        not isinstance(ticket, dict)
                        or ticket.get("username") != self.username
                        or not isinstance(ticket.get("key"), str)
                        or len(ticket["key"]) != 64
                        or any(c not in "0123456789abcdef" for c in ticket["key"])
                        or str(uuid.UUID(ticket.get("session_id", "")))
                        != ticket["session_id"]
                        or uuid.UUID(ticket["session_id"]).int == 0
                        or type(port) is not int
                        or not 1 <= port <= 65535
                    ):
                        raise ValueError("Invalid file ticket")
                    relay = (self.sock.getpeername()[0], port)
                    self.file_thread = threading.Thread(
                        target=self.start_files,
                        args=(ticket, relay),
                        daemon=True,
                        name="file-start",
                    )
                    self.file_thread.start()
                elif status in {
                    "INVALID_REQUEST",
                    "FILE_SERVICE_UNAVAILABLE",
                    "FILE_SESSION_FAILED",
                    "AUTH_REQUIRED",
                }:
                    self.emit(
                        "files.changed",
                        {
                            "state": "unavailable",
                            "userMessage": "Dịch vụ file chưa sẵn sàng; cần FILE_SESSION từ P2.",
                        },
                    )
                else:
                    raise ValueError("Unexpected file session response")
                self.pending = None
                return
            if message.get("action") == "LIST_ONLINE":
                status = packet.get("status")
                if status == "LIST_ONLINE_SUCCESS":
                    users = packet.get("users")
                    if (
                        not isinstance(users, list)
                        or not all(
                            isinstance(user, str) and user.strip() for user in users
                        )
                        or len(set(users)) != len(users)
                    ):
                        raise ValueError("Invalid online snapshot")
                    online = set(users) | {self.username}
                    for username in online:
                        self.users.setdefault(
                            username, {"userId": username, "displayName": username}
                        )
                    self.users = {
                        key: {
                            **user,
                            "presence": "online" if key in online else "offline",
                        }
                        for key, user in self.users.items()
                    }
                    self.online_status = "available"
                    self.next_online = time.monotonic() + ONLINE_INTERVAL
                elif status == "INVALID_REQUEST":
                    # Current P2 has no LIST_ONLINE. Do not keep probing this session.
                    self.online_status = "unavailable"
                    self.next_online = float("inf")
                else:
                    raise ValueError("Unexpected online response")
                self.pending = None
                self.snapshot()
                return
            action = "UNICAST" if message["recipientId"] is not None else "BROADCAST"
            status = packet.get("status")
            allowed = {f"{action}_SUCCESS", "INVALID_REQUEST", "AUTH_REQUIRED"}
            if action == "UNICAST":
                allowed.add("UNICAST_FAILED")
            if status not in allowed:
                raise ValueError("Unexpected response; cannot correlate ACK")
            self.pending = None
            success = status == f"{action}_SUCCESS"
            self.emit(
                "message.upsert",
                {
                    **message,
                    "revision": 2,
                    "status": "sent" if success else "failed",
                    "error": None
                    if success
                    else {
                        "code": packet["status"],
                        "userMessage": "Máy chủ từ chối gửi tin.",
                    },
                },
            )
        else:
            raise ValueError("Unexpected response; cannot correlate ACK")

    def receive(self):
        buffer = b""
        try:
            while True:
                with self.condition:
                    sock = self.sock
                    if not self.connected:
                        return
                    if self.pending and time.monotonic() > self.pending[1]:
                        raise TimeoutError("ACK deadline")
                    if time.monotonic() - self.last_poll > 90:
                        raise TimeoutError("Browser abandoned session")
                    self.refresh_files()
                    self.refresh_online()
                if not select.select([sock], [], [], 0.2)[0]:
                    continue
                part = sock.recv(4096)
                if not part:
                    raise ConnectionError("TCP closed")
                buffer += part
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if len(line) + 1 > MAX_RESPONSE:
                        raise ValueError("Server frame too large")
                    with self.condition:
                        if not self.connected:
                            return
                        self.packet(json.loads(line))
                if len(buffer) >= MAX_RESPONSE:
                    raise ValueError("Server frame too large")
        except OSError, ValueError, TypeError:
            with self.condition:
                if self.connected:
                    self.end(
                        "lost", "TCP_LOST", "Mất kết nối; chưa xác định kết quả gửi."
                    )

    def poll(self, after):
        with self.condition:
            self.last_poll = time.monotonic()
            if (
                after < 0
                or after > self.sequence
                or (self.events and after < self.events[0][0] - 1)
            ):
                raise ValueError("Luồng cập nhật bị gián đoạn; hãy đăng nhập lại.")
            if after == self.sequence and self.connected:
                self.condition.wait(timeout=10)
            return {
                "cursor": self.sequence,
                "events": [event for seq, event in self.events if seq > after],
            }


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, target, *, file_factory=None, storage=STORAGE):
        super().__init__(address, Handler)
        self.target = target
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.file_factory, self.storage = file_factory, storage

    def server_close(self):
        for session in list(self.sessions.values()):
            session.end("disconnected")
        for session in list(self.sessions.values()):
            if session.file_thread:
                session.file_thread.join()
            if session.files:
                session.files.closed.wait()
        super().server_close()


class Handler(SimpleHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except ConnectionResetError, BrokenPipeError:
            pass  # Closing a tab may reset an idle HTTP connection.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, *_args):
        pass  # Never log request bodies, credentials or session tokens.

    def local_request(self):
        host = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == host and self.headers.get("Origin") in (
            None,
            f"http://{host}",
        )

    def respond(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        token = self.headers.get("X-Connect-Session")
        with self.server.sessions_lock:
            session = self.server.sessions.get(token)
        if session is None:
            raise ValueError("Phiên đã hết hạn. Hãy đăng nhập lại.")
        return session

    def do_GET(self):
        if not self.local_request():
            self.respond({"error": "Yêu cầu không hợp lệ."}, 403)
            return
        path = urlsplit(self.path)
        if path.path.startswith("/api/files/"):
            try:
                with (
                    self.session()
                    .file_service()
                    .download(path.path.removeprefix("/api/files/")) as (stream, data)
                ):
                    self.download_started = True
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(data["totalBytes"]))
                    self.send_header(
                        "Content-Disposition",
                        "attachment; filename*=UTF-8''" + quote(data["fileName"]),
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    while chunk := stream.read(65536):
                        self.wfile.write(chunk)
            except ValueError, OSError:
                self.close_connection = True
                if not self.wfile.closed:
                    # Do not append JSON after a download has started.
                    if not getattr(self, "download_started", False):
                        self.respond(
                            {"error": "Không thể tải file của phiên này."}, 409
                        )
            return
        if path.path != "/api/events":
            if path.path.startswith("/api/"):
                self.respond({"error": "Không có thao tác này."}, 404)
            else:
                super().do_GET()
            return
        try:
            after = int(parse_qs(path.query).get("after", ["0"])[0])
            self.respond(self.session().poll(after))
        except ValueError as exc:
            self.respond({"error": str(exc)}, 409)

    def do_POST(self):
        if urlsplit(self.path).path == "/api/files/upload":
            self.upload_file()
            return
        if (
            not self.local_request()
            or self.headers.get("Content-Type") != "application/json"
        ):
            self.respond({"error": "Yêu cầu không hợp lệ."}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 20000:
                raise ValueError("Kích thước yêu cầu không hợp lệ.")
            self.connection.settimeout(TIMEOUT)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Yêu cầu phải là đối tượng JSON.")
            if self.path == "/api/connect":
                session_id = str(uuid.UUID(body.get("sessionId", "")))
                username, password = body.get("username"), body.get("password")
                if (
                    not isinstance(username, str)
                    or not username.strip()
                    or not isinstance(password, str)
                    or not password
                ):
                    raise ValueError("Nhập tên đăng nhập và mật khẩu.")
                session = Session(
                    session_id, self.server.file_factory, self.server.storage
                )
                with self.server.sessions_lock:
                    for token, old in list(self.server.sessions.items()):
                        if not old.connected and time.monotonic() - old.last_poll > 30:
                            del self.server.sessions[token]
                    if len(self.server.sessions) >= 20:
                        raise ValueError("Quá nhiều phiên cục bộ; thử lại sau.")
                    token = secrets.token_urlsafe(32)
                    self.server.sessions[token] = session
                session.open(self.server.target, username, password)
                self.respond({"token": token, **session.poll(0)})
            elif self.path == "/api/message":
                self.respond({"accepted": self.session().send_message(body)})
            elif self.path in {"/api/files/accept", "/api/files/reject"}:
                transfer_id = body.get("transferId")
                if not isinstance(transfer_id, str):
                    raise ValueError("ID file không hợp lệ.")
                accepted = (
                    self.session()
                    .file_service()
                    .decide(transfer_id, self.path.endswith("/accept"))
                )
                self.respond({"accepted": accepted})
            elif self.path == "/api/disconnect":
                session = self.session()
                cursor = session.sequence
                session.end("disconnected")
                self.respond(session.poll(cursor))
                with self.server.sessions_lock:
                    self.server.sessions.pop(
                        self.headers.get("X-Connect-Session"), None
                    )
            else:
                self.respond({"error": "Không có thao tác này."}, 404)
        except (ValueError, TypeError, AttributeError) as exc:
            # Parser errors can contain input; only our validation messages are public.
            message = (
                "Yêu cầu không hợp lệ."
                if isinstance(exc, (json.JSONDecodeError, UnicodeError))
                else str(exc)
            )
            self.respond({"error": message}, 400)
        except OSError:
            self.respond({"error": "Kết nối cục bộ bị gián đoạn."}, 503)

    def upload_file(self):
        self.close_connection = True
        if (
            not self.local_request()
            or self.headers.get("Content-Type") != "application/octet-stream"
            or self.headers.get("Transfer-Encoding") is not None
        ):
            self.respond({"error": "Yêu cầu upload không hợp lệ."}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            params = parse_qs(
                urlsplit(self.path).query,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
            )
            if any(len(value) != 1 for value in params.values()):
                raise ValueError("Metadata trùng lặp.")
            meta = {key: value[0] for key, value in params.items()}
            self.connection.settimeout(TIMEOUT)
            accepted = self.session().file_service().upload(meta, length, self.rfile)
            self.respond({"accepted": accepted})
        except ValueError, OSError, UnicodeError:
            self.respond(
                {
                    "error": "Upload bị từ chối: kiểm tra dịch vụ file, tên, dung lượng hoặc hạn mức phiên."
                },
                400,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--p2-port", type=int, default=5000)
    parser.add_argument(
        "--p1-root", type=Path, help="P1 A1_Client-Server checkout; no ticket/key files"
    )
    args = parser.parse_args()
    factory = load_p1(args.p1_root) if args.p1_root else None
    with BridgeServer(
        ("127.0.0.1", args.port), ("127.0.0.1", args.p2_port), file_factory=factory
    ) as server:
        print(f"Connect: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
