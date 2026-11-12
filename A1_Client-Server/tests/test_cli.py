"""Exercise the documented commands in separate Python processes."""

import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="p1-cli-test-")
        self.root = Path(temporary.name)
        self.addCleanup(temporary.cleanup)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "p1", *map(str, args)],
            cwd=APP,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )

    def start_cli(self, *args):
        process = subprocess.Popen(
            [sys.executable, "-m", "p1", *map(str, args)],
            cwd=APP,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        lines = queue.Queue()

        def read():
            for line in process.stdout:
                lines.put(line.rstrip("\n"))

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def stop():
            if process.poll() is None:
                if os.name == "posix":
                    process.send_signal(signal.SIGINT)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()

        self.addCleanup(stop)
        return process, lines

    def test_one_command_demo_verifies_files_both_directions(self):
        output = self.root / "demo"
        result = self.run_cli("demo", "--output", output)
        self.assertEqual(result.stdout.count("VERIFIED"), 4)
        sources = output / "sources"
        received = [path for path in (output / "bob").glob("*/*") if path.is_file()]
        self.assertEqual(len(received), 3)
        for path in received:
            self.assertEqual(path.read_bytes(), (sources / path.name).read_bytes())

    def test_separate_relay_receiver_and_sender_commands(self):
        tickets = self.root / "tickets"
        self.run_cli("init-demo", "--directory", tickets)
        relay, relay_lines = self.start_cli(
            "serve", "--sessions", tickets / "server.json", "--port", 0
        )
        ready = relay_lines.get(timeout=10)
        self.assertIn("listening on", ready)
        port = ready.rsplit(":", 1)[1]
        receiver, receiver_lines = self.start_cli(
            "receive",
            "--ticket",
            tickets / "bob.json",
            "--port",
            port,
            "--download-dir",
            self.root / "received",
        )
        self.assertIn("Ready as bob", receiver_lines.get(timeout=10))
        data = bytes(range(256)) * 128 + b"partial final chunk"
        source = self.root / "binary.bin"
        source.write_bytes(data)
        received_paths = []
        for _ in range(2):
            sent = self.run_cli(
                "send",
                "--ticket",
                tickets / "alice.json",
                "--port",
                port,
                "--recipient",
                "bob",
                "--file",
                source,
            )
            result = json.loads(sent.stdout)
            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                event = json.loads(receiver_lines.get(timeout=5))
                if event["type"] == "file_received":
                    path = Path(event["path"])
                    self.assertEqual(path.read_bytes(), data)
                    received_paths.append(path)
                    break
            else:
                self.fail("Receiver did not report completion")
        self.assertEqual(len(set(received_paths)), 2)
        self.assertIsNone(relay.poll())
        self.assertIsNone(receiver.poll())


if __name__ == "__main__":
    unittest.main()
