"""P3 Windows demo/check CLI. Run with this checkout's Python 3.14."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from process_job import WindowsJob

ROOT = Path(__file__).resolve().parent
REFERENCES = {
    "p1": "b08572182705912b32b639ca3e8bc150265c4954",
    "p2": "fbf53eb35583ea9eabd9639acaf59fbab4675567",
}
INDEPENDENT = [
    "tests/test_bridge.py",
    "tests/test_file_bridge.py",
    "tests/test_payload.py",
    "tests/test_p3_cli.py",
]
SENSITIVE = re.compile(
    r"^(?:token|ticket|password|key|keys|c2s|s2c|secret|authorization|x-connect-session)$",
    re.I,
)


def public_text(value):
    value = re.sub(
        r"(\b(?:token|ticket|password|key|c2s|s2c|authorization)\b[\s\"\x27]*[:=]\s*)(?:\"[^\"]*\"|\x27[^\x27]*\x27|[^\s,}]+)",
        r"\1[REDACTED]",
        value,
        flags=re.I,
    )
    return re.sub(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}", "[REDACTED]", value)


def public(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if SENSITIVE.fullmatch(k) else public(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [public(v) for v in value]
    return public_text(value) if isinstance(value, str) else value


def write_report(path, value):
    path.write_text(
        json.dumps(public(value), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def stop_tree(process):
    """Only a Windows process tree created here; never discover unrelated PIDs."""
    if process.poll() is None:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def junit_counts(path, *, required=False):
    tree = ET.parse(path)
    cases = tree.findall(".//testcase")
    counts = dict(
        total=len(cases), skipped=sum(c.find("skipped") is not None for c in cases)
    )
    if required and (not cases or counts["skipped"] == counts["total"]):
        raise RuntimeError(
            "Required integration collected no executed tests (all skipped)"
        )
    return counts


SUITE_PURPOSE = {
    "independent": "Bridge/file/security unit tests, Ruff, JS helpers and syntax",
    "ui": "Official UI and local demo; browser assertions, no backend",
    "integrated": "Same-checkout P1/P2/P3: login, chat, online and real files",
    "security": "TLS certificates, AES-GCM, nonce/replay and secure browser flows",
    "p1": "Pinned P1 reference tests and file browser; not main acceptance",
    "p2": "Pinned P2 reference/fallback and chat browser; not main acceptance",
    "large": "Opt-in file size, hash, admission limit and cleanup",
    "load": "Opt-in concurrent clients, chat delivery and file/chat",
}


def measured(value):
    try:
        seconds = float(value)
        return f"{seconds:.3f}s" if math.isfinite(seconds) and seconds >= 0 else "-"
    except (TypeError, ValueError):
        return "-"


def output_line(value):
    return public_text(str(value)).splitlines()[0] if str(value).splitlines() else ""


def failure_reason(text, timed_out, exit_code):
    if timed_out:
        return "process timed out"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return next(
        (
            line
            for line in lines
            if re.search(
                r"\b(?:SyntaxError|TypeError|ReferenceError|AssertionError|Error)(?: \[[^]]+\])?:",
                line,
            )
        ),
        lines[0] if lines else f"process exited {exit_code}",
    )


def node_totals(text):
    stats = {}
    for match in re.finditer(
        r"^\s*[\u2139#]\s+(tests|pass|fail|cancelled|skipped|todo)\s+(\d+)\s*$",
        text,
        re.M,
    ):
        if match[1] == "tests":
            stats.clear()
        stats[match[1]] = int(match[2])
    outcomes = ("pass", "fail", "cancelled", "skipped", "todo")
    if not {"tests", *outcomes} <= stats.keys():
        return None
    done = sum(stats[name] for name in outcomes)
    if done > stats["tests"]:
        return None
    return dict(
        done=done,
        total=stats["tests"],
        counts={"PASS": stats["pass"], "FAIL": stats["fail"], "SKIP": stats["skipped"]},
    )


def output_row(kind, identity, status=None, seconds=None, reason="", *, counts=None):
    row = dict(kind=kind, id=identity, status=status, seconds=seconds, reason=reason)
    if counts is not None:
        row["counts"] = counts
    return row


def junit_rows(path):
    rows = {}
    for case in ET.parse(path).findall(".//testcase"):
        identity = (
            "::".join(filter(None, (case.get("classname"), case.get("name"))))
            or "unnamed JUnit testcase"
        )
        problem = next(
            (
                case.find(tag)
                for tag in ("failure", "error", "skipped")
                if case.find(tag) is not None
            ),
            None,
        )
        status = (
            "PASS"
            if problem is None
            else ("SKIP" if problem.tag == "skipped" else "FAIL")
        )
        reason = "" if problem is None else problem.get("message") or problem.text or ""
        row = output_row("pytest", identity, status, case.get("time"), reason)
        row["module"] = case.get("file") or case.get("classname") or "JUnit"
        if identity in rows:
            previous = rows[identity]
            # A call failure and teardown error may produce two records for one test.
            row["status"] = max(
                (previous["status"], status),
                key=lambda s: {"PASS": 0, "SKIP": 1, "FAIL": 2}[s],
            )
            row.update(
                seconds=None,
                reason=f"{output_line(previous['reason'])}; {output_line(reason)} (multiple JUnit records; see XML)",
            )
        rows[identity] = row
    return list(rows.values())


def browser_rows(data):
    """Only explicit report checks/verdicts are cases; UI checks are assertions."""
    rows = []
    for check in data.get("checks", []):
        if isinstance(check, str):
            rows.append(output_row("browser case", check, "PASS"))
    for group in data.get("regression", []):
        viewport = "x".join(map(str, group.get("viewport", [])))
        counts = [result.get("passed") for result in group.get("results", [])]
        rows.append(
            output_row(
                "browser assertions",
                f"UI {viewport}",
                "PASS"
                if counts and all(isinstance(n, int) for n in counts)
                else "RECORDED",
                counts={
                    "PASS": sum(counts)
                    if counts and all(isinstance(n, int) for n in counts)
                    else None
                },
            )
        )
    for group in data.get("demo", []):
        viewport = "x".join(map(str, group.get("viewport", [])))
        for name in ("smoke", "company"):
            if name in group:
                rows.append(
                    output_row(
                        "browser assertions",
                        f"demo {viewport} / {name}",
                        "PASS"
                        if isinstance(group[name].get("passed"), int)
                        else "RECORDED",
                        counts={"PASS": group[name].get("passed")},
                    )
                )
    for name, case in data.get("tcp", {}).items():
        verdict = case.get("verdict", "")
        status = next(
            (s for s in ("PASS", "FAIL", "SKIP") if verdict.startswith(s)), None
        )
        if status:
            rows.append(
                output_row(
                    "TCP case", name, status, case.get("durationSeconds"), verdict
                )
            )
    if "onlineUiChecks" in data:
        rows.append(
            output_row(
                "browser assertions",
                "Online presence and user search",
                counts={"PASS": data["onlineUiChecks"].get("passed")},
            )
        )
    return rows


def status_counts(rows):
    result = {}
    for row in rows:
        kind = row["kind"]
        counts = row.get(
            "counts", {s: int(row["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
        )
        if kind not in result:
            result[kind] = {s: 0 for s in ("PASS", "FAIL", "SKIP")}
        for status in result[kind]:
            value = counts.get(status)
            previous = result[kind][status]
            result[kind][status] = (
                previous + value
                if isinstance(value, int) and previous is not None
                else None
            )
    return result


def reference(kind, path):
    path = Path(path).resolve()
    required = "p1/client.py" if kind == "p1" else "server/socket_server.py"
    if not (path / required).is_file():
        raise RuntimeError(
            f"Missing {kind.upper()} checkout: {path}; configure --{kind}-root"
        )
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    revision = result.stdout.strip()
    if revision != REFERENCES[kind]:
        raise RuntimeError(
            f"{kind.upper()} revision {revision} differs from pinned {REFERENCES[kind]}"
        )
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    if status:
        raise RuntimeError(
            f"{kind.upper()} checkout has tracked changes; pinned source is not clean"
        )
    return dict(
        source="https://github.com/borusdo-3nkh0/BK261_CO3093_NET_L09G5",
        revision=revision,
        path=str(path),
    )


class Check:
    def __init__(self, args):
        self.args = args
        self.started = time.monotonic()
        self.deadline = self.started + args.timeout
        self.output = args.output.resolve() / ("check-" + uuid.uuid4().hex)
        self.output.mkdir(parents=True)
        self.report = dict(
            runId=self.output.name,
            startedAt=datetime.now(timezone.utc).isoformat(),
            python=sys.version,
            platform=sys.platform,
            securityV2="TLS + AES-GCM hop-by-hop; implemented",
            sources={},
            suites=[],
        )
        revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.report["sources"]["p3"] = dict(
            revision=revision.stdout.strip() or "unavailable",
            path=str(ROOT),
            trackedChanges=subprocess.run(
                ["git", "-C", str(ROOT), "diff", "--quiet", "HEAD"],
                capture_output=True,
                timeout=10,
            ).returncode
            != 0,
        )
        self.cancelled = False
        self.output_rows = {}
        self.output_groups = {}
        self.pytest_groups = {}
        self.active_suite = "direct"
        self.terminal = sys.stdout.isatty() and not os.environ.get("CI")
        self.progress_width = 0
        self.syntax_group = None
        group_width = max(
            32, *(len(path.stem) for path in (ROOT / "tests").glob("test_*.py"))
        )
        self.column_widths = (10, 18, group_width, 9, 5, 5, 5, 10)
        self.header_shown = False

    def detail(self, message):
        if not getattr(self.args, "quiet", False):
            if self.progress_width:
                print("\r" + " " * self.progress_width + "\r", end="", flush=True)
                self.progress_width = 0
            print(public_text(message), flush=True)

    def progress_line(self, group):
        final = group["status"] != "RUN"
        self.ensure_header()
        text = self.group_line(group)
        if self.terminal:
            print(
                "\r" + text.ljust(self.progress_width),
                end="\n" if final else "",
                flush=True,
            )
            self.progress_width = 0 if final else len(text)
        else:
            print(text, flush=True)

    def columns(self, values):
        cells = []
        for index, (value, width) in enumerate(zip(values, self.column_widths)):
            text = output_line(value)
            if index < 3 and len(text) > width:
                text = text[: width - 3] + "..."
            cells.append(text.ljust(width) if index < 3 else text.rjust(width))
        return " | ".join(cells)

    def ensure_header(self):
        if not self.header_shown:
            self.detail(
                self.columns(
                    ("STATUS", "TYPE", "GROUP", "DONE", "PASS", "FAIL", "SKIP", "TIME")
                )
            )
            self.header_shown = True

    def group_line(self, group):
        counts = group.get(
            "counts", {s: int(group["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
        )
        done = f"{group['done']}/{group['total']}" if "done" in group else "-"
        numbers = [
            str(counts.get(s)) if counts.get(s) is not None else "-"
            for s in ("PASS", "FAIL", "SKIP")
        ]
        elapsed = "-" if group["status"] == "RUN" else measured(group["seconds"])
        return self.columns(
            (
                group["status"] or "RECORDED",
                group["kind"],
                group["id"],
                done,
                *numbers,
                elapsed,
            )
        )

    def begin_syntax(self, sources):
        if getattr(self.args, "quiet", False):
            return
        self.syntax_group = dict(
            id="js-syntax",
            kind="syntax files",
            status="RUN",
            done=0,
            total=len(sources),
            files=list(sources),
            counts={s: 0 for s in ("PASS", "FAIL", "SKIP")},
            started=time.monotonic(),
            seconds=None,
            reason="",
            diagnosed=False,
        )
        self.output_groups.setdefault(self.active_suite, []).append(self.syntax_group)
        self.progress_line(self.syntax_group)

    def end_syntax(self, error=None):
        group = self.syntax_group
        if group is None:
            return
        group["seconds"] = time.monotonic() - group["started"]
        group["status"] = (
            "FAIL"
            if error or group["counts"]["FAIL"]
            else "PASS"
            if group["total"]
            else "SKIP"
        )
        if error and not group["diagnosed"]:
            source = (
                group["files"][min(group["done"], len(group["files"]) - 1)]
                if group["files"]
                else "js-syntax"
            )
            self.detail(
                f"  FAIL: {source} - {output_line(error).split('; see ', 1)[0]}"
            )
        self.progress_line(group)
        self.syntax_group = None

    def progress_event(self, step, event):
        groups = self.pytest_groups.setdefault((self.active_suite, step), {})
        if event["event"] == "collected":
            for name, total in event["groups"].items():
                groups[name] = dict(
                    id=Path(name).stem,
                    kind="pytest",
                    total=total,
                    done=0,
                    counts={s: 0 for s in ("PASS", "FAIL", "SKIP")},
                    status="RUN",
                    seconds=None,
                    reason="",
                    seen=set(),
                )
            return
        group = groups[event["group"]]
        if event["event"] == "start":
            self.progress_line(group)
        elif event["event"] == "complete":
            if event["index"] in group["seen"]:
                return
            group["seen"].add(event["index"])
            group["counts"][event["status"]] += 1
            group["done"] += 1
            if group["done"] == group["total"]:
                group["status"] = (
                    "FAIL"
                    if group["counts"]["FAIL"]
                    else "SKIP"
                    if group["counts"]["SKIP"] == group["total"]
                    else "PASS"
                )
                group["seconds"] = event["elapsed"]
            if event["status"] != "PASS":
                self.detail(
                    f"  {event['status']}: {output_line(event['id'])} - {output_line(event['reason'])}"
                )
            self.progress_line(group)
        elif event["event"] == "incomplete":
            group.update(status="INCOMPLETE", seconds=event["elapsed"])
            self.progress_line(group)

    def watch_progress(self, path, step, stop):
        try:
            with path.open(encoding="utf-8") as stream:
                pending = ""
                while True:
                    pending += stream.read()
                    lines = pending.split("\n")
                    pending = lines.pop()
                    for line in lines:
                        try:
                            self.progress_event(step, json.loads(line))
                        except (ValueError, KeyError, TypeError) as error:
                            self.detail(
                                f"  Progress event unavailable: {output_line(error)}"
                            )
                    if stop.is_set():
                        break
                    stop.wait(0.02)
        except OSError as error:
            self.detail(f"  Progress transport unavailable: {output_line(error)}")

    def finish_progress(self, step):
        for group in self.pytest_groups.get((self.active_suite, step), {}).values():
            if group["status"] == "RUN":
                group["status"] = "INCOMPLETE" if group["done"] else "NOT RUN"
                self.progress_line(group)

    def show_step(
        self, name, text, junit, result, *, timed_out=False, label=None, required=False
    ):
        if getattr(self.args, "quiet", False):
            return
        rows = []
        label = label or name
        if name == "js-syntax" and self.syntax_group is not None:
            group = self.syntax_group
            source = group["files"][group["done"]]
            failed = timed_out or result["exitCode"] != 0
            group["done"] += 1
            group["counts"]["FAIL" if failed else "PASS"] += 1
            if failed:
                reason = failure_reason(text, timed_out, result["exitCode"])
                self.detail(f"  FAIL: {source} - {output_line(reason)}")
                group["diagnosed"] = True
            elif group["done"] < group["total"]:
                self.progress_line(group)
            return
        if junit and not Path(junit).exists():
            self.detail(
                "  JUnit missing: individual test counts/times unavailable; see process log"
            )
        if junit and Path(junit).exists():
            rows.extend(junit_rows(junit))
            summary = next(
                (
                    line
                    for line in reversed(text.splitlines())
                    if re.search(r"\bin [\d.]+s", line)
                ),
                "",
            )
            subtests = re.findall(
                r"(\d+) subtests (passed|failed|skipped|xfailed)", summary
            )
            if subtests:
                counts = {"PASS": None, "FAIL": None, "SKIP": None}
                for number, status in subtests:
                    category = {
                        "passed": "PASS",
                        "failed": "FAIL",
                        "skipped": "SKIP",
                        "xfailed": "SKIP",
                    }[status]
                    counts[category] = (counts[category] or 0) + int(number)
                rows.append(
                    output_row(
                        "subtest",
                        "pytest log summary",
                        None,
                        None,
                        "Individual IDs/times not recorded in JUnit/log",
                        counts=counts,
                    )
                )
        elif name == "js-support":
            for match in re.finditer(
                r"^[\u2714\u2716\ufe63\uff0d] (.+) \(([\d.]+)ms\)", text, re.M
            ):
                rows.append(
                    output_row(
                        "node test",
                        match[1],
                        "PASS"
                        if match[0].startswith("\u2714")
                        else "FAIL"
                        if match[0].startswith("\u2716")
                        else "SKIP",
                        float(match[2]) / 1000,
                    )
                )
        elif name == "p1-reference":
            for match in re.finditer(
                r"^(test\S+ \(.+\)) \.\.\. (ok|FAIL|ERROR|skipped.*)$", text, re.M
            ):
                rows.append(
                    output_row(
                        "unittest",
                        match[1],
                        "PASS"
                        if match[2] == "ok"
                        else "SKIP"
                        if match[2].startswith("skipped")
                        else "FAIL",
                        None,
                        match[2] if match[2] != "ok" else "",
                    )
                )
        if name == "load-clients":
            for path in sorted((self.output / "load").rglob("results.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                for case_id, cases in data.get("cases", {}).items():
                    for index, case in enumerate(
                        cases if isinstance(cases, list) else [cases]
                    ):
                        status = {
                            "Đạt": "PASS",
                            "Không đạt": "FAIL",
                            "Chưa chạy": "SKIP",
                        }.get(case.get("verdict"))
                        if status:
                            identity = (
                                f"{case_id}[{index}]"
                                if isinstance(cases, list)
                                else case_id
                            )
                            rows.append(
                                output_row(
                                    "system case",
                                    identity,
                                    status,
                                    case.get("elapsedSeconds"),
                                    case.get("reason", case.get("error", "")),
                                )
                            )
        if name.endswith("-browser"):
            folder = self.output / self.active_suite
            reports = []
            completed = False
            for path in sorted(folder.rglob("*.json")):
                if path.name not in {
                    "report.json",
                    "results.json",
                } and not path.name.endswith("-failure.json"):
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("status") not in {
                    "PASS",
                    "FAIL",
                    "SKIP",
                }:
                    continue
                reports.append(data)
                completed = completed or path.name in {"report.json", "results.json"}
                rows.extend(browser_rows(data))
            failed = timed_out or result["exitCode"] != 0
            status = (
                "FAIL"
                if failed or any(data["status"] == "FAIL" for data in reports)
                else "SKIP"
                if reports and all(data["status"] == "SKIP" for data in reports)
                else "PASS"
                if reports
                else "RECORDED"
            )
            run = output_row(
                "browser run",
                name,
                status,
                result["durationSeconds"],
                "process timed out"
                if timed_out
                else next((data["error"] for data in reports if data.get("error")), "")
                or (failure_reason(text, False, result["exitCode"]) if failed else ""),
            )
            # A final report is the completion marker; a crash/partial failure dump is not.
            if (
                completed
                and not timed_out
                and (
                    result["exitCode"] == 0
                    or result["exitCode"] == 1
                    and any(data["status"] == "FAIL" for data in reports)
                )
            ):
                run.update(done=1, total=1)
            rows.append(run)
            if not reports:
                self.detail(
                    "  Browser: no readable result report; per-case counts/times unavailable"
                )
        node = node_totals(text) if name == "js-support" else None
        failed = timed_out or result["exitCode"] != 0
        if required and junit and Path(junit).exists():
            parents = [row for row in rows if row["kind"] == "pytest"]
            failed = failed or not any(row["status"] != "SKIP" for row in parents)
        if not rows and not junit and not name.endswith("-browser") and node is None:
            rows.append(
                output_row(
                    "runner check",
                    label,
                    "FAIL" if failed else "PASS",
                    result["durationSeconds"],
                    failure_reason(text, timed_out, result["exitCode"])
                    if failed
                    else "",
                )
            )
        self.output_rows.setdefault(self.active_suite, []).extend(rows)
        groups = []
        live = self.pytest_groups.get((self.active_suite, name), {})
        if junit:
            groups.extend(live.values())
            if not live:
                modules = {}
                for row in rows:
                    if row["kind"] == "pytest":
                        modules.setdefault(row["module"], []).append(row)
                        if row["status"] != "PASS":
                            self.detail(
                                f"  {row['status']}: {output_line(row['id'])} - {output_line(row['reason'])}"
                            )
                for module, cases in modules.items():
                    counts = status_counts(cases)["pytest"]
                    status = (
                        "FAIL"
                        if counts["FAIL"]
                        else "SKIP"
                        if counts["SKIP"] == len(cases)
                        else "PASS"
                    )
                    groups.append(
                        output_row(
                            "pytest",
                            Path(module).stem,
                            status,
                            counts=counts,
                            reason="No live collection/group timer available",
                        )
                    )
        for kind in ("node test", "unittest"):
            cases = [row for row in rows if row["kind"] == kind]
            if cases or (kind == "node test" and node is not None):
                group = output_row(
                    kind,
                    name,
                    "FAIL" if failed else "PASS",
                    result["durationSeconds"],
                    failure_reason(text, timed_out, result["exitCode"])
                    if failed
                    else "",
                    counts=node["counts"]
                    if kind == "node test" and node is not None
                    else status_counts(cases)[kind],
                )
                if kind == "node test" and node is not None:
                    group.update(done=node["done"], total=node["total"])
                groups.append(group)
                for row in cases:
                    if row["status"] != "PASS":
                        self.detail(
                            f"  {row['status']}: {output_line(row['id'])} - {output_line(row['reason']) or 'Reason not recorded; see report'}"
                        )
        groups.extend(
            row
            for row in rows
            if row["kind"] not in {"pytest", "node test", "unittest", "subtest"}
        )
        if name in {"lint", "format"}:
            for group in groups:
                group.update(done=1, total=1)
        self.output_groups.setdefault(self.active_suite, []).extend(groups)
        for group in groups:
            if not (live and group["kind"] == "pytest"):
                self.ensure_header()
                self.detail(self.group_line(group))
                if group.get("reason") and group["status"] in {"FAIL", "SKIP"}:
                    self.detail(
                        f"    {output_line(group['reason']).split('; see ', 1)[0]}"
                    )

    def summary(self):
        if getattr(self.args, "quiet", False):
            return
        self.detail("\nSUMMARY - pytest tests / browser assertions stay separate")
        self.detail(
            self.columns(
                ("STATUS", "TYPE", "GROUP", "DONE", "PASS", "FAIL", "SKIP", "TIME")
            )
        )
        not_selected = []
        for suite in self.report["suites"]:
            if suite.get("reason") == "Not selected":
                not_selected.append(suite["name"])
                continue
            groups = self.output_groups.get(suite["name"], [])
            if not groups:
                groups = [
                    output_row(
                        "suite",
                        suite["name"],
                        suite["status"],
                        suite.get("durationSeconds"),
                        counts={},
                    )
                ]
            self.detail(f"[{suite['name']}]")
            for group in groups:
                self.detail(self.group_line(group))
            subtests = [
                row
                for row in self.output_rows.get(suite["name"], [])
                if row["kind"] == "subtest"
            ]
            if subtests:
                self.detail(
                    "  "
                    + "; ".join(
                        f"{sum(row['counts'].get(status) or 0 for row in subtests)} subtest {label}"
                        for status, label in (
                            ("PASS", "passed"),
                            ("FAIL", "failed"),
                            ("SKIP", "skipped"),
                        )
                        if any(
                            row["counts"].get(status) is not None for row in subtests
                        )
                    )
                )
            if suite.get("status") == "FAIL":
                self.detail(
                    f"  FAIL: {output_line(suite.get('reason', '')).split('; see ', 1)[0]}"
                )
        if not_selected:
            self.detail("Not selected: " + ", ".join(not_selected))
        self.detail(
            f"Total: {self.report['status']}; elapsed {measured(self.report['durationSeconds'])}"
        )
        self.detail("- = not applicable or not recorded separately")

    def step(self, name, command, *, cwd=ROOT, env=None, junit=None, required=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Overall check timeout reached")
        started = time.monotonic()
        label = name
        if name.endswith("-browser"):
            self.ensure_header()
            self.detail(
                self.group_line(output_row("browser run", name, "RUN", counts={}))
            )
        elif name in {"lint", "format", "js-support"} and not getattr(
            self.args, "quiet", False
        ):
            group = output_row(
                "node test" if name == "js-support" else "runner check",
                name,
                "RUN",
                counts={}
                if name == "js-support"
                else {s: 0 for s in ("PASS", "FAIL", "SKIP")},
            )
            if name != "js-support":
                group.update(done=0, total=1)
            self.progress_line(group)
        elif name not in {"lint", "format", "js-support", "js-syntax"} and not junit:
            self.detail(f"  RUN {label}")
        progress_path = None
        stop_progress = threading.Event()
        watcher = None
        if junit and "pytest" in command and not getattr(self.args, "quiet", False):
            progress_path = self.output / (uuid.uuid4().hex + ".events")
            progress_path.touch()
            env = dict(os.environ if env is None else env)
            env["CONNECT_P3_PROGRESS"] = str(progress_path)
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            command = list(command)
            index = command.index("pytest") + 1
            command[index:index] = ["-p", "p3_progress"]
        job = WindowsJob()
        try:
            process = subprocess.Popen(
                job.command(command),
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except BaseException:
            job.close()
            if progress_path:
                progress_path.unlink(missing_ok=True)
            raise
        if progress_path:
            watcher = threading.Thread(
                target=self.watch_progress,
                args=(progress_path, name, stop_progress),
                daemon=True,
            )
            watcher.start()
        timed_out = False
        try:
            text, _ = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            stop_tree(process)
            text, _ = process.communicate(timeout=5)
            timed_out = True
        finally:
            try:
                if process.poll() is None:
                    stop_tree(process)
            finally:
                job.close()
                if watcher:
                    stop_progress.set()
                    watcher.join(timeout=2)
                    self.finish_progress(name)
                    try:
                        progress_path.unlink(missing_ok=True)
                    except OSError:
                        self.detail(
                            "  Progress file cleanup pending; see local runtime"
                        )
        (self.output / (name + ".log")).write_text(
            public_text(text)[-200000:], encoding="utf-8"
        )
        result = dict(
            name=name,
            exitCode=process.returncode,
            pid=process.pid,
            durationSeconds=round(time.monotonic() - started, 3),
        )
        # Console rendering is observational; it must not change verdicts or report schema.
        try:
            self.show_step(
                name,
                text,
                junit,
                result,
                timed_out=timed_out,
                label=label,
                required=required,
            )
        except (
            ValueError,
            OSError,
            ET.ParseError,
            TypeError,
            KeyError,
            AttributeError,
        ) as error:
            self.detail(
                f"  Output detail unavailable: {output_line(error)}; see log/JUnit"
            )
        if timed_out:
            self.detail(f"  FAIL {name}: timeout; tests/groups may be incomplete")
            raise TimeoutError(f"Overall timeout during {name}")
        if junit and Path(junit).exists():
            result["tests"] = junit_counts(junit, required=required)
            Path(junit).write_text(
                public_text(Path(junit).read_text(encoding="utf-8")), encoding="utf-8"
            )
        if process.returncode:
            raise RuntimeError(f"{name} exited {process.returncode}; see {name}.log")
        return result

    def suite(self, name):
        started = time.monotonic()
        self.active_suite = name
        self.detail(f"\nSUITE {name} - {SUITE_PURPOSE[name]}")
        result = dict(name=name, status="FAIL", reason="", steps=[])
        self.report["suites"].append(result)
        env = dict(
            os.environ,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONUTF8="1",
            CONNECT_PYTHON=sys.executable,
            CONNECT_REQUIRE_INTEGRATION="1",
        )
        env.pop("CONNECT_REFERENCE_SUITE", None)
        try:
            if name == "security":
                self.report["sources"]["security"] = dict(
                    self.report["sources"]["p3"],
                    mode="same checkout P1/P2/P3; HTTPS/TLS + AES-GCM; real tickets",
                )
                junit = self.output / "security.xml"
                result["steps"].append(
                    self.step(
                        "security-python",
                        [
                            sys.executable,
                            "-B",
                            "-m",
                            "pytest",
                            "-q",
                            "tests/test_security_context.py",
                            "tests/test_security_live.py",
                            f"--junitxml={junit}",
                        ],
                        env=env,
                        junit=junit,
                        required=True,
                    )
                )
                result["steps"].append(
                    self.step(
                        "security-browser",
                        [
                            sys.executable,
                            "-B",
                            "tests/file_fixture.py",
                            "--security-browser",
                            "--output",
                            str(self.output / "security"),
                        ],
                        env=env,
                    )
                )
            elif name == "independent":
                junit = self.output / "independent.xml"
                result["steps"].append(
                    self.step(
                        "python",
                        [
                            sys.executable,
                            "-B",
                            "-m",
                            "pytest",
                            "-q",
                            *INDEPENDENT,
                            f"--junitxml={junit}",
                        ],
                        env=env,
                        junit=junit,
                    )
                )
                for command, suffix in (
                    (["check", "."], "lint"),
                    (["format", "--check", "."], "format"),
                ):
                    result["steps"].append(
                        self.step(
                            suffix, [sys.executable, "-m", "ruff", *command], env=env
                        )
                    )
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("Node 24+ is required for JavaScript checks")
                result["steps"].append(
                    self.step(
                        "js-support",
                        [node, "--test", "tests/browser-support.test.cjs"],
                        env=env,
                    )
                )
                sources = sorted(
                    [
                        *ROOT.joinpath("tests").glob("*.js"),
                        *ROOT.joinpath("tests").glob("*.cjs"),
                        *ROOT.joinpath("web").rglob("*.js"),
                    ]
                )
                self.begin_syntax(sources)
                try:
                    for source in sources:
                        self.step("js-syntax", [node, "--check", str(source)], env=env)
                finally:
                    self.end_syntax(sys.exc_info()[1])
                result["steps"].append(dict(name="js-syntax", status="PASS"))
            elif name in {"integrated", "large", "load"}:
                env.update(CONNECT_P1_ROOT=str(ROOT), CONNECT_P2_ROOT=str(ROOT))
                self.report["sources"]["integrated"] = dict(
                    self.report["sources"]["p3"],
                    backend="same checkout P1/P2/P3; TLS/AES-GCM; real P2 tickets",
                    modules={
                        str(path): {
                            "path": str(ROOT / path),
                            "sha256": hashlib.sha256(
                                (ROOT / path).read_bytes()
                            ).hexdigest(),
                        }
                        for path in map(
                            Path,
                            (
                                "p1/client.py",
                                "p1/relay.py",
                                "shared/protocol.py",
                                "server/socket_server.py",
                                "bridge.py",
                                "bridge_files.py",
                            ),
                        )
                    },
                )
                if name == "load":
                    result["steps"].append(
                        self.step(
                            "load-clients",
                            [
                                sys.executable,
                                "-B",
                                "tests/p2_load_check.py",
                                "--source",
                                str(ROOT),
                                "--output",
                                str(self.output / "load"),
                            ],
                            env=env,
                        )
                    )
                    selection = ["tests/test_integrated_edges.py", "-m", "load"]
                elif name == "large":
                    env["CONNECT_LARGE_MIB"] = str(self.args.file_mib)
                    selection = ["tests/test_integrated_edges.py", "-m", "large"]
                else:
                    selection = [
                        "tests",
                        "--ignore=tests/test_p1_files.py",
                        "--ignore=tests/test_p2_file_dependency.py",
                        "--ignore=tests/test_security_context.py",
                        "--ignore=tests/test_security_live.py",
                        *("--ignore=" + path for path in INDEPENDENT),
                        "-m",
                        "not large and not load",
                    ]
                junit = self.output / (name + ".xml")
                result["steps"].append(
                    self.step(
                        name + "-python",
                        [
                            sys.executable,
                            "-B",
                            "-m",
                            "pytest",
                            "-q",
                            *selection,
                            f"--basetemp={self.output / (name + '-tmp')}",
                            f"--junitxml={junit}",
                        ],
                        env=env,
                        junit=junit,
                        required=True,
                    )
                )
                if name == "integrated":
                    result["steps"].append(
                        self.step(
                            "integrated-browser",
                            [
                                sys.executable,
                                "-B",
                                "tests/file_fixture.py",
                                "--backend",
                                "integrated",
                                "--output",
                                str(self.output / "integrated"),
                                "--run-browser",
                            ],
                            env=env,
                        )
                    )
            else:
                if name in REFERENCES:
                    env["CONNECT_REFERENCE_SUITE"] = name
                    self.report["sources"][name] = reference(
                        name, getattr(self.args, name + "_root")
                    )
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("Node 24+ and Chrome/Chromium are required")
                if name in REFERENCES:
                    path = getattr(self.args, name + "_root")
                    env["CONNECT_" + name.upper() + "_ROOT"] = str(path.resolve())
                    junit = self.output / (name + ".xml")
                    file = (
                        "test_p1_files.py"
                        if name == "p1"
                        else "test_p2_file_dependency.py"
                    )
                    result["steps"].append(
                        self.step(
                            name + "-python",
                            [
                                sys.executable,
                                "-B",
                                "-m",
                                "pytest",
                                "-q",
                                "tests/" + file,
                                f"--junitxml={junit}",
                            ],
                            env=env,
                            junit=junit,
                            required=True,
                        )
                    )
                    if name == "p1":
                        result["steps"].append(
                            self.step(
                                "p1-reference",
                                [
                                    sys.executable,
                                    "-B",
                                    "-m",
                                    "unittest",
                                    "discover",
                                    "-s",
                                    "tests",
                                    "-v",
                                ],
                                cwd=path,
                                env=env,
                            )
                        )
                folder = self.output / name
                command = [
                    sys.executable,
                    "-B",
                    "tests/file_fixture.py",
                    "--backend",
                    name,
                    "--output",
                    str(folder),
                    "--run-browser",
                ]
                if name in REFERENCES:
                    command += ["--" + name + "-root", str(path.resolve())]
                result["steps"].append(self.step(name + "-browser", command, env=env))
            result.update(status="PASS", reason="Selected checks completed")
        except (Exception, KeyboardInterrupt) as error:
            result["reason"] = public_text(str(error) or "Interrupted")
            self.cancelled = isinstance(error, KeyboardInterrupt)
        try:
            staging = self.output / (name + "-tmp")
            assert staging.resolve().is_relative_to(self.output)
            if staging.exists():
                shutil.rmtree(staging)
        except OSError as error:
            result.update(
                status="FAIL", reason="Owned test staging cleanup failed: " + str(error)
            )
        result["durationSeconds"] = round(time.monotonic() - started, 3)
        print(
            f"{name}: {result['status']} ({result['durationSeconds']}s) {output_line(result['reason']).split('; see ', 1)[0]}",
            flush=True,
        )

    def run(self):
        selected = set(self.args.suite)
        if "all" in selected:
            selected = (selected - {"all"}) | {
                "independent",
                "ui",
                "integrated",
                "security",
            }
        for name in (
            "independent",
            "ui",
            "integrated",
            "security",
            "p1",
            "p2",
            "large",
            "load",
        ):
            if name in selected and not self.cancelled:
                self.suite(name)
            else:
                self.report["suites"].append(
                    dict(
                        name=name,
                        status="SKIP",
                        durationSeconds=0,
                        reason="Interrupted" if self.cancelled else "Not selected",
                    )
                )
                if getattr(self.args, "quiet", False):
                    print(
                        f"{name}: SKIP (0s) {self.report['suites'][-1]['reason']}",
                        flush=True,
                    )
        self.report["durationSeconds"] = round(time.monotonic() - self.started, 3)
        json_files = list(self.output.rglob("*.json"))
        try:
            for artifact in json_files:
                data = json.loads(artifact.read_text(encoding="utf-8"))
                if public(data) != data:
                    write_report(artifact, data)
                    raise ValueError(
                        f"Unsafe report fields: {artifact.relative_to(self.output)}"
                    )
            self.report["artifactAudit"] = dict(
                status="PASS", jsonFiles=len(json_files)
            )
        except ValueError as error:
            self.report["artifactAudit"] = dict(status="FAIL", reason=str(error))
            self.report["suites"].append(
                dict(
                    name="artifact-audit",
                    status="FAIL",
                    reason=str(error),
                    durationSeconds=0,
                )
            )
        self.report["status"] = (
            "FAIL"
            if any(s["status"] == "FAIL" for s in self.report["suites"])
            else "PASS"
        )
        write_report(self.output / "report.json", self.report)
        self.summary()
        print("Report:", self.output / "report.json", flush=True)
        return int(self.report["status"] != "PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check", help="Run selected suites; missing integration dependencies fail"
    )
    check.add_argument(
        "--suite",
        nargs="+",
        choices=[
            "independent",
            "ui",
            "integrated",
            "security",
            "p1",
            "p2",
            "large",
            "load",
            "all",
        ],
        default=["all"],
    )
    check.add_argument("--output", type=Path, default=ROOT / "runtime/p3/checks")
    check.add_argument(
        "--quiet", action="store_true", help="Only suite status lines and report path"
    )
    check.add_argument("--timeout", type=float, default=600)
    check.add_argument("--file-mib", type=int, choices=[32, 256], default=32)
    for name in REFERENCES:
        check.add_argument(
            "--" + name + "-root",
            type=Path,
            default=Path(
                os.environ.get(
                    "CONNECT_" + name.upper() + "_ROOT",
                    ROOT.parent.parent / ("MMT-" + name.upper()) / "A1_Client-Server",
                )
            ),
        )
    demo = commands.add_parser(
        "demo", help="Serve simulation only; never starts P2 or provisions tickets"
    )
    demo.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "check":
        args.output = args.output.resolve()
        args.p1_root = args.p1_root.resolve()
        args.p2_root = args.p2_root.resolve()
    os.chdir(ROOT)
    if args.command == "check":
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            parser.error("--timeout must be positive and finite")
        return Check(args).run()
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    with ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        partial(SimpleHTTPRequestHandler, directory=str(ROOT / "web")),
    ) as server:
        print(
            f"Simulation mode: http://127.0.0.1:{server.server_port}/local-demo/",
            flush=True,
        )
        print("No real backend, tickets or file bytes. Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
