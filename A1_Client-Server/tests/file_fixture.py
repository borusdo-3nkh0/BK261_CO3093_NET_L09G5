"""Test auth/control + real P1 UDP; explicitly not a P2 implementation."""

import argparse
import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p2_online_stub import OnlineServer  # noqa: E402

from bridge import BridgeServer  # noqa: E402
from bridge_files import load_p1  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-root", type=Path, required=True)
    args = parser.parse_args()
    factory = load_p1(args.p1_root)
    from p1.relay import FileRelay

    review = Path("runtime/reviews/files-2026-11-11")
    review.mkdir(parents=True, exist_ok=True)
    with FileRelay(port=0) as relay:
        with OnlineServer(("127.0.0.1", 0), file_relay=relay) as tcp:
            thread = threading.Thread(target=tcp.serve_forever, daemon=True)
            thread.start()
            with BridgeServer(
                ("127.0.0.1", 0),
                tcp.server_address,
                file_factory=factory,
                storage=review / "fixture-storage",
            ) as http:
                metadata = dict(
                    source="test control fixture + real P1 UDP; NOT P2",
                    pid=os.getpid(),
                    tcp=tcp.server_address[1],
                    http=http.server_port,
                    udp=relay.address[1],
                )
                (review / "fixture.json").write_text(
                    json.dumps(metadata, indent=2), encoding="utf-8"
                )
                print(json.dumps(metadata), flush=True)

                def stop_on_input():
                    if sys.stdin.readline().strip() == "stop":
                        http.shutdown()

                threading.Thread(target=stop_on_input, daemon=True).start()
                try:
                    http.serve_forever()
                except KeyboardInterrupt:
                    pass
            tcp.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
