"""Check the real P2 reference's FILE_SESSION gap, using an owned port-0 server."""

import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from test_file_bridge import FakeClient, wait

from bridge import Session, read_line


def test_reference_p2_file_session_unavailable_keeps_chat(tmp_path):
    default = Path(__file__).resolve().parents[2] / "../MMT-P2/A1_Client-Server"
    root = Path(os.environ.get("CONNECT_P2_ROOT", default)).resolve()
    if not (root / "server/socket_server.py").is_file():
        if os.environ.get("CONNECT_REQUIRE_INTEGRATION") == "1":
            pytest.fail("Required P2 checkout is missing; set CONNECT_P2_ROOT")
        pytest.skip("Real P2 reference checkout is not available")
    bootstrap = """
import json, sys, threading, time
sys.path.insert(0, sys.argv[1])
from server.socket_server import SocketServer
server = SocketServer(host="127.0.0.1", port=0)
thread = threading.Thread(target=server.start)
thread.start()
while server.server_socket is None or server.server_socket.getsockname()[1] == 0:
    time.sleep(0.01)
print(json.dumps({"port": server.server_socket.getsockname()[1]}), flush=True)
sys.stdin.readline()
server.stop()
thread.join()
"""
    process = subprocess.Popen(
        [sys.executable, "-B", "-u", "-c", bootstrap, str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    session = Session(str(uuid.uuid4()), FakeClient, tmp_path)
    try:
        port = json.loads(process.stdout.readline())["port"]
        username, password = (
            "file-check-" + uuid.uuid4().hex[:10],
            "public-p2-file-fixture",
        )
        with socket.create_connection(("127.0.0.1", port), timeout=2) as seed:
            seed.sendall(b"HELLO\n")
            assert read_line(seed) == b"WELCOME\n"
            seed.sendall(
                (
                    json.dumps(
                        dict(action="REGISTER", username=username, password=password)
                    )
                    + "\n"
                ).encode()
            )
            assert json.loads(read_line(seed))["status"] == "REGISTER_SUCCESS"
        session.open(("127.0.0.1", port), username, password)
        wait(lambda: session.file_requested and session.pending is None)
        snapshots = session.poll(0)["events"]
        assert any(
            e["type"] == "files.changed" and e["data"]["state"] == "unavailable"
            for e in snapshots
        )
        assert session.connected and session.files is None
        assert session.send_message(
            dict(
                requestId="p2-file-check",
                messageId="p2-file-msg",
                conversationId="global",
                text="Chat after unsupported FILE_SESSION",
            )
        )
        wait(lambda: session.pending is None)
        assert session.poll(0)["events"][-1]["data"]["status"] == "sent"
        with pytest.raises(ValueError, match="FILE_SESSION"):
            session.file_service()
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        evidence = dict(
            source="real P2 reference",
            commit=commit,
            pid=process.pid,
            port=port,
            fileSessionSupported=False,
            fileUIState="unavailable",
            tcpStillConnected=True,
            broadcastAck="BROADCAST_SUCCESS",
            fileBytesTransferred=0,
        )
        review = Path("runtime/reviews/files-2026-11-11")
        review.mkdir(parents=True, exist_ok=True)
        (review / "real-p2-dependency.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
    finally:
        session.end("disconnected")
        stdout, stderr = process.communicate("stop\n", timeout=5)
        assert process.returncode == 0, stderr
