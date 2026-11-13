"""P3 Windows demo/check CLI. Run with this checkout's Python 3.14."""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
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
SENSITIVE = re.compile(
    r"^(?:token|ticket|password|key|keys|secret|authorization|x-connect-session)$", re.I
)


def public_text(value):
    value = re.sub(
        r"(\b(?:token|ticket|password|key|authorization)\b[\s\"\x27]*[:=]\s*)(?:\"[^\"]*\"|\x27[^\x27]*\x27|[^\s,}]+)",
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
            securityV2="draft; not implemented",
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

    def step(self, name, command, *, cwd=ROOT, env=None, junit=None, required=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Overall check timeout reached")
        started = time.monotonic()
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
            raise
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
        (self.output / (name + ".log")).write_text(
            public_text(text)[-200000:], encoding="utf-8"
        )
        if timed_out:
            raise TimeoutError(f"Overall timeout during {name}")
        result = dict(
            name=name,
            exitCode=process.returncode,
            pid=process.pid,
            durationSeconds=round(time.monotonic() - started, 3),
        )
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
        result = dict(name=name, status="FAIL", reason="", steps=[])
        self.report["suites"].append(result)
        env = dict(
            os.environ,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONUTF8="1",
            CONNECT_PYTHON=sys.executable,
            CONNECT_REQUIRE_INTEGRATION="1",
        )
        try:
            if name == "independent":
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
                            "--ignore=tests/test_p1_files.py",
                            "--ignore=tests/test_p2_file_dependency.py",
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
                for source in sorted(
                    [
                        *ROOT.joinpath("tests").glob("*.js"),
                        *ROOT.joinpath("tests").glob("*.cjs"),
                        *ROOT.joinpath("web").rglob("*.js"),
                    ]
                ):
                    self.step("js-syntax", [node, "--check", str(source)], env=env)
                result["steps"].append(dict(name="js-syntax", status="PASS"))
            else:
                if name in REFERENCES:
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
                from tests.file_fixture import fixture

                folder = self.output / name
                with fixture(
                    name, folder, p1_root=self.args.p1_root, p2_root=self.args.p2_root
                ) as config:
                    env["CONNECT_TEST_OUTPUT"] = str(folder / "browser")
                    if name == "p2":
                        command = [
                            node,
                            "tests/browser-p2-live.cjs",
                            str(config["http"]),
                            str(config["tcp"]),
                        ]
                    else:
                        command = [
                            node,
                            "tests/browser-file-live.cjs",
                            "--config",
                            str(folder / "fixture.json"),
                            "--output",
                            str(folder / "browser"),
                            "--suite",
                            "ui" if name == "ui" else "files",
                        ]
                    result["steps"].append(
                        self.step(name + "-browser", command, env=env)
                    )
            result.update(status="PASS", reason="Selected checks completed")
        except (Exception, KeyboardInterrupt) as error:
            result["reason"] = public_text(str(error) or "Interrupted")
            self.cancelled = isinstance(error, KeyboardInterrupt)
        result["durationSeconds"] = round(time.monotonic() - started, 3)
        print(
            f"{name}: {result['status']} ({result['durationSeconds']}s) {result['reason']}",
            flush=True,
        )

    def run(self):
        selected = (
            {"independent", "ui", "p1", "p2"}
            if "all" in self.args.suite
            else set(self.args.suite)
        )
        for name in ("independent", "ui", "p1", "p2"):
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
        choices=["independent", "ui", "p1", "p2", "all"],
        default=["independent"],
    )
    check.add_argument("--output", type=Path, default=ROOT / "runtime/p3/checks")
    check.add_argument("--timeout", type=float, default=600)
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
            f"Chế độ mô phỏng: http://127.0.0.1:{server.server_port}/local-demo/",
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
