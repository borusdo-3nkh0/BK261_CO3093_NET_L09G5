import argparse
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

import pytest

from p3 import (
    REFERENCES,
    ROOT,
    Check,
    browser_rows,
    junit_counts,
    junit_rows,
    main,
    measured,
    node_totals,
    public,
    reference,
    status_counts,
    stop_tree,
)
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


def table_records(text):
    records = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) == 8 and cells[0] in {
            "RUN",
            "PASS",
            "FAIL",
            "SKIP",
            "RECORDED",
            "INCOMPLETE",
            "NOT RUN",
        }:
            records.append(cells)
    return records


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


def test_output_junit_status_time_reason_and_duplicate_records(tmp_path):
    xml = tmp_path / "cases.xml"
    xml.write_text(
        """<testsuite tests="99"><testcase classname="sample" name="ok" time="0.012"/>
      <testcase classname="sample" name="skip" time="0.001"><skipped message="not available"/></testcase>
      <testcase classname="sample" name="bad" time="0.021"><failure message="wrong value"/></testcase>
      <testcase classname="sample" name="bad" time="0.002"><error message="teardown"/></testcase>
      </testsuite>""",
        encoding="utf-8",
    )
    rows = junit_rows(xml)
    assert len(rows) == 3  # XML suite total is not a count of pytest parent tests.
    assert status_counts(rows) == {"pytest": {"PASS": 1, "FAIL": 1, "SKIP": 1}}
    assert rows[0]["id"] == "sample::ok" and measured(rows[0]["seconds"]) == "0.012s"
    assert rows[1]["reason"] == "not available"
    assert rows[2]["status"] == "FAIL" and rows[2]["seconds"] is None
    assert "wrong value" in rows[2]["reason"] and "teardown" in rows[2]["reason"]
    assert measured(None) == measured("not measured") == "—"


def test_output_subtests_are_separate_and_only_read_final_summary(tmp_path, capsys):
    check = Check(args(tmp_path / "pytest-88"))
    xml = tmp_path / "cases.xml"
    xml.write_text(
        '<testsuite tests="99"><testcase classname="sample" name="parent" time="0.004"/></testsuite>',
        encoding="utf-8",
    )
    check.show_step(
        "python",
        "captured 88 subtests passed\n1 passed, 3 subtests passed in 0.02s\n",
        xml,
        dict(exitCode=0, durationSeconds=0.2),
    )
    totals = status_counts(check.output_rows["direct"])
    assert totals["pytest"]["PASS"] == 1
    assert totals["subtest"] == {"PASS": 3, "FAIL": None, "SKIP": None}
    text = capsys.readouterr().out
    assert "pytest-88" in str(check.output)  # Paths are not subtest counts.
    assert str(check.output) not in text  # No per-step log paths on the terminal.
    subtests = [row for row in check.output_rows["direct"] if row["kind"] == "subtest"]
    assert len(subtests) == 1 and subtests[0]["counts"]["PASS"] == 3
    assert check.output_rows["direct"][0]["seconds"] == "0.004"
    assert not any(row[1] == "subtest" for row in table_records(text))
    check.report.update(status="PASS", durationSeconds=0.2)
    check.report["suites"] = [dict(name="direct", status="PASS")]
    check.summary()
    summary = capsys.readouterr().out
    assert summary.count("3 subtest đạt") == 1
    assert not any(row[1] == "subtest" for row in table_records(summary))


def test_output_browser_scenarios_are_not_assertions_or_invented_failures(
    tmp_path, capsys
):
    check = Check(args(tmp_path))
    check.active_suite = "ui"
    folder = check.output / "ui" / "browser"
    folder.mkdir(parents=True)
    data = dict(
        status="FAIL",
        checks=["login and incoming chat"],
        regression=[
            dict(
                viewport=[1440, 900],
                results=[dict(passed=2, checks=["label", "focus"])],
            )
        ],
        error='token="CANARY"\nraw details',
        token="CANARY",
    )
    (folder / "report.json").write_text(json.dumps(data), encoding="utf-8")
    check.show_step("ui-browser", "", None, dict(exitCode=1, durationSeconds=2.718))
    totals = status_counts(check.output_rows["ui"])
    assert totals["browser case"] == {"PASS": 1, "FAIL": 0, "SKIP": 0}
    assert totals["browser assertions"] == {"PASS": 2, "FAIL": None, "SKIP": None}
    assert totals["browser run"]["FAIL"] == 1
    text = capsys.readouterr().out
    assert "n/a" not in text and "2.718s" in text and "CANARY" not in text
    assert "raw details" not in text and "label |" not in text
    assert len(browser_rows(data)) == 2
    records = table_records(text)
    case = next(row for row in records if row[1] == "browser case")
    assert case[2] == "login and incoming chat" and "checks[" not in text
    assertions = next(row for row in records if row[1] == "browser assertions")
    assert assertions[3:] == ["—", "2", "—", "—", "—"]
    run = next(row for row in records if row[1] == "browser run")
    assert run[0] == "FAIL" and run[3] == "1/1"


def test_output_demo_counts_and_unknown_values_are_preserved():
    data = dict(
        demo=[dict(viewport=[390, 844], smoke=dict(passed=33), company=dict(passed=37))]
    )
    totals = status_counts(browser_rows(data))
    assert totals == {"browser assertions": {"PASS": 70, "FAIL": None, "SKIP": None}}
    assert not browser_rows(dict(status="PASS", outgoing=dict(hashMatch=True)))


@pytest.mark.parametrize(
    "report_status,filename,exit_code,timed_out,done,status",
    [
        ("PASS", "report.json", 0, False, "1/1", "PASS"),
        ("FAIL", "report.json", 1, False, "1/1", "FAIL"),
        ("SKIP", "results.json", 0, False, "1/1", "SKIP"),
        ("PASS", "report.json", 0, True, "—", "FAIL"),
        ("PASS", "report.json", 1, False, "—", "FAIL"),
        ("FAIL", "partial-failure.json", 1, False, "—", "FAIL"),
        (None, "report.json", 1, False, "—", "FAIL"),
    ],
)
def test_output_browser_run_completion_and_whole_process_time(
    tmp_path, capsys, report_status, filename, exit_code, timed_out, done, status
):
    check = Check(args(tmp_path))
    folder = check.output / "direct"
    folder.mkdir()
    if report_status:
        (folder / filename).write_text(
            json.dumps(dict(status=report_status, durationSeconds=1.111)),
            encoding="utf-8",
        )
    check.show_step(
        "ui-browser",
        "",
        None,
        dict(exitCode=exit_code, durationSeconds=2.345),
        timed_out=timed_out,
    )
    records = table_records(capsys.readouterr().out)
    assert len(records) == 1
    assert records[0][0] == status and records[0][3] == done
    assert records[0][-1] == "2.345s"  # Full process, not report's inner timer.


def test_output_browser_running_has_no_invented_progress(tmp_path, capsys):
    check = Check(args(tmp_path))
    folder = check.output / "direct"
    folder.mkdir()
    (folder / "report.json").write_text('{"status":"PASS"}', encoding="utf-8")
    result = check.step("ui-browser", [sys.executable, "-c", "pass"])
    records = table_records(capsys.readouterr().out)
    assert records[0][0] == "RUN" and records[0][3:] == ["—"] * 5
    assert records[1][0] == "PASS" and records[1][3] == "1/1"
    assert records[1][-1] == measured(result["durationSeconds"])


def test_output_node_and_unittest_use_only_recorded_times(tmp_path, capsys):
    check = Check(args(tmp_path))
    result = dict(exitCode=0, durationSeconds=1.5)
    check.show_step(
        "js-support", "\u2714 helper (12.5ms)\n\ufe63 optional (1ms)\n", None, result
    )
    check.show_step(
        "p1-reference",
        "test_ok (tests.Example.test_ok) ... ok\ntest_off (tests.Example.test_off) ... skipped 'not available'\n",
        None,
        result,
    )
    rows = check.output_rows["direct"]
    assert rows[0]["seconds"] == 0.0125 and rows[1]["status"] == "SKIP"
    assert all(row["seconds"] is None for row in rows if row["kind"] == "unittest")
    text = capsys.readouterr().out
    assert "node test" in text and "unittest" in text
    assert "PASS | test_ok" not in text


@pytest.mark.parametrize("quiet", [False, True])
def test_output_quiet_failure_summary_and_report_schema(tmp_path, capsys, quiet):
    config = args(tmp_path, quiet=quiet)
    check = Check(config)
    original_keys = set(check.report)
    assert check.run() == 1
    text = capsys.readouterr().out
    assert "p1: FAIL" in text and "Report:" in text
    assert ("SUITE p1" in text) is (not quiet)
    assert ("SUMMARY" in text) is (not quiet)
    if not quiet:
        assert "Pinned P1" in text and "Missing P1 checkout" in text
        assert "Not selected" in text and "n/a" not in text
        assert text.count("— = không áp dụng hoặc chưa được ghi nhận riêng") == 1
    report = json.loads((check.output / "report.json").read_text(encoding="utf-8"))
    assert set(report) == original_keys | {"durationSeconds", "artifactAudit", "status"}
    assert "output_rows" not in report
    assert all(
        set(s) == {"name", "status", "reason", "durationSeconds", "steps"}
        if s["name"] == "p1"
        else set(s) == {"name", "status", "reason", "durationSeconds"}
        for s in report["suites"]
    )


def test_output_load_report_only_uses_explicit_verdicts_and_elapsed(tmp_path, capsys):
    check = Check(args(tmp_path))
    folder = check.output / "load"
    folder.mkdir()
    data = {
        "cases": {
            "IT11": [
                dict(verdict="Đạt", elapsedSeconds=12.345),
                dict(verdict="Không đạt", reason="missing deliveries"),
            ],
            "IT12": dict(verdict="Chưa chạy"),
        }
    }
    (folder / "results.json").write_text(json.dumps(data), encoding="utf-8")
    check.show_step("load-clients", "", None, dict(exitCode=1, durationSeconds=20.0))
    rows = check.output_rows["direct"]
    assert status_counts(rows) == {"system case": {"PASS": 1, "FAIL": 1, "SKIP": 1}}
    assert rows[0]["seconds"] == 12.345 and rows[1]["seconds"] is None
    assert "missing deliveries" in capsys.readouterr().out


def test_output_quiet_cli_argument(monkeypatch):
    selected = []
    monkeypatch.setattr(sys, "argv", ["p3.py", "check", "--quiet"])
    monkeypatch.setattr(
        Check, "run", lambda self: selected.append(self.args.quiet) or 0
    )
    assert main() == 0 and selected == [True]


def test_output_timeout_does_not_print_pass_even_for_zero_exit(tmp_path, capsys):
    check = Check(args(tmp_path))
    check.show_step(
        "deadline", "", None, dict(exitCode=0, durationSeconds=3.14), timed_out=True
    )
    text = capsys.readouterr().out
    assert any(row[0] == "FAIL" and row[2] == "deadline" for row in table_records(text))
    assert check.output_groups["direct"][0]["status"] == "FAIL"


def test_output_required_all_skipped_is_not_a_passing_step(tmp_path, capsys):
    check = Check(args(tmp_path))
    xml = tmp_path / "skip.xml"
    xml.write_text(
        '<testsuite><testcase name="optional" time="0.001"><skipped message="missing dependency"/></testcase></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="all skipped"):
        check.step("required", [sys.executable, "-c", "pass"], junit=xml, required=True)
    text = capsys.readouterr().out
    assert any(row[0] == "SKIP" and row[1] == "pytest" for row in table_records(text))
    assert not any(row[0] == "PASS" for row in table_records(text))


def test_output_bad_report_does_not_change_process_verdict(tmp_path, capsys):
    check = Check(args(tmp_path))
    check.active_suite = "ui"
    folder = check.output / "ui"
    folder.mkdir()
    (folder / "report.json").write_text("not JSON", encoding="utf-8")
    result = check.step("ui-browser", [sys.executable, "-c", "pass"])
    assert result["exitCode"] == 0
    assert "Output detail unavailable" in capsys.readouterr().out
    assert set(result) == {"name", "exitCode", "pid", "durationSeconds"}


@pytest.mark.parametrize("terminal", [False, True])
def test_output_live_group_counts_terminal_and_duplicate_event(
    tmp_path, capsys, terminal
):
    check = Check(args(tmp_path))
    check.terminal = terminal
    check.progress_event(
        "python", dict(event="collected", groups={"tests/test_group.py": 3})
    )
    check.progress_event("python", dict(event="start", group="tests/test_group.py"))
    for index, status in enumerate(("PASS", "FAIL", "SKIP")):
        event = dict(
            event="complete",
            group="tests/test_group.py",
            index=index,
            id=f"tests/test_group.py::case_{status}",
            status=status,
            reason="expected fixture reason",
            elapsed=(index + 1) * 0.2,
        )
        check.progress_event("python", event)
        if index == 0:
            check.progress_event("python", event)
    group = check.pytest_groups[("direct", "python")]["tests/test_group.py"]
    assert group["done"] == group["total"] == 3
    assert group["counts"] == {"PASS": 1, "FAIL": 1, "SKIP": 1}
    assert group["status"] == "FAIL" and group["seconds"] == pytest.approx(0.6)
    text = capsys.readouterr().out
    assert ("\r" in text) is terminal
    assert {row[3] for row in table_records(text)} >= {"1/3", "3/3"}
    assert "case_PASS" not in text and "case_FAIL" in text and "case_SKIP" in text


def test_output_incomplete_collection_is_not_counted_as_skipped(tmp_path, capsys):
    check = Check(args(tmp_path))
    check.progress_event(
        "python", dict(event="collected", groups={"a.py": 4, "b.py": 2})
    )
    check.progress_event("python", dict(event="start", group="a.py"))
    check.progress_event(
        "python",
        dict(
            event="complete",
            group="a.py",
            index=0,
            id="a.py::first",
            status="PASS",
            reason="",
            elapsed=0.1,
        ),
    )
    check.progress_event("python", dict(event="incomplete", group="a.py", elapsed=0.2))
    check.finish_progress("python")
    groups = check.pytest_groups[("direct", "python")]
    assert groups["a.py"]["status"] == "INCOMPLETE" and groups["a.py"]["done"] == 1
    assert (
        groups["b.py"]["status"] == "NOT RUN" and groups["b.py"]["counts"]["SKIP"] == 0
    )
    assert any(row[3] == "1/4" for row in table_records(capsys.readouterr().out))


def test_output_real_collection_deselection_teardown_and_subtest_failure(
    tmp_path, capsys
):
    fixture = tmp_path / "test_progress_cases.py"
    fixture.write_text(
        """import pytest
@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError("fixture teardown failed")
def test_keep():
    assert True
def test_drop():
    assert False, "must be deselected"
def test_teardown(bad_teardown):
    assert True
def test_subtest(subtests):
    with subtests.test(number=1):
        assert False, "fixture subtest failed"
    with subtests.test(number=2):
        assert True
""",
        encoding="utf-8",
    )
    check = Check(args(tmp_path))
    xml = check.output / "cases.xml"
    with pytest.raises(RuntimeError, match="exited 1"):
        check.step(
            "fixture",
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                str(fixture),
                "-k",
                "not test_drop",
                f"--junitxml={xml}",
            ],
            junit=xml,
        )
    group = next(iter(check.pytest_groups[("direct", "fixture")].values()))
    assert group["total"] == group["done"] == 3
    assert group["counts"] == {"PASS": 1, "FAIL": 2, "SKIP": 0}
    assert group["seconds"] is not None
    assert not list(check.output.glob("*.events"))
    text = capsys.readouterr().out
    assert "test_drop" not in text and "test_keep" not in text
    assert "fixture teardown failed" in text and "fixture subtest failed" in text


def test_output_short_real_run_sample(tmp_path, capsys):
    fixture = tmp_path / "test_output_fixture.py"
    release, finished = tmp_path / "release.txt", tmp_path / "finished.txt"
    fixture.write_text(
        f"""import pytest, time
from pathlib import Path
def test_runner_pass():
    assert 2 + 2 == 4
@pytest.mark.skip(reason="output fixture: optional condition unavailable")
def test_runner_skip():
    pass
def test_runner_subtests(subtests):
    deadline=time.monotonic()+10
    while not Path({str(release)!r}).exists() and time.monotonic()<deadline:
        time.sleep(0.01)
    assert Path({str(release)!r}).exists(), 'Parent did not display live progress'
    for value in (1, 2):
        with subtests.test(value=value):
            assert value > 0
    Path({str(finished)!r}).write_text('finished')
""",
        encoding="utf-8",
    )
    second = tmp_path / "test_output_second.py"
    second.write_text("def test_next_module():\n    assert True\n", encoding="utf-8")
    config = args(tmp_path)
    config.suite = []  # Direct runner self-check, never a substitute product suite.
    check = Check(config)
    check.active_suite = "runner-output"
    original = check.progress_event
    proof = []

    def observe(step, event):
        original(step, event)  # Print the actual update before releasing the test.
        if event["event"] == "complete" and event["index"] == 0:
            proof.append(not finished.exists())
            release.write_text("progress observed", encoding="utf-8")

    check.progress_event = observe
    check.detail(
        "SUITE runner-output - direct runner/output fixture only; no product suite"
    )
    started = time.monotonic()
    xml = check.output / "runner.xml"
    step = check.step(
        "output-self-check",
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            str(fixture),
            str(second),
            f"--rootdir={fixture.parent}",
            f"--junitxml={xml}",
        ],
        junit=xml,
    )
    check.report["suites"].append(
        dict(
            name="runner-output",
            status="PASS",
            reason="Direct runner self-check only",
            steps=[step],
            durationSeconds=round(time.monotonic() - started, 3),
        )
    )
    assert check.run() == 0
    text = capsys.readouterr().out
    (check.output / "console.txt").write_text(text, encoding="utf-8")
    assert proof == [True], (
        "Progress must be displayed while the child is still running"
    )
    assert "test_runner_pass" not in text and "test_runner_skip" in text
    assert {row[3] for row in table_records(text)} >= {"1/3", "3/3", "1/1"}
    assert "\r" not in text  # Captured/redirected output is ordinary lines.
    assert "output fixture: optional condition unavailable" in text
    assert status_counts(check.output_rows["runner-output"])["pytest"] == {
        "PASS": 3,
        "FAIL": 0,
        "SKIP": 1,
    }
    assert status_counts(check.output_rows["runner-output"])["subtest"]["PASS"] == 2
    (check.output / "live-proof.txt").write_text(
        "Completion displayed before child finished: True\n", encoding="utf-8"
    )
    assert "SUMMARY" in text and "Report:" in text


def test_output_aux_syntax_group_alignment_and_measured_batch(tmp_path, capsys):
    check = Check(args(tmp_path))
    sources = [tmp_path / "pass-one.js", tmp_path / "pass-two.js"]
    for source in sources:
        source.write_text("const value = 1;", encoding="utf-8")
    started = time.monotonic()
    check.begin_syntax(sources)
    for _source in sources:
        check.show_step("js-syntax", "", None, dict(exitCode=0, durationSeconds=999))
    check.end_syntax()
    elapsed = time.monotonic() - started
    group = check.output_groups["direct"][0]
    assert len(check.output_groups["direct"]) == 1
    assert group["kind"] == "syntax files" and group["done"] == group["total"] == len(
        sources
    )
    assert group["counts"] == {"PASS": 2, "FAIL": 0, "SKIP": 0}
    assert (
        0 <= group["seconds"] <= elapsed
    )  # Wall-clock batch, not the two fake step times.
    text = capsys.readouterr().out
    records = table_records(text)
    assert [row[3] for row in records] == ["0/2", "1/2", "2/2"]
    assert sum(row[0] == "PASS" for row in records) == 1
    assert "pass-one.js" not in text and "pass-two.js" not in text
    columns = [line for line in text.splitlines() if len(line.split("|")) == 8]
    assert (
        len(
            {tuple(i for i, char in enumerate(line) if char == "|") for line in columns}
        )
        == 1
    )
    run = check.columns(("RUN", "pytest", "short", "9/100", 9, 0, 0, ""))
    done = check.columns(
        ("PASS", "pytest", "a longer group", "100/100", 100, 0, 0, "1.234s")
    )
    assert [i for i, char in enumerate(run) if char == "|"] == [
        i for i, char in enumerate(done) if char == "|"
    ]
    assert run.split(" | ")[2].startswith("short")
    assert done.split(" | ")[4].endswith("100") and done.split(" | ")[-1].endswith(
        "1.234s"
    )


def test_output_aux_syntax_failure_only_reports_failed_file(tmp_path, capsys):
    check = Check(args(tmp_path))
    sources = [tmp_path / name for name in ("good.js", "bad.js", "not-run.js")]
    check.begin_syntax(sources)
    check.show_step("js-syntax", "", None, dict(exitCode=0, durationSeconds=1))
    check.show_step(
        "js-syntax",
        "bad.js:1\nSyntaxError: Unexpected token\n",
        None,
        dict(exitCode=1, durationSeconds=1),
    )
    check.end_syntax(RuntimeError("js-syntax exited 1; see js-syntax.log"))
    group = check.output_groups["direct"][0]
    assert group["status"] == "FAIL" and group["done"] == 2 and group["total"] == 3
    assert group["counts"] == {"PASS": 1, "FAIL": 1, "SKIP": 0}
    text = capsys.readouterr().out
    assert "bad.js" in text and text.count("SyntaxError") == 1
    assert "good.js" not in text and "not-run.js" not in text and ".log" not in text
    assert sum(row[0] == "FAIL" for row in table_records(text)) == 1


def test_output_aux_short_sample(tmp_path, capsys):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for the short auxiliary output sample")
    python_source = tmp_path / "clean.py"
    python_source.write_text("value = 1\n", encoding="utf-8")
    helper = tmp_path / "helper.cjs"
    helper.write_text(
        "const test = require('node:test'); const assert = require('node:assert/strict');\ntest('helper fixture', () => assert.equal(1 + 1, 2));\n",
        encoding="utf-8",
    )
    for name in ("syntax-one.js", "syntax-two.js"):
        (tmp_path / name).write_text("const value = 1;\n", encoding="utf-8")
    config = args(tmp_path)
    config.suite = []
    check = Check(config)
    check.active_suite = "aux-output"
    check.detail("SUITE aux-output - short output fixture only; no full project checks")
    started = time.monotonic()
    steps = [
        check.step("lint", [sys.executable, "-m", "ruff", "check", str(python_source)]),
        check.step(
            "format",
            [sys.executable, "-m", "ruff", "format", "--check", str(python_source)],
        ),
        check.step("js-support", [node, "--test", "--test-reporter=spec", str(helper)]),
    ]
    sources = sorted(tmp_path.glob("syntax-*.js"))
    check.begin_syntax(sources)
    try:
        for source in sources:
            check.step("js-syntax", [node, "--check", str(source)])
    finally:
        check.end_syntax(sys.exc_info()[1])
    steps.append(dict(name="js-syntax", status="PASS"))
    check.report["suites"].append(
        dict(
            name="aux-output",
            status="PASS",
            reason="Short output fixture only",
            steps=steps,
            durationSeconds=round(time.monotonic() - started, 3),
        )
    )
    assert check.run() == 0
    text = capsys.readouterr().out
    (check.output / "console.txt").write_text(text, encoding="utf-8")
    before, summary = text.split("SUMMARY", 1)
    for name in ("lint", "format", "js-support", "js-syntax"):
        assert (
            sum(row[0] == "PASS" and row[2] == name for row in table_records(before))
            == 1
        )
    for name in ("lint", "format"):
        assert [
            (row[0], row[3]) for row in table_records(before) if row[2] == name
        ] == [("RUN", "0/1"), ("PASS", "1/1")]
    assert [
        (row[0], row[3]) for row in table_records(before) if row[2] == "js-support"
    ] == [("RUN", "—"), ("PASS", "1/1")]
    syntax = [row for row in table_records(summary) if row[2] == "js-syntax"]
    assert (
        len(syntax) == 1
        and syntax[0][1] == "syntax files"
        and syntax[0][3:7] == ["2/2", "2", "0", "0"]
    )
    assert len(check.output_groups["aux-output"]) == 4
    assert {row[3] for row in table_records(before) if row[2] == "js-syntax"} == {
        "0/2",
        "1/2",
        "2/2",
    }
    assert "syntax-one.js" not in text and "syntax-two.js" not in text
    assert text.count("Report:") == 1 and text.count(str(check.output)) == 1
    assert ".log" not in text and " | step " not in text and "\r" not in text
    lines = [line for line in text.splitlines() if len(line.split("|")) == 8]
    assert (
        len({tuple(i for i, char in enumerate(line) if char == "|") for line in lines})
        == 1
    )


@pytest.mark.parametrize("prefix", ["\u2139", "#"])
def test_output_node_totals_read_report_not_pass_count(prefix):
    stats = dict(tests=5, suites=0, passed=2, fail=1, cancelled=0, skipped=2, todo=0)
    text = "\n".join(
        f"{prefix} {'pass' if key == 'passed' else key} {value}"
        for key, value in stats.items()
    )
    assert node_totals(text) == dict(
        done=5, total=5, counts={"PASS": 2, "FAIL": 1, "SKIP": 2}
    )
    assert node_totals(f"{prefix} tests 5\n{prefix} pass 2\n") is None


@pytest.mark.parametrize("name", ["lint", "format"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_output_aux_done_exit_code(tmp_path, capsys, name, exit_code):
    check = Check(args(tmp_path))
    command = [sys.executable, "-c", f"raise SystemExit({exit_code})"]
    if exit_code:
        with pytest.raises(RuntimeError, match="exited 7"):
            check.step(name, command)
    else:
        assert check.step(name, command)["exitCode"] == 0
    rows = [row for row in table_records(capsys.readouterr().out) if row[2] == name]
    status = "FAIL" if exit_code else "PASS"
    assert [(row[0], row[3]) for row in rows] == [("RUN", "0/1"), (status, "1/1")]
    assert rows[-1][4:7] == (["0", "1", "0"] if exit_code else ["1", "0", "0"])


def test_output_js_support_summary_without_individual_events(tmp_path, capsys):
    check = Check(args(tmp_path))
    text = "# tests 5\n# pass 2\n# fail 1\n# cancelled 0\n# skipped 2\n# todo 0\n"
    check.show_step("js-support", text, None, dict(exitCode=1, durationSeconds=0.5))
    groups = check.output_groups["direct"]
    assert len(groups) == 1 and groups[0]["kind"] == "node test"
    assert groups[0]["done"] == groups[0]["total"] == 5
    record = table_records(capsys.readouterr().out)[0]
    assert record[0] == "FAIL" and record[3:7] == ["5/5", "2", "1", "2"]


def test_output_js_support_without_summary_has_no_fabricated_total(tmp_path, capsys):
    check = Check(args(tmp_path))
    check.show_step(
        "js-support",
        "\u2714 helper (12.5ms)\n",
        None,
        dict(exitCode=0, durationSeconds=0.1),
    )
    record = table_records(capsys.readouterr().out)[0]
    assert record[3] == "—" and "total" not in check.output_groups["direct"][0]
