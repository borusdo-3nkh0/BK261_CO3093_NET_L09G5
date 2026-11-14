"""Owned localhost services for P3 checks; ticket fixture is never real P2."""

import argparse
import base64
import hashlib
import inspect
import json
import os
import shutil
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
        elif backend in {"p2", "integrated", "security"}:
            source = Path(p2_root).resolve(strict=True) if backend == "p2" else ROOT
            sys.path.insert(0, str(source))
            from server.socket_server import SocketServer

            if not Path(sys.modules[SocketServer.__module__].__file__).is_relative_to(
                source
            ):
                raise ValueError("P2 import does not match configured checkout")
            options = (
                {"udp_port": 0}
                if "udp_port" in inspect.signature(SocketServer).parameters
                else {}
            )
            if backend in {"integrated", "security"}:
                from security.tls import (
                    client_context,
                    create_certificates,
                    server_context,
                )

                certs = output / "tls"
                create_certificates(certs)
                stack.callback(shutil.rmtree, certs)
                https = server_context(certs / "server.pem", certs / "server.key")
                tls = client_context(certs / "ca.pem")
                options["tls_context"] = https
            tcp = SocketServer(host="127.0.0.1", port=0, **options)
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
            if backend in {"integrated", "security"}:
                factory = load_p1(ROOT)
                relay = tcp.file_relay
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
                "integrated": "same checkout P1/P2/P3; TLS/AES-GCM; real P2 FILE_SESSION",
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
        if backend in {"integrated", "security"}:
            metadata["revision"] = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, timeout=10
            ).strip()
            metadata["modules"] = {}
            for name in (
                "p1.client",
                "p1.relay",
                "shared.protocol",
                "server.socket_server",
                "bridge",
                "bridge_files",
            ):
                path = Path(sys.modules[name].__file__).resolve()
                if not path.is_relative_to(ROOT):
                    raise ValueError("Integrated module outside checkout: " + name)
                metadata["modules"][name] = {
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
        (output / "fixture.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        yield metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-root", type=Path)
    parser.add_argument("--p2-root", type=Path)
    parser.add_argument(
        "--backend", choices=["p1", "p2", "ui", "integrated", "security"], default="p1"
    )
    parser.add_argument("--security-browser", action="store_true")
    parser.add_argument("--run-browser", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/p3/fixtures")
    args = parser.parse_args()
    if args.security_browser:
        args.backend, args.run_browser = "security", True
    # Managed checks already own a UUID directory; avoid another Windows path level.
    output = (
        args.output
        if args.run_browser
        else args.output / ("fixture-" + uuid.uuid4().hex)
    )
    with fixture(
        args.backend, output, p1_root=args.p1_root, p2_root=args.p2_root
    ) as config:
        print(json.dumps(dict(config, config=str(output / "fixture.json"))), flush=True)
        print(config["source"], flush=True)
        if args.run_browser:
            if args.backend == "integrated":
                command = [
                    "node",
                    "tests/browser-integrated-live.cjs",
                    "--http",
                    str(config["http"]),
                    "--tcp",
                    str(config["tcp"]),
                    "--output",
                    str(output / "browser"),
                    "--spki",
                    config["spki"],
                ]
            elif args.backend == "p2":
                command = [
                    "node",
                    "tests/browser-p2-live.cjs",
                    str(config["http"]),
                    str(config["tcp"]),
                ]
            else:
                command = [
                    "node",
                    "tests/browser-file-live.cjs",
                    "--config",
                    str(output / "fixture.json"),
                    "--output",
                    str(output / "browser"),
                    "--suite",
                    "ui" if args.backend == "ui" else "files",
                ]
            env = dict(os.environ, CONNECT_TEST_OUTPUT=str(output / "browser"))
            if config.get("scheme") == "https":
                env["NODE_EXTRA_CA_CERTS"] = str(output / "tls/ca.pem")
            subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                timeout=260,
                env=env,
            )
            return
        print("Type stop or Ctrl+C to close.", flush=True)
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass


if __name__ == "__main__":
    main()
