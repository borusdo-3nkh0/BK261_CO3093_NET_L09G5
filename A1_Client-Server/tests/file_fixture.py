"""Owned localhost services for P3 checks; ticket fixture is never real P2."""

import argparse
import json
import sys
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p2_online_stub import OnlineServer  # noqa: E402

from bridge import BridgeServer  # noqa: E402
from bridge_files import load_p1  # noqa: E402


@contextmanager
def fixture(backend, output, *, p1_root=None, p2_root=None):
    """Stop only services created here, including on browser failure/timeout."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        factory, relay = None, None
        target = ("127.0.0.1", 1)
        if backend == "p1":
            factory = load_p1(p1_root)
            from p1.relay import FileRelay

            relay = stack.enter_context(FileRelay(port=0))
            tcp = stack.enter_context(OnlineServer(("127.0.0.1", 0), file_relay=relay))
            thread = threading.Thread(target=tcp.serve_forever)
            thread.start()
            stack.callback(thread.join, 5)
            stack.callback(tcp.shutdown)
            target = tcp.server_address
        elif backend == "p2":
            source = Path(p2_root).resolve(strict=True)
            sys.path.insert(0, str(source))
            from server.socket_server import SocketServer

            if not Path(sys.modules[SocketServer.__module__].__file__).is_relative_to(
                source
            ):
                raise ValueError("P2 import does not match configured checkout")
            tcp = SocketServer(host="127.0.0.1", port=0)
            thread = threading.Thread(target=tcp.start)
            thread.start()
            stack.callback(thread.join, 5)
            stack.callback(tcp.stop)
            deadline = time.monotonic() + 10
            while tcp.server_socket is None or not tcp.server_socket.getsockname()[1]:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise TimeoutError("P2 startup timed out")
                time.sleep(0.02)
            target = tcp.server_socket.getsockname()
        elif backend != "ui":
            raise ValueError("Unknown fixture backend")
        http = stack.enter_context(
            BridgeServer(
                ("127.0.0.1", 0),
                target,
                file_factory=factory,
                storage=output / "storage",
            )
        )
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        stack.callback(thread.join, 5)
        stack.callback(http.shutdown)
        metadata = dict(
            backend=backend,
            http=http.server_port,
            tcp=target[1],
            udp=relay.address[1] if relay else None,
            source={
                "ui": "UI/demo only; no backend",
                "p1": "P1 UDP + test auth/ticket fixture; NOT P2",
                "p2": "real P2; no FILE_SESSION",
            }[backend],
        )
        (output / "fixture.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        yield metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/p3/fixtures")
    args = parser.parse_args()
    output = args.output / ("fixture-" + uuid.uuid4().hex)
    with fixture("p1", output, p1_root=args.p1_root) as config:
        print(json.dumps(dict(config, config=str(output / "fixture.json"))), flush=True)
        print(
            "Test auth/ticket fixture, real P1 UDP. Type stop or Ctrl+C to close.",
            flush=True,
        )
        try:
            input()
        except KeyboardInterrupt, EOFError:
            pass


if __name__ == "__main__":
    main()
