"""Run `python3 -m p1 --help` from A1_Client-Server."""

import argparse
import json
import os
import queue
import tempfile
import time
from pathlib import Path

from p1.client import FileClient, TransferError
from p1.relay import FileRelay
from shared.protocol import ProtocolError, SessionTicket


def _load_ticket(path):
    return SessionTicket.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_private(path, value):
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def init_demo(args):
    directory = Path(args.directory)
    directory.mkdir(parents=True, mode=0o700)
    relay = FileRelay()
    tickets = [relay.register_session(name) for name in ("alice", "bob")]
    _write_private(
        directory / "server.json", {"sessions": [t.to_dict() for t in tickets]}
    )
    for ticket in tickets:
        _write_private(directory / (ticket.username + ".json"), ticket.to_dict())
    print("Created private demo tickets in", directory)


def serve(args):
    value = json.loads(Path(args.sessions).read_text(encoding="utf-8"))
    relay = FileRelay(args.host, args.port)
    for fields in value["sessions"]:
        ticket = SessionTicket.from_dict(fields)
        relay.register_session(ticket.username, ticket=ticket)
    with relay:
        print("UDP file relay listening on %s:%s" % relay.address, flush=True)
        while True:
            time.sleep(0.5)


def receive(args):
    ticket = _load_ticket(args.ticket)
    with FileClient(
        ticket, (args.host, args.port), args.download_dir, auto_accept=True
    ) as client:
        print(
            "Ready as %s; accepting file offers into %s"
            % (ticket.username, args.download_dir),
            flush=True,
        )
        while True:
            try:
                print(
                    json.dumps(client.events.get(timeout=0.5), ensure_ascii=False),
                    flush=True,
                )
            except queue.Empty:
                pass


def send(args):
    ticket = _load_ticket(args.ticket)
    with FileClient(ticket, (args.host, args.port)) as client:
        result = client.send_file(args.file, args.recipient, timeout=args.timeout)
        print(
            json.dumps(
                dict(
                    status="verified",
                    transfer_id=str(result.transfer_id),
                    filename=result.filename,
                    size=result.size,
                    sha256=result.sha256,
                    retransmissions=result.retransmissions,
                    elapsed=result.elapsed,
                ),
                indent=2,
            )
        )


def demo(args):
    directory = (
        Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix="p1-demo-"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    source_dir = directory / "sources"
    source_dir.mkdir(exist_ok=True)
    sources = {
        "empty.bin": b"",
        "hello.txt": "Hello from P1 — xin chào!\n".encode("utf-8"),
        "binary.dat": bytes(range(256)) * 2048 + b"final partial chunk",
    }
    for name, data in sources.items():
        with (source_dir / name).open("xb") as stream:
            stream.write(data)
    with FileRelay(port=0) as relay:
        alice_ticket, bob_ticket = [
            relay.register_session(name) for name in ("alice", "bob")
        ]
        with FileClient(
            alice_ticket, relay.address, directory / "alice", auto_accept=True
        ) as alice:
            with FileClient(
                bob_ticket, relay.address, directory / "bob", auto_accept=True
            ) as bob:
                for name, data in sources.items():
                    result = alice.send_file(source_dir / name, "bob")
                    received = bob.received_files.get(timeout=5)
                    if (
                        received.path.read_bytes() != data
                        or received.sha256 != result.sha256
                    ):
                        raise TransferError("Demo verification failed")
                    print(
                        "VERIFIED %s: %s bytes; SHA-256 %s"
                        % (name, result.size, result.sha256),
                        flush=True,
                    )
                result = bob.send_file(source_dir / "hello.txt", "alice")
                received = alice.received_files.get(timeout=5)
                if received.path.read_bytes() != sources["hello.txt"]:
                    raise TransferError("Reverse transfer failed")
                print("VERIFIED reverse transfer bob -> alice", flush=True)
    print("Demo files saved in", directory.resolve())


def main():
    parser = argparse.ArgumentParser(description="P1 reliable UDP file transfer")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "demo", help="Run real UDP transfers on localhost without P2"
    )
    command.add_argument(
        "--output",
        help="New or empty output directory; otherwise use a temporary directory",
    )
    command.set_defaults(run=demo)
    command = commands.add_parser(
        "init-demo",
        help="Create local private session tickets for a multi-terminal demo",
    )
    command.add_argument("--directory", default=".local/p1-demo")
    command.set_defaults(run=init_demo)
    command = commands.add_parser(
        "serve", help="Start a relay with locally provisioned demo sessions"
    )
    command.add_argument("--sessions", required=True)
    command.add_argument("--host", default="127.0.0.1")
    command.add_argument("--port", type=int, default=5001)
    command.set_defaults(run=serve)
    for name, handler in (("send", send), ("receive", receive)):
        command = commands.add_parser(name)
        command.add_argument(
            "--ticket", required=True, help="Only this user's private session ticket"
        )
        command.add_argument("--host", default="127.0.0.1")
        command.add_argument("--port", type=int, default=5001)
        if name == "send":
            command.add_argument("--recipient", required=True)
            command.add_argument("--file", required=True)
            command.add_argument("--timeout", type=float, default=300)
        else:
            command.add_argument("--download-dir", default="downloads")
        command.set_defaults(run=handler)
    args = parser.parse_args()
    try:
        args.run(args)
    except KeyboardInterrupt:
        pass
    except (
        OSError,
        ValueError,
        TransferError,
        ProtocolError,
        KeyError,
        queue.Empty,
    ) as exc:
        parser.exit(1, "P1 error: %s\n" % exc)


if __name__ == "__main__":
    main()
