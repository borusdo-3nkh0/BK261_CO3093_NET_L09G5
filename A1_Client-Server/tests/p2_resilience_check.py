"""Run IT07 JSON recovery and IT10 abrupt reconnect against an existing P2."""

import argparse
import hashlib
import json
import os
import platform
import secrets
import select
import socket
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

WAIT = 10
OBSERVE = 10
RECONNECT = 15


def check(condition, description):
    if not condition:
        raise AssertionError(description)


class Run:
    def __init__(self, port):
        self.port = port
        self.id = "resilience-" + uuid.uuid4().hex[:12]
        self.started = time.monotonic()
        self.trace = []
        self.peers = []
        self.case = "preflight"
        self.inflight = None
        self.inflight_received = {}
        self.password = secrets.token_urlsafe(24)

    def log(self, **data):
        self.trace.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "elapsedMs": round((time.monotonic() - self.started) * 1000, 3),
                "case": self.case,
                **data,
            }
        )

    def connect(self, label, username=None):
        peer = Peer(self, label, username)
        self.peers.append(peer)
        peer.send_raw(b"HELLO\n")
        check(peer.read() == "WELCOME", "Handshake must return WELCOME")
        return peer

    def clients(self):
        peers = []
        for label in ("A", "B", "C"):
            name = f"{self.id}-{self.case.lower()}-{label.lower()}"
            peer = self.connect(label, name)
            peer.send(
                {"action": "REGISTER", "username": name, "password": self.password}
            )
            peer.status("REGISTER_SUCCESS")
            peer.send({"action": "LOGIN", "username": name, "password": self.password})
            peer.status("LOGIN_SUCCESS")
            peers.append(peer)
        return peers

    def observe(self, peers):
        deadline = time.monotonic() + OBSERVE
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ready = [peer for peer in peers if b"\n" in peer.buffer]
            if not ready:
                sockets, _, _ = select.select(
                    [peer.sock for peer in peers], [], [], remaining
                )
                ready = [peer for peer in peers if peer.sock in sockets]
            for peer in ready:
                # No packet other than the uncertain B request is expected here.
                packet = peer.read(deadline, allow_silence=True)
                check(packet is None, "Unexpected extra delivery during observation")
        self.log(
            observedPeers=[peer.label for peer in peers], quietWindowSeconds=OBSERVE
        )

    def close_all(self):
        for peer in self.peers:
            if peer.sock.fileno() >= 0:
                peer.sock.close()


class Peer:
    def __init__(self, run, label, username):
        self.run, self.label, self.username = run, label, username
        self.sock = socket.create_connection(("127.0.0.1", run.port), timeout=WAIT)
        self.buffer = b""
        self.local_port = self.sock.getsockname()[1]
        self.server_pid = None
        if os.name == "nt":
            listing = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"], text=True
            )
            for line in listing.splitlines():
                parts = line.split()
                if len(parts) == 5 and parts[1:4] == [
                    f"127.0.0.1:{run.port}",
                    f"127.0.0.1:{self.local_port}",
                    "ESTABLISHED",
                ]:
                    self.server_pid = int(parts[4])
                    break
        run.log(
            client=label,
            event="connected",
            username=username,
            localPort=self.local_port,
            serverPid=self.server_pid,
        )

    def send_raw(self, frame):
        self.sock.sendall(frame)
        self.run.log(
            client=self.label, sentUtf8=frame.decode("utf-8"), byteLength=len(frame)
        )

    def send(self, packet):
        self.sock.sendall((json.dumps(packet, ensure_ascii=False) + "\n").encode())
        safe = {
            key: "<omitted>" if key == "password" else value
            for key, value in packet.items()
        }
        self.run.log(client=self.label, sent=safe)

    def read(self, deadline=None, allow_silence=False):
        deadline = deadline or time.monotonic() + WAIT
        while True:
            while b"\n" not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if allow_silence:
                        return None
                    raise TimeoutError("TCP response deadline exceeded")
                self.sock.settimeout(remaining)
                try:
                    data = self.sock.recv(4096)
                except TimeoutError:
                    if allow_silence:
                        return None
                    raise
                if not data:
                    raise ConnectionError("Unexpected TCP EOF")
                self.buffer += data
                check(len(self.buffer) < 65536, "Unexpected oversized TCP response")
            raw, self.buffer = self.buffer.split(b"\n", 1)
            packet = "WELCOME" if raw == b"WELCOME" else json.loads(raw)
            if (
                isinstance(packet, dict)
                and "sender" in packet
                and not packet["sender"].startswith(self.run.id)
            ):
                self.run.log(client=self.label, event="unrelated traffic omitted")
                if allow_silence:
                    return None
                continue
            self.run.log(client=self.label, received=packet)
            if (
                self.run.inflight is not None
                and isinstance(packet, dict)
                and packet.get("message") == self.run.inflight
            ):
                count = self.run.inflight_received.get(self.label, 0) + 1
                self.run.inflight_received[self.label] = count
                check(count == 1, "B in-flight request was duplicated")
                if allow_silence:
                    return None
                continue
            return packet

    def status(self, expected):
        packet = self.read()
        check(
            isinstance(packet, dict) and packet.get("status") == expected,
            f"Expected status {expected}",
        )

    def unicast(self, recipient, text):
        self.send(
            {"action": "UNICAST", "recipient": recipient.username, "message": text}
        )
        self.status("UNICAST_SUCCESS")
        check(
            recipient.read()
            == {
                "type": "UNICAST",
                "sender": self.username,
                "recipient": recipient.username,
                "message": text,
            },
            "Incorrect private delivery",
        )


def it07(run):
    a, b, c = run.clients()
    old_port = a.local_port
    malformed = b'{"action":"BROADCAST","message":}\n'
    a.send_raw(malformed)
    a.status("INVALID_REQUEST")
    text = run.id + "/IT07/valid-after-json"
    a.send({"action": "BROADCAST", "message": text})
    a.status("BROADCAST_SUCCESS")
    for target in (b, c):
        check(
            target.read()
            == {"type": "BROADCAST", "sender": a.username, "message": text},
            "Recovery broadcast was not delivered correctly",
        )
    canary = run.id + "/IT07/C-canary"
    c.send({"action": "BROADCAST", "message": canary})
    c.status("BROADCAST_SUCCESS")
    for target in (a, b):
        check(
            target.read()
            == {"type": "BROADCAST", "sender": c.username, "message": canary},
            "Server recovery canary failed",
        )
    check(a.sock.getsockname()[1] == old_port, "Original A socket must remain usable")
    run.observe([a, b, c])
    return {
        "verdict": "Đạt",
        "branch": "malformed JSON followed by valid requests",
        "response": "INVALID_REQUEST",
        "sameSocketUsable": True,
        "aLocalPort": old_port,
        "serverPids": [p.server_pid for p in (a, b, c)],
        "recoveryDeliveries": 4,
        "quietSeconds": OBSERVE,
        "extraDeliveries": 0,
    }


def it10(run):
    a, b, c = run.clients()
    a.unicast(c, run.id + "/IT10/baseline")
    old_port, old_pid = b.local_port, b.server_pid
    run.inflight = run.id + "/IT10/B-before-reset-no-ACK-read"
    b.send({"action": "BROADCAST", "message": run.inflight})
    b.sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_LINGER,
        struct.pack("HH" if os.name == "nt" else "ii", 1, 0),
    )
    disconnected_at = time.monotonic()
    b.sock.close()  # Abortive close (RST), without LOGOUT/shutdown/reading ACK.
    run.log(client="B", event="abortive close requested", linger=[1, 0], ackRead=False)
    a.unicast(c, run.id + "/IT10/A-C-during")
    c.unicast(a, run.id + "/IT10/C-A-during")
    deadline = disconnected_at + RECONNECT
    attempts = 0
    while True:
        check(time.monotonic() < deadline, "B route cleanup exceeded reconnect budget")
        attempts += 1
        a.send(
            {
                "action": "UNICAST",
                "recipient": b.username,
                "message": run.id + "/IT10/cleanup-probe",
            }
        )
        packet = a.read(deadline)
        if packet.get("status") == "UNICAST_FAILED":
            break
        check(
            packet.get("status") == "UNICAST_SUCCESS",
            "Unexpected cleanup probe response",
        )
        time.sleep(0.1)
    cleanup_ms = round((time.monotonic() - disconnected_at) * 1000, 3)
    b2 = run.connect("B-reconnected", b.username)
    check(time.monotonic() < deadline, "Reconnect handshake exceeded budget")
    b2.send({"action": "LOGIN", "username": b.username, "password": run.password})
    response = b2.read(deadline)
    check(
        response.get("status") == "LOGIN_SUCCESS",
        "B cannot log in again with its original account",
    )
    reconnect_ms = round((time.monotonic() - disconnected_at) * 1000, 3)
    check(old_port != b2.local_port, "Reconnect should use a new TCP endpoint")
    b2.unicast(a, run.id + "/IT10/B-new-A")
    a.unicast(b2, run.id + "/IT10/A-new-B")
    a.unicast(c, run.id + "/IT10/A-C-after")
    c.unicast(a, run.id + "/IT10/C-A-after")
    run.observe([a, b2, c])
    return {
        "verdict": "Đạt",
        "branch": "abrupt B disconnect and fresh login, same account",
        "oldBPort": old_port,
        "newBPort": b2.local_port,
        "oldServerPid": old_pid,
        "newServerPid": b2.server_pid,
        "sameServerPid": old_pid == b2.server_pid,
        "duringCanaries": 2,
        "afterCanaries": 2,
        "newBDeliveries": 2,
        "cleanupProbeAttempts": attempts,
        "cleanupObservedMs": cleanup_ms,
        "reloginObservedMs": reconnect_ms,
        "loginResponse": response,
        "inflightBOutcome": "Chưa xác định: không đọc ACK, không tự replay",
        "inflightObservedAtPeers": run.inflight_received,
        "quietSeconds": OBSERVE,
        "extraDeliveries": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "runtime/reviews/it07-it10-2026-11-08"
    output.mkdir(parents=True, exist_ok=True)
    run = Run(args.port)
    reference = (
        Path(
            os.environ.get(
                "CONNECT_P2_ROOT", root.parent.parent / "MMT-P2/A1_Client-Server"
            )
        ).resolve()
        / "server"
    )
    report = {
        "runId": run.id,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "target": f"127.0.0.1:{args.port}",
        "python": sys.version,
        "runnerSHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "platform": platform.platform(),
        "waitSeconds": WAIT,
        "observationSeconds": OBSERVE,
        "reconnectBudgetSeconds": RECONNECT,
        "p2ReferenceSHA256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in reference.glob("*.py")
        },
        "cases": {},
    }
    try:
        try:
            probe = run.connect("preflight")
            probe.sock.close()
        except OSError:
            for case in ("IT07", "IT10"):
                report["cases"][case] = {
                    "verdict": "Chưa chạy",
                    "reason": "Endpoint/handshake unavailable; no server started or restarted",
                }
        else:
            for name, task in (("IT07", it07), ("IT10", it10)):
                run.case = name
                try:
                    report["cases"][name] = task(run)
                except (AssertionError, OSError, ValueError) as exc:
                    report["cases"][name] = {
                        "verdict": "Không đạt",
                        "error": type(exc).__name__ + ": " + str(exc),
                    }
                finally:
                    run.close_all()
                    run.log(
                        event="closed owned client sockets; existing server unchanged"
                    )
    finally:
        run.close_all()
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        report["trace"] = run.trace
        text = json.dumps(report, ensure_ascii=False, indent=2)
        check(run.password not in text, "Test password must not appear in evidence")
        for name in ("results.json", run.id + ".json"):
            (output / name).write_text(text, encoding="utf-8")
        print(
            json.dumps(
                {"runId": run.id, "cases": report["cases"]},
                ensure_ascii=False,
                indent=2,
            )
        )
    return (
        0 if all(case["verdict"] == "Đạt" for case in report["cases"].values()) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
