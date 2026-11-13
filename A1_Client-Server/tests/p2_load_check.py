"""IT12/IT11 against one owned P2 process; no changes to the P2 checkout."""

import argparse
import ctypes
import hashlib
import inspect
import json
import logging
import multiprocessing as mp
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "runtime/reviews/it11-it12-2026-11-08"
P2 = Path(os.environ.get("CONNECT_P2_ROOT", ROOT)).resolve()
WAIT = 10
QUIET = 10


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def rss():
    if os.name != "nt":
        return {"workingSetBytes": None, "peakWorkingSetBytes": None}
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak",
                "working",
                "peakPaged",
                "paged",
                "peakNonPaged",
                "nonPaged",
                "pagefile",
                "peakPagefile",
            )
        ]

    kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return {"workingSetBytes": None, "peakWorkingSetBytes": None}
    return {"workingSetBytes": counters.working, "peakWorkingSetBytes": counters.peak}


def serve(pipe, source, log_file):
    sys.dont_write_bytecode = True
    sys.path.insert(0, source)
    from server.socket_server import SocketServer

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    options = (
        {"udp_port": 0}
        if "udp_port" in inspect.signature(SocketServer).parameters
        else {}
    )
    if os.environ.get("CONNECT_TEST_CA"):
        from security.tls import server_context

        certs = Path(os.environ["CONNECT_TEST_CA"]).parent
        options["tls_context"] = server_context(
            certs / "server.pem", certs / "server.key"
        )
    server = SocketServer(host="127.0.0.1", port=0, **options)
    thread = threading.Thread(target=server.start)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while True:
            sock = server.server_socket
            if sock and sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
                break
            require(
                thread.is_alive() and time.monotonic() < deadline,
                "Owned P2 did not become ready",
            )
            time.sleep(0.01)
        pipe.send(
            {
                "pid": os.getpid(),
                "port": sock.getsockname()[1],
                "udpPort": server.file_relay.address[1]
                if hasattr(server, "file_relay")
                else None,
                "sourceFile": str(
                    Path(sys.modules[SocketServer.__module__].__file__).resolve()
                ),
                "config": {
                    "host": server.host,
                    "max_clients": server.max_clients,
                    "handshake_timeout": server.handshake_timeout,
                    "idle_timeout": server.idle_timeout,
                    "backlogFromSource": 5,
                },
            }
        )
        while True:
            command = pipe.recv()
            if command == "stop":
                break
            require(command == "snapshot", "Unknown observer command")
            names = server.message_router.get_online_users()
            with server.clients_lock:
                sockets = len(server.client_sockets)
                workers = sum(worker.is_alive() for worker in server.client_threads)
            pipe.send(
                {
                    "atNs": time.monotonic_ns(),
                    "cpuSeconds": time.process_time(),
                    **rss(),
                    "sockets": sockets,
                    "workerThreads": workers,
                    "sessions": {
                        name: server.session_manager.get_session(name) for name in names
                    },
                    "serverAlive": thread.is_alive(),
                }
            )
    finally:
        server.stop()
        thread.join(5)
        pipe.close()
        require(not thread.is_alive(), "Owned server thread did not stop")


class Wire:
    def __init__(self, port, timeout):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.crypto, self.username = None, None
        ca = os.environ.get("CONNECT_TEST_CA")
        if ca:
            from security.tls import client_context

            self.sock = client_context(ca).wrap_socket(
                self.sock, server_hostname="127.0.0.1"
            )
        self.sock.settimeout(timeout)
        self.buffer = b""
        self.local_port = self.sock.getsockname()[1]
        self.sock.sendall(b"HELLO2\n" if ca else b"HELLO\n")
        require(self.read() == "WELCOME", "Missing WELCOME")

    def read(self):
        while b"\n" not in self.buffer:
            data = self.sock.recv(4096)
            if not data:
                raise EOFError("TCP EOF")
            self.buffer += data
            require(len(self.buffer) < 131072, "Unexpected response size")
        line, self.buffer = self.buffer.split(b"\n", 1)
        if line in {b"WELCOME", b"WELCOME2"}:
            return "WELCOME"
        packet = json.loads(line)
        if packet.get("type") in {"BROADCAST", "UNICAST"} and self.crypto:
            from security.context import chat_aad

            packet["message"] = self.crypto.decrypt_text(
                packet["message"],
                chat_aad(packet["type"], packet["sender"], packet.get("recipient")),
            )
        return packet

    def send(self, packet):
        if packet.get("action") in {"BROADCAST", "UNICAST"} and self.crypto:
            from security.context import chat_aad

            packet = dict(
                packet,
                message=self.crypto.encrypt_text(
                    packet["message"],
                    chat_aad(packet["action"], self.username, packet.get("recipient")),
                ),
            )
        self.sock.sendall((json.dumps(packet, ensure_ascii=False) + "\n").encode())

    def auth(self, action, username, password):
        self.send({"action": action, "username": username, "password": password})
        response = self.read()
        require(
            response.get("status") == action + "_SUCCESS",
            f"{action} did not succeed: {response.get('status')}",
        )
        if action == "LOGIN" and os.environ.get("CONNECT_TEST_CA"):
            from security.context import Context

            self.crypto, self.username = Context(response["security"]), username


def client(pipe, gate, port, username, password, timeout):
    wire = None
    reader = None
    closing = threading.Event()
    lock = threading.Lock()
    records, acks, errors, sends, endpoints = [], [], [], [], []
    online = []
    phase = "login"

    def receive():
        nonlocal online
        try:
            while not closing.is_set():
                packet = wire.read()
                with lock:
                    if packet.get("type") == "BROADCAST":
                        records.append(
                            {
                                "sender": packet.get("sender"),
                                "text": packet.get("message"),
                                "receivedAtNs": time.monotonic_ns(),
                            }
                        )
                    elif packet.get("status") == "LIST_ONLINE_SUCCESS":
                        online = packet["users"]
                    elif packet.get("status") == "BROADCAST_SUCCESS":
                        acks.append({"phase": phase, "atNs": time.monotonic_ns()})
                    else:
                        errors.append("Unexpected packet: " + json.dumps(packet))
        except (OSError, ValueError, EOFError) as exc:
            if not closing.is_set():
                with lock:
                    errors.append(type(exc).__name__ + ": " + str(exc))

    def open_wire(register):
        nonlocal wire, reader
        wire = Wire(port, timeout)
        if register:
            wire.auth("REGISTER", username, password)
        wire.auth("LOGIN", username, password)
        endpoints.append(wire.local_port)
        closing.clear()
        reader = threading.Thread(target=receive)
        reader.start()

    def close_wire():
        if wire and wire.sock.fileno() >= 0:
            closing.set()
            try:
                wire.sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            if reader:
                reader.join(2)
            wire.sock.close()
            if reader:
                reader.join(2)

    def snapshot():
        with lock:
            return {
                "username": username,
                "pid": os.getpid(),
                "endpoints": list(endpoints),
                "records": list(records),
                "acks": list(acks),
                "errors": list(errors),
                "sends": list(sends),
            }

    try:
        pipe.send({"ready": True, "pid": os.getpid()})
        gate.wait()
        try:
            open_wire(True)
            pipe.send({"loggedIn": True, "pid": os.getpid(), "port": wire.local_port})
        except (OSError, ValueError, EOFError, AssertionError) as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
            pipe.send({"loggedIn": False, "error": errors[-1], "pid": os.getpid()})
        while True:
            command = pipe.recv()
            op = command["op"]
            if op == "stats":
                pipe.send(snapshot())
            elif op == "online":
                wire.send({"action": "LIST_ONLINE"})
                deadline = time.monotonic() + timeout
                while not online and time.monotonic() < deadline:
                    time.sleep(0.02)
                pipe.send({"users": list(online)})
            elif op == "arm":
                phase = command["phase"]
                pipe.send({"armed": phase})
            elif op == "send":
                gate.wait()
                for index in range(1, command["count"] + 1):
                    text = f"{phase}/{username}/{index}"
                    try:
                        at = time.monotonic_ns()
                        wire.send({"action": "BROADCAST", "message": text})
                        with lock:
                            sends.append({"phase": phase, "text": text, "sentAtNs": at})
                    except OSError as exc:
                        with lock:
                            errors.append(type(exc).__name__ + ": " + str(exc))
                        break
                    if index < command["count"]:
                        time.sleep(0.2)
                pipe.send({"submitted": True})
            elif op == "close":
                gate.wait()
                close_wire()
                pipe.send({"closed": True})
            elif op == "reconnect":
                gate.wait()
                try:
                    open_wire(False)
                    pipe.send({"loggedIn": True, "port": wire.local_port})
                except (OSError, ValueError, EOFError, AssertionError) as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
                    pipe.send({"loggedIn": False, "error": errors[-1]})
            elif op == "stop":
                break
            else:
                raise ValueError("Unknown client command")
    finally:
        close_wire()
        pipe.close()


def receive(pipe, timeout):
    require(pipe.poll(timeout), "Control channel timed out")
    return pipe.recv()


def exchange(pipes, command, timeout):
    for pipe in pipes:
        pipe.send(command)
    deadline = time.monotonic() + timeout
    return [receive(pipe, max(0, deadline - time.monotonic())) for pipe in pipes]


def observer(pipe):
    pipe.send("snapshot")
    return receive(pipe, WAIT)


def wait_registry(pipe, expected):
    deadline = time.monotonic() + WAIT
    while True:
        state = observer(pipe)
        if set(state["sessions"]) == set(expected) and state["sockets"] == len(
            expected
        ):
            return state
        require(time.monotonic() < deadline, "Registry/socket cleanup timed out")
        time.sleep(0.05)


def it12(pipe, port, prefix, password):
    wires, names, endpoints = [], [], {}
    result = {"verdict": "Không đạt", "trace": []}
    try:
        require(not observer(pipe)["sessions"], "IT12 requires an empty registry")
        for label in ("A", "B", "C"):
            name = f"{prefix}-it12-{label}"
            wire = Wire(port, WAIT)
            wires.append(wire)
            names.append(name)
            result["trace"].append(
                {
                    "client": label,
                    "pid": os.getpid(),
                    "port": wire.local_port,
                    "handshake": "WELCOME2/TLS"
                    if os.environ.get("CONNECT_TEST_CA")
                    else "WELCOME",
                }
            )
            wire.auth("REGISTER", name, password)
            wire.auth("LOGIN", name, password)
            endpoints[name] = wire.local_port
        state = wait_registry(pipe, names)
        result["registryBeforeLogout"] = state
        for name, active_port in endpoints.items():
            require(
                state["sessions"][name]
                == {
                    "username": name,
                    "ip": "127.0.0.1",
                    "port": active_port,
                    "status": "online",
                },
                "Registry endpoint/identity mismatch",
            )
        wires[0].sock.shutdown(socket.SHUT_WR)
        try:
            wires[0].read()
            raise AssertionError("Expected EOF after graceful close")
        except EOFError:
            pass
        wires[0].sock.close()
        result["registryAfterLogout"] = wait_registry(pipe, names[1:])
        text = prefix + "/IT12/B-to-C-after-A-exit"
        wires[1].send({"action": "UNICAST", "recipient": names[2], "message": text})
        require(wires[1].read() == {"status": "UNICAST_SUCCESS"}, "Canary ACK failed")
        require(
            wires[2].read()
            == {
                "type": "UNICAST",
                "sender": names[1],
                "recipient": names[2],
                "message": text,
            },
            "Canary routing failed",
        )
        result.update(
            verdict="Đạt",
            logins=3,
            registryEndpointsMatched=3,
            canaryDelivered=1,
            gracefulExit="TCP half-close/EOF; P2 has no LOGOUT action",
        )
    except (OSError, EOFError, ValueError, AssertionError) as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        for wire in wires:
            wire.sock.close()
        result["reset"] = wait_registry(pipe, [])
    return result


def evaluate(stats, phase, names, count):
    all_ids = {
        f"{phase}/{name}/{i}": name for name in names for i in range(1, count + 1)
    }
    sent_times = {
        row["text"]: row["sentAtNs"]
        for stat in stats
        for row in stat["sends"]
        if row["phase"] == phase
    }
    rows, latencies = [], []
    for stat in stats:
        expected = {
            text for text, sender in all_ids.items() if sender != stat["username"]
        }
        packets = [
            row for row in stat["records"] if row["text"].startswith(phase + "/")
        ]
        counts = Counter(row["text"] for row in packets)
        wrong = sum(
            row["text"] not in expected or all_ids.get(row["text"]) != row["sender"]
            for row in packets
        )
        for row in packets:
            if row["text"] in sent_times:
                latencies.append((row["receivedAtNs"] - sent_times[row["text"]]) / 1e6)
        rows.append(
            {
                "username": stat["username"],
                "pid": stat["pid"],
                "expected": len(expected),
                "raw": len(packets),
                "unique": len(counts),
                "missing": len(expected - counts.keys()),
                "duplicates": sum(max(0, n - 1) for n in counts.values()),
                "wrong": wrong,
                "acks": sum(row["phase"] == phase for row in stat["acks"]),
                "errors": list(stat["errors"]),
            }
        )
    latencies.sort()
    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            "expected",
            "raw",
            "unique",
            "missing",
            "duplicates",
            "wrong",
            "acks",
        )
    }
    return {
        "phase": phase,
        "sentExpected": len(all_ids),
        "sentActual": len(sent_times),
        "clients": rows,
        **totals,
        "latencyMs": {
            "samples": len(latencies),
            "max": max(latencies, default=None),
            "p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
            if latencies
            else None,
        },
    }


def workload(pipes, gate, names, count, phase, timeout, monitor):
    before = observer(monitor)
    gate.clear()
    exchange(pipes, {"op": "arm", "phase": phase}, WAIT)
    for pipe in pipes:
        pipe.send({"op": "send", "count": count})
    gate.set()
    deadline = time.monotonic() + timeout
    for pipe in pipes:
        receive(pipe, max(0, deadline - time.monotonic()))
    while True:
        stats = exchange(pipes, {"op": "stats"}, WAIT)
        result = evaluate(stats, phase, names, count)
        if result["raw"] >= result["expected"] and result["acks"] >= len(names) * count:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    time.sleep(QUIET)
    stats = exchange(pipes, {"op": "stats"}, WAIT)
    result = evaluate(stats, phase, names, count)
    after = observer(monitor)
    result.update(
        serverBefore=before,
        serverAfter=after,
        observerSeconds=QUIET,
        cpuSecondsDelta=after["cpuSeconds"] - before["cpuSeconds"],
    )
    result["verdict"] = (
        "Đạt"
        if result["sentActual"] == result["sentExpected"]
        and result["raw"] == result["expected"]
        and result["missing"] == result["duplicates"] == result["wrong"] == 0
        and result["acks"] == len(names) * count
        and not any(row["errors"] for row in result["clients"])
        else "Không đạt"
    )
    return result, stats


def it11(ctx, monitor, port, prefix, password, number):
    timeout = 30 if number == 10 else 60
    gate = ctx.Event()
    processes, pipes = [], []
    names = [f"{prefix}-n{number}-C{i:02d}" for i in range(1, number + 1)]
    result = {
        "N": number,
        "verdict": "Không đạt",
        "loginBudgetSeconds": timeout,
        "configuredExpectedMessages": number * 5,
        "configuredExpectedDeliveries": number * (number - 1) * 5,
    }
    try:
        result["initialServer"] = wait_registry(monitor, [])
        for name in names:
            parent, child = ctx.Pipe()
            process = ctx.Process(
                target=client, args=(child, gate, port, name, password, timeout)
            )
            process.start()
            child.close()
            processes.append(process)
            pipes.append(parent)
        for pipe in pipes:
            receive(pipe, timeout)
        started = time.monotonic()
        gate.set()
        logins = [
            receive(pipe, max(0, timeout - (time.monotonic() - started)))
            for pipe in pipes
        ]
        result.update(
            loginResults=logins,
            loginSuccess=sum(row["loggedIn"] for row in logins),
            loginElapsedSeconds=time.monotonic() - started,
        )
        if result["loginSuccess"] != number:
            result["reason"] = (
                "Target client count not reached; workload not started or renormalized"
            )
            result["partialStats"] = exchange(pipes, {"op": "stats"}, WAIT)
            return result
        result["registryReady"] = wait_registry(monitor, names)
        result["onlineSnapshots"] = exchange(pipes, {"op": "online"}, timeout)
        require(
            all(set(row["users"]) == set(names) for row in result["onlineSnapshots"]),
            "LIST_ONLINE mismatch",
        )
        stable, stats = workload(
            pipes, gate, names, 5, prefix + f"/N{number}/stable", timeout, monitor
        )
        result["stable"] = stable
        half = number // 2
        gate.clear()
        for pipe in pipes[:half]:
            pipe.send({"op": "close"})
        gate.set()
        for pipe in pipes[:half]:
            receive(pipe, WAIT)
        result["registryHalfClosed"] = wait_registry(monitor, names[half:])
        survivors, _ = workload(
            pipes[half:],
            gate,
            names[half:],
            1,
            prefix + f"/N{number}/survivors",
            timeout,
            monitor,
        )
        result["survivors"] = survivors
        gate.clear()
        for pipe in pipes[:half]:
            pipe.send({"op": "reconnect"})
        gate.set()
        reconnect = [receive(pipe, timeout) for pipe in pipes[:half]]
        result["reconnectResults"] = reconnect
        result["registryReconnected"] = wait_registry(monitor, names)
        final = exchange(pipes, {"op": "stats"}, WAIT)
        result["rawClientEvidence"] = final
        result["verdict"] = (
            "Đạt"
            if stable["verdict"] == survivors["verdict"] == "Đạt"
            and all(row["loggedIn"] for row in reconnect)
            else "Không đạt"
        )
    except (OSError, EOFError, ValueError, AssertionError) as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        gate.set()
        for pipe, process in zip(pipes, processes):
            if process.is_alive():
                try:
                    pipe.send({"op": "stop"})
                except OSError:
                    pass
        for process in processes:
            process.join(5)
            if process.is_alive():
                process.terminate()  # Only the worker created by this harness.
                process.join(5)
        result["workerExitCodes"] = [process.exitcode for process in processes]
        for pipe in pipes:
            pipe.close()
        result["reset"] = wait_registry(monitor, [])
    return result


def main():
    global P2, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=P2)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/p3/load")
    args = parser.parse_args()
    P2 = args.source.resolve(strict=True)
    OUTPUT = args.output.resolve() / ("load-" + uuid.uuid4().hex)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    certs = OUTPUT / "tls"
    os.environ.pop("CONNECT_TEST_CA", None)
    if P2 == ROOT:
        from security.tls import create_certificates

        create_certificates(certs)
        os.environ["CONNECT_TEST_CA"] = str(certs / "ca.pem")
    ctx = mp.get_context("spawn")
    run_id = "load-" + uuid.uuid4().hex[:12]

    def git(*args):
        return subprocess.check_output(["git", "-C", str(P2), *args], text=True).strip()

    report = {
        "runId": run_id,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "p2Status": git("status", "--short"),
        "python": sys.version,
        "platform": platform.platform(),
        "logicalCPUs": os.cpu_count(),
        "runnerSHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "security": "TLS/AES-GCM" if P2 == ROOT else "legacy reference",
        "sourceKind": "configured checkout; not automatically a legacy reference",
        "p2SourceSHA256": {
            str(p.relative_to(P2)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (P2 / "server").glob("*.py")
        },
        "cases": {},
    }
    parent, child = ctx.Pipe()
    process = ctx.Process(
        target=serve, args=(child, str(P2), str(OUTPUT / (run_id + "-server.log")))
    )
    process.start()
    child.close()
    password = secrets.token_urlsafe(24)
    try:
        report["server"] = receive(parent, 15)
        print(json.dumps({"ownedServer": report["server"]}), flush=True)
        report["cases"]["IT12"] = it12(
            parent, report["server"]["port"], run_id, password
        )
        print("IT12: " + report["cases"]["IT12"]["verdict"], flush=True)
        report["cases"]["IT11"] = []
        for count in (10, 20):
            case_started = time.monotonic()
            result = it11(
                ctx, parent, report["server"]["port"], run_id, password, count
            )
            result["elapsedSeconds"] = round(time.monotonic() - case_started, 3)
            report["cases"]["IT11"].append(result)
            print(
                json.dumps(
                    {
                        "N": count,
                        "verdict": result["verdict"],
                        "loginSuccess": result.get("loginSuccess"),
                        "stable": {
                            key: value
                            for key, value in result.get("stable", {}).items()
                            if key
                            in {
                                "sentActual",
                                "expected",
                                "raw",
                                "unique",
                                "duplicates",
                                "missing",
                                "wrong",
                                "acks",
                            }
                        },
                        "error": result.get("error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    except (OSError, EOFError, ValueError, AssertionError) as exc:
        report["harnessError"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if process.is_alive():
            try:
                parent.send("stop")
            except OSError:
                pass
            process.join(10)
        forced = process.is_alive()
        if forced:
            process.terminate()  # Never locate or kill an existing P2 instance.
            process.join(5)
        parent.close()
        report["shutdown"] = {
            "pid": process.pid,
            "alive": process.is_alive(),
            "exitCode": process.exitcode,
            "forced": forced,
        }
        if certs.exists():
            assert certs.parent == OUTPUT
            shutil.rmtree(certs)
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        content = json.dumps(report, ensure_ascii=False, indent=2)
        require(password not in content, "Credentials must not enter evidence")
        for name in ("results.json", run_id + ".json"):
            (OUTPUT / name).write_text(content, encoding="utf-8")
        print(
            json.dumps(
                {"runId": run_id, "shutdown": report["shutdown"]}, ensure_ascii=False
            ),
            flush=True,
        )
    passed = (
        not report.get("harnessError")
        and report.get("cases", {}).get("IT12", {}).get("verdict") == "Đạt"
        and len(report["cases"].get("IT11", [])) == 2
        and all(row["verdict"] == "Đạt" for row in report["cases"]["IT11"])
        and process.exitcode == 0
        and not forced
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
