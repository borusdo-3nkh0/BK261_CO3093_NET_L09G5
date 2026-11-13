import argparse
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import pytest

from p3 import REFERENCES, ROOT, Check, junit_counts, main, public, reference, stop_tree
from process_job import WindowsJob


def args(tmp_path, **changes):
    return argparse.Namespace(
        output=tmp_path,
        timeout=30,
        suite=["p1"],
        p1_root=tmp_path / "missing-p1",
        p2_root=tmp_path / "missing-p2",
        **changes,
    )


@pytest.mark.parametrize("suite", ["p1", "p2"])
def test_required_integration_missing_checkout_is_fail_not_skip(tmp_path, suite):
    config = args(tmp_path)
    config.suite = [suite]
    check = Check(config)
    assert check.run() == 1
    report = json.loads((check.output / "report.json").read_text(encoding="utf-8"))
    result = next(s for s in report["suites"] if s["name"] == suite)
    assert result["status"] == "FAIL" and "Missing" in result["reason"]
    assert all(
        s["status"] == "SKIP" and s["reason"] == "Not selected"
        for s in report["suites"]
        if s["name"] != suite
    )


@pytest.mark.parametrize(
    "xml", ["<testsuite/>", "<testsuite><testcase><skipped/></testcase></testsuite>"]
)
def test_no_executed_integration_is_rejected(tmp_path, xml):
    path = tmp_path / "junit.xml"
    path.write_text(xml, encoding="utf-8")
    with pytest.raises(RuntimeError, match="all skipped"):
        junit_counts(path, required=True)


def test_public_report_removes_nested_credentials_and_error_values():
    value = public(
        {
            "token": "CANARY_TOKEN",
            "nested": [
                {"ticket": {"key": "CANARY_KEY"}},
                {"password": "CANARY_PASSWORD"},
            ],
            "error": 'token="CANARY_ERROR with spaces"',
            "durationSeconds": 2,
        }
    )
    text = json.dumps(value)
    assert "CANARY" not in text and value["durationSeconds"] == 2
    assert value["nested"][0]["ticket"] == "[REDACTED]"


def test_each_check_gets_a_new_run_directory(tmp_path):
    first, second = Check(args(tmp_path)), Check(args(tmp_path))
    assert first.output != second.output
    assert first.output.is_dir() and second.output.is_dir()


def test_nonzero_command_keeps_failure_log(tmp_path):
    check = Check(args(tmp_path))
    with pytest.raises(RuntimeError, match="exited 7"):
        check.step(
            "failure",
            [sys.executable, "-c", "print('intentional failure'); raise SystemExit(7)"],
        )
    assert "intentional failure" in (check.output / "failure.log").read_text()


def test_timeout_kills_owned_child_tree(tmp_path):
    check = Check(args(tmp_path))
    check.deadline = time.monotonic() + 3
    port_file = tmp_path / "child-port.txt"
    child = f"import socket,time,pathlib; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); pathlib.Path({str(port_file)!r}).write_text(str(s.getsockname()[1])); time.sleep(60)"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(60)"
    with pytest.raises(TimeoutError):
        check.step("timeout", [sys.executable, "-c", parent])
    port = int(port_file.read_text())
    with socket.socket() as probe:
        probe.settimeout(0.5)
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_job_close_kills_descendant_after_parent_exits(tmp_path):
    port_file = tmp_path / "orphan-port.txt"
    child = f"import socket,time,pathlib; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); pathlib.Path({str(port_file)!r}).write_text(str(s.getsockname()[1])); time.sleep(60)"
    parent = f"import subprocess,sys,time,pathlib; time.sleep(0.2); subprocess.Popen([sys.executable,'-c',{child!r}]); p=pathlib.Path({str(port_file)!r}); deadline=time.monotonic()+5\nwhile not p.exists() and time.monotonic()<deadline: time.sleep(0.01)"
    job = WindowsJob()
    process = subprocess.Popen([sys.executable, "-c", parent])
    try:
        job.attach(process)
        process.wait(timeout=10)
        port = int(port_file.read_text())
    finally:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    deadline = time.monotonic() + 3
    while True:
        with socket.socket() as probe:
            probe.settimeout(0.1)
            closed = probe.connect_ex(("127.0.0.1", port)) != 0
        if closed or time.monotonic() > deadline:
            break
    assert closed


def test_fixture_closes_its_http_listener(tmp_path):
    from tests.file_fixture import fixture

    with fixture("ui", tmp_path) as config:
        with urlopen(f"http://127.0.0.1:{config['http']}/", timeout=2) as response:
            assert response.status == 200
        assert config["source"] == "UI/demo only; no backend"
    with socket.socket() as probe:
        probe.settimeout(0.5)
        assert probe.connect_ex(("127.0.0.1", config["http"])) != 0


def test_reference_revision_mismatch_is_not_accepted(tmp_path, monkeypatch):
    import subprocess

    (tmp_path / "p1").mkdir()
    (tmp_path / "p1/client.py").write_text("")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: argparse.Namespace(stdout="wrong-revision")
    )
    with pytest.raises(RuntimeError, match="differs from pinned"):
        reference("p1", tmp_path)


def test_reference_dirty_tracked_source_is_not_accepted(tmp_path, monkeypatch):
    (tmp_path / "p1").mkdir()
    (tmp_path / "p1/client.py").write_text("")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: argparse.Namespace(
            stdout=REFERENCES["p1"] if "rev-parse" in command else " M p1/client.py"
        ),
    )
    with pytest.raises(RuntimeError, match="not clean"):
        reference("p1", tmp_path)


def test_all_selects_current_checkout_without_legacy_or_large(tmp_path, monkeypatch):
    config = args(tmp_path)
    config.suite = ["all"]
    check = Check(config)
    selected = []

    def record(name):
        selected.append(name)
        check.report["suites"].append(dict(name=name, status="PASS"))

    monkeypatch.setattr(check, "suite", record)
    assert check.run() == 0
    assert selected == ["independent", "ui", "integrated", "security"]


def test_check_defaults_to_current_suites(monkeypatch):
    selected = []
    monkeypatch.setattr(sys, "argv", ["p3.py", "check"])
    monkeypatch.setattr(
        Check, "run", lambda self: selected.extend(self.args.suite) or 0
    )
    assert main() == 0 and selected == ["all"]


@pytest.mark.parametrize("timeout", ["inf", "nan", "0", "-1"])
def test_timeout_argument_rejects_unbounded_or_invalid_deadline(monkeypatch, timeout):
    monkeypatch.setattr(sys, "argv", ["p3.py", "check", "--timeout", timeout])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_one_command_demo_uses_own_assets_and_stops(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-B", "-u", str(ROOT / "p3.py"), "demo", "--port", "0"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONUTF8="1"),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    lines = queue.Queue()
    threading.Thread(
        target=lambda: lines.put(process.stdout.readline()), daemon=True
    ).start()
    try:
        url = re.search(r"http://\S+", lines.get(timeout=10)).group()
        with urlopen(url, timeout=2) as response:
            assert "Chế độ mô phỏng" in response.read().decode("utf-8")
        with urlopen(url.replace("local-demo/", ""), timeout=2) as response:
            assert b"js/main.js" in response.read()
    finally:
        stop_tree(process)
        process.stdout.close()
