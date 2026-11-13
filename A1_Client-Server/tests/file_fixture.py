"""Owned localhost services for P3 checks; ticket fixture is never real P2."""

import argparse
import base64
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import BridgeServer  # noqa: E402
from bridge_files import load_p1  # noqa: E402
from tests.p2_online_stub import OnlineServer  # noqa: E402


@contextmanager
def fixture(backend, output, *, p1_root=None, p2_root=None):
    """Stop only services created here, including on browser failure/timeout."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        factory, relay, tls, https, certs = None, None, None, None, None
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
        elif backend == "security":
            from security.tls import client_context, create_certificates, server_context
            from server.socket_server import SocketServer

            certs = output / "tls"
            create_certificates(certs)
            https = server_context(certs / "server.pem", certs / "server.key")
            tls = client_context(certs / "ca.pem")
            factory = load_p1(ROOT)
            tcp = SocketServer(host="127.0.0.1", port=0, udp_port=0, tls_context=https)
            thread = threading.Thread(target=tcp.start)
            thread.start()
            stack.callback(thread.join, 5)
            stack.callback(tcp.stop)
            deadline = time.monotonic() + 10
            while tcp.server_socket is None:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise TimeoutError("Secure P2 startup timed out")
                time.sleep(0.02)
            target = tcp.server_socket.getsockname()
            relay = tcp.file_relay
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
                tls_context=tls,
                https_context=https,
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
                "security": "real P2 TLS + v2 P1 AES-GCM; no ticket fixture",
            }[backend],
        )
        if certs:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization

            cert = x509.load_pem_x509_certificate((certs / "server.pem").read_bytes())
            digest = hashes.Hash(hashes.SHA256())
            digest.update(
                cert.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            metadata.update(
                scheme="https", spki=base64.b64encode(digest.finalize()).decode("ascii")
            )
        (output / "fixture.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        yield metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-root", type=Path)
    parser.add_argument("--security-browser", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/p3/fixtures")
    args = parser.parse_args()
    output = (
        args.output
        if args.security_browser
        else args.output / ("fixture-" + uuid.uuid4().hex)
    )
    with fixture(
        "security" if args.security_browser else "p1", output, p1_root=args.p1_root
    ) as config:
        if args.security_browser:
            try:
                subprocess.run(
                    [
                        "node",
                        "tests/browser-file-live.cjs",
                        "--config",
                        str(output / "fixture.json"),
                        "--output",
                        str(output / "browser"),
                    ],
                    cwd=ROOT,
                    check=True,
                    timeout=260,
                    env=dict(
                        os.environ, NODE_EXTRA_CA_CERTS=str(output / "tls/ca.pem")
                    ),
                )
            finally:
                import shutil

                shutil.rmtree(output / "tls")
            return
        print(json.dumps(dict(config, config=str(output / "fixture.json"))), flush=True)
        print(
            "Test auth/ticket fixture, real P1 UDP. Type stop or Ctrl+C to close.",
            flush=True,
        )
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass


if __name__ == "__main__":
    main()
