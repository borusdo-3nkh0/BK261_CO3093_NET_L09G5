"""Private pytest-to-check progress events; no verdict or report changes."""

import json
import os
import time
from collections import Counter
from pathlib import Path

from p3 import public

_path = None
_groups = {}
_indices = {}
_outcomes = {}


def _emit(event, **data):
    if _path:
        try:
            with _path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(public(dict(event=event, **data))) + "\n")
        except OSError:
            pass  # Progress transport must not change pytest results.


def pytest_configure(config):
    global _path
    value = os.environ.get("CONNECT_P3_PROGRESS")
    _path = Path(value) if value else None
    _groups.clear()
    _indices.clear()
    _outcomes.clear()


def pytest_collection_finish(session):
    for index, item in enumerate(session.items):
        _indices[item.nodeid] = index
    totals = Counter(item.nodeid.split("::")[0] for item in session.items)
    for name, total in totals.items():
        _groups[name] = dict(total=total, done=0, PASS=0, FAIL=0, SKIP=0, started=None)
    _emit("collected", groups=dict(totals))


def pytest_runtest_logstart(nodeid, location):
    name = nodeid.split("::")[0]
    group = _groups[name]
    if group["started"] is None:
        group["started"] = time.monotonic()
        _emit("start", group=name)


def pytest_runtest_logreport(report):
    if hasattr(report, "context") and not report.failed:
        return  # Subtests are not additional collected parent tests.
    status = "FAIL" if report.failed else "SKIP" if report.skipped else "PASS"
    previous = _outcomes.get(report.nodeid, ("PASS", ""))
    rank = {"PASS": 0, "SKIP": 1, "FAIL": 2}
    if rank[status] > rank[previous[0]] or (
        rank[status] == rank[previous[0]] and not previous[1]
    ):
        reason = ""
        if report.failed:
            lines = str(
                getattr(report.longrepr, "reprcrash", report.longrepr)
            ).splitlines()
            reason = lines[0] if lines else ""
        elif report.skipped:
            reason = str(
                report.longrepr[-1]
                if isinstance(report.longrepr, tuple)
                else report.longrepr
            )
        _outcomes[report.nodeid] = status, reason


def pytest_runtest_logfinish(nodeid, location):
    name = nodeid.split("::")[0]
    group = _groups[name]
    status, reason = _outcomes.pop(nodeid, ("PASS", ""))
    group["done"] += 1
    group[status] += 1
    elapsed = time.monotonic() - group["started"]
    _emit(
        "complete",
        group=name,
        index=_indices[nodeid],
        id=nodeid,
        status=status,
        reason=reason,
        elapsed=elapsed,
    )


def pytest_sessionfinish(session, exitstatus):
    for name, group in _groups.items():
        if group["started"] is not None and group["done"] < group["total"]:
            _emit("incomplete", group=name, elapsed=time.monotonic() - group["started"])
