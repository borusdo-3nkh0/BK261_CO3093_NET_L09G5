"""Session-owned HTTP staging and a single-consumer P1 event/worker boundary."""

import importlib
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

MAX_FILE = 256 * 1024 * 1024
MAX_ACTIVE = 8
MAX_RECORDS = 128
LIVE = {"queued", "awaiting_acceptance", "transferring"}


def uncertain(error):
    return isinstance(error, (TimeoutError, ConnectionError)) or any(
        term in str(error).lower()
        for term in ("deadline", "retry limit", "client closed", "socket failed")
    )


def load_p1(root):
    root = Path(root).resolve(strict=True)
    sys.path.insert(0, str(root))
    client = importlib.import_module("p1.client")
    protocol = importlib.import_module("shared.protocol")
    for module in (client, protocol):
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise ValueError("P1/shared import does not match --p1-root")

    def factory(ticket, relay, downloads):
        return client.FileClient(
            protocol.SessionTicket.from_dict(ticket),
            relay,
            downloads,
            auto_accept=False,
        )

    return factory


def filename(value):
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or len(value.encode("utf-8")) > 128
        or value.endswith((".", " "))
        or any(c in '/\\:*?"<>|' or ord(c) < 32 or ord(c) == 127 for c in value)
        or value.split(".")[0].upper()
        in {"CON", "PRN", "AUX", "NUL"}
        | {p + str(i) for p in ("COM", "LPT") for i in range(1, 10)}
    ):
        raise ValueError("Tên file không hợp lệ hoặc vượt 128 byte UTF-8.")
    return value


def pair_id(a, b):
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(sorted([a, b]), ensure_ascii=False))
    )


class FileService:
    def __init__(self, username, client_factory, ticket, relay, storage, publish):
        self.username, self.publish = username, publish
        storage = Path(storage)
        storage.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="session-", dir=storage)).resolve()
        self.downloads = self.root / "received"
        self.lock = threading.Condition(threading.RLock())
        self.closing_lock = threading.Lock()
        self.stopped, self.closed = threading.Event(), threading.Event()
        self.records, self.wire_ids, self.used_requests = {}, {}, set()
        self.used_bytes, self.io_count = 0, 0
        self.tasks = queue.Queue()
        self.active = None
        self.thread = self.worker = None
        try:
            self.client = client_factory(ticket, relay, self.downloads)
        except BaseException:
            shutil.rmtree(self.root)
            raise

    def start(self):
        self.client.start()
        if self.stopped.is_set():
            return
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="file-events"
        )
        self.thread.start()

    def _emit(self, record, status=None, *, error=None, count=None):
        data = record["data"]
        if self.stopped.is_set() or data["status"] not in LIVE:
            return
        data.update(revision=data["revision"] + 1, error=error)
        if status:
            data["status"] = status
        if count is not None:
            data["transferredBytes"] = count
        self.publish("transfer.upsert", dict(data))

    def _new(self, transfer_id, sender, recipient, name, size, conversation):
        if (
            self.stopped.is_set()
            or transfer_id in self.records
            or len(self.records) >= MAX_RECORDS
            or sum(r["data"]["status"] in LIVE for r in self.records.values())
            >= MAX_ACTIVE
            or type(size) is not int
            or not 0 <= size <= MAX_FILE
        ):
            raise ValueError("File hoặc giới hạn tác vụ không hợp lệ.")
        record = {
            "data": dict(
                transferId=transfer_id,
                revision=0,
                conversationId=conversation,
                senderId=sender,
                recipientId=recipient,
                fileName=filename(name),
                totalBytes=size,
                transferredBytes=0,
                progressSource="live",
                status="queued",
                error=None,
            ),
            "reserved": 0,
            "wire_id": None,
            "path": None,
        }
        self.records[transfer_id] = record
        return record

    def _reserve(self, record):
        amount = record["data"]["totalBytes"]
        if self.used_bytes + amount > MAX_FILE:
            raise ValueError("Phiên vượt hạn mức lưu file 256 MiB.")
        self.used_bytes += amount
        record["reserved"] = amount

    def _release(self, record):
        self.used_bytes -= record["reserved"]
        record["reserved"] = 0

    def upload(self, meta, length, stream):
        if set(meta) != {
            "requestId",
            "transferId",
            "conversationId",
            "recipient",
            "name",
        }:
            raise ValueError("Thiếu thông tin file.")
        for key in ("requestId", "transferId"):
            if str(uuid.UUID(meta[key])) != meta[key]:
                raise ValueError("ID file không hợp lệ.")
        recipient = meta["recipient"]
        if (
            not recipient
            or recipient == self.username
            or recipient != recipient.strip()
            or len(recipient.encode()) > 64
            or any(ord(c) < 32 or ord(c) == 127 for c in recipient)
            or not 0 < len(meta["conversationId"]) <= 128
            or meta["conversationId"] == "global"
        ):
            raise ValueError("Người nhận hoặc cuộc chat không hợp lệ.")
        with self.lock:
            if meta["requestId"] in self.used_requests:
                raise ValueError("Yêu cầu file đã được sử dụng.")
            if len(self.used_requests) >= MAX_RECORDS:
                raise ValueError("Phiên đã đạt giới hạn yêu cầu file.")
            record = self._new(
                meta["transferId"],
                self.username,
                recipient,
                meta["name"],
                length,
                meta["conversationId"],
            )
            try:
                self._reserve(record)
            except ValueError:
                del self.records[meta["transferId"]]
                raise
            self.used_requests.add(meta["requestId"])
            self.io_count += 1
        directory = None
        try:
            directory = Path(tempfile.mkdtemp(prefix="upload-", dir=self.root))
            path = directory / record["data"]["fileName"]
            remaining, deadline = length, time.monotonic() + 120
            with path.open("xb") as output:
                while remaining:
                    if self.stopped.is_set() or time.monotonic() > deadline:
                        raise ValueError("Upload đã hết hạn hoặc phiên đã đóng.")
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError("Upload chưa đủ dữ liệu.")
                    output.write(chunk)
                    remaining -= len(chunk)
            with self.lock:
                if self.stopped.is_set():
                    raise ValueError("Phiên đã đóng.")
                record["path"] = path
                self._emit(record, "queued")
                self.tasks.put(record)
            return True
        except BaseException:
            if directory:
                shutil.rmtree(directory)
            with self.lock:
                self._release(record)
                self.records.pop(meta["transferId"], None)
            raise
        finally:
            with self.lock:
                self.io_count -= 1
                self.lock.notify_all()

    def decide(self, transfer_id, accept):
        with self.lock:
            record = self.records.get(transfer_id)
            if (
                self.stopped.is_set()
                or not record
                or record["data"]["recipientId"] != self.username
                or record["data"]["status"] != "awaiting_acceptance"
            ):
                raise ValueError("Yêu cầu nhận file không còn hiệu lực.")
            if not accept:
                self.client.reject_file(record["wire_id"])
                self._emit(
                    record,
                    "rejected",
                    error={
                        "code": "REJECTED",
                        "userMessage": "Bạn đã từ chối nhận file.",
                    },
                )
            else:
                self._reserve(record)
                try:
                    self.client.accept_file(record["wire_id"])
                except Exception:
                    try:
                        self.client.cancel_file(record["wire_id"])
                    except Exception:
                        pass
                    self._release(record)
                    self._emit(
                        record,
                        "failed",
                        error={
                            "code": "ACCEPT_FAILED",
                            "userMessage": "Không thể nhận file.",
                        },
                    )
                    return False
                self._emit(record, "transferring")
            return True

    @contextmanager
    def download(self, transfer_id):
        with self.lock:
            record = self.records.get(transfer_id)
            if (
                self.stopped.is_set()
                or not record
                or record["data"]["recipientId"] != self.username
                or record["data"]["status"] != "completed"
            ):
                raise ValueError("File không thuộc phiên hoặc chưa hoàn tất.")
            path = record["path"].resolve(strict=True)
            if not path.is_relative_to(self.downloads.resolve()):
                raise ValueError("File không hợp lệ.")
            stream = path.open("rb")
            self.io_count += 1
        try:
            yield stream, dict(record["data"])
        finally:
            stream.close()
            with self.lock:
                self.io_count -= 1
                self.lock.notify_all()

    def _bind(self, record, wire_id):
        if record["wire_id"] not in (None, wire_id) or (
            wire_id in self.wire_ids and self.wire_ids[wire_id] is not record
        ):
            raise ValueError("P1 correlation mismatch")
        record["wire_id"] = wire_id
        self.wire_ids[wire_id] = record

    def _event(self, event):
        kind, wire_id = event.get("type"), event.get("transfer_id")
        record = self.wire_ids.get(wire_id)
        if kind == "file_offer":
            if record:
                return
            sender = event["sender"]
            try:
                record = self._new(
                    wire_id,
                    sender,
                    self.username,
                    event["filename"],
                    event["size"],
                    pair_id(sender, self.username),
                )
            except ValueError:
                self.client.reject_file(wire_id, "TRANSFER_LIMIT")
                return
            record["sha256"] = event["sha256"]
            self._bind(record, wire_id)
            self._emit(record, "awaiting_acceptance")
        elif kind == "file_sending":
            if record:
                return
            if not self.active:
                raise ValueError("No exclusive send context")
            record = self.active["record"]
            data = record["data"]
            if (event["filename"], event["recipient"], event["size"]) != (
                data["fileName"],
                data["recipientId"],
                data["totalBytes"],
            ):
                raise ValueError("P1 send context mismatch")
            self._bind(record, wire_id)
            self._emit(record, "awaiting_acceptance")
        elif record and kind == "file_progress":
            data = record["data"]
            if (
                event["total"] != data["totalBytes"]
                or not data["transferredBytes"] <= event["bytes"] <= data["totalBytes"]
            ):
                raise ValueError("Invalid P1 progress")
            self._emit(record, "transferring", count=event["bytes"])
        elif record and kind == "file_failed":
            rejected = event.get("reason") == "REJECTED"
            unknown = uncertain(event.get("reason", ""))
            self._emit(
                record,
                "rejected" if rejected else "unknown" if unknown else "failed",
                error={
                    "code": "REJECTED" if rejected else "FILE_FAILED",
                    "userMessage": "Chưa xác định kết quả truyền file."
                    if unknown
                    else "Người nhận đã từ chối file."
                    if rejected
                    else "Truyền file thất bại.",
                },
            )
            if record["data"]["recipientId"] == self.username:
                self._release(record)
        # Sender completion uses the worker result; receiver uses received_files.

    def _received(self, result):
        record = self.wire_ids.get(str(result.transfer_id))
        if not record or record["data"]["status"] not in LIVE:
            return
        path = Path(result.path).resolve(strict=True)
        if (
            record["data"]["recipientId"] != self.username
            or not path.is_relative_to(self.downloads.resolve())
            or result.size != record["data"]["totalBytes"]
            or result.sha256 != record["sha256"]
            or path.stat().st_size != result.size
        ):
            raise ValueError("Invalid received file result")
        record["path"] = path
        record["data"]["downloadAvailable"] = True
        self._emit(record, "completed", count=result.size)

    def _drain(self):
        for _ in range(256):
            try:
                event = self.client.events.get_nowait()
            except queue.Empty:
                break
            self._event(event)
        for _ in range(8):
            try:
                result = self.client.received_files.get_nowait()
            except queue.Empty:
                break
            self._received(result)

    def _send(self, task):
        try:
            task["result"] = self.client.send_file(
                task["record"]["path"], task["record"]["data"]["recipientId"]
            )
        except Exception as error:
            task["uncertain"] = uncertain(error)
        finally:
            task["done"].set()

    def _run(self):
        try:
            while not self.stopped.is_set():
                with self.lock:
                    self._drain()
                    if self.active and self.active["done"].is_set():
                        # All emits precede worker return. Drain the bounded FIFO before
                        # replacing its exclusive context, even on failure/evicted events.
                        self._drain()
                        task, record = self.active, self.active["record"]
                        result = task.get("result")
                        if result:
                            self._bind(record, str(result.transfer_id))
                            if (result.size, result.filename, result.recipient) != (
                                record["data"]["totalBytes"],
                                record["data"]["fileName"],
                                record["data"]["recipientId"],
                            ):
                                raise ValueError("P1 result mismatch")
                            self._emit(record, "completed", count=result.size)
                        else:
                            self._emit(
                                record,
                                "unknown" if task.get("uncertain") else "failed",
                                error={
                                    "code": "FILE_FAILED",
                                    "userMessage": "Truyền file thất bại; chưa có xác nhận hoàn tất.",
                                },
                            )
                        shutil.rmtree(record["path"].parent)
                        self._release(record)
                        self.active = None
                    if not self.active:
                        try:
                            record = self.tasks.get_nowait()
                        except queue.Empty:
                            pass
                        else:
                            self.active = {"record": record, "done": threading.Event()}
                            self.worker = threading.Thread(
                                target=self._send,
                                args=(self.active,),
                                daemon=True,
                                name="file-send",
                            )
                            self.worker.start()
                self.stopped.wait(0.02)
        except Exception:
            self.close_async()
            self.publish(
                "files.changed",
                {
                    "state": "unavailable",
                    "userMessage": "Dịch vụ file bị gián đoạn. Hãy đăng nhập lại.",
                },
            )

    def close_async(self):
        with self.closing_lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
        threading.Thread(target=self._close, daemon=True, name="file-cleanup").start()

    def _close(self):
        try:
            try:
                self.client.close()
            except Exception:
                pass  # The session's private staging still needs cleanup.
            if self.worker:
                self.worker.join()
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join()
            with self.lock:
                self.lock.wait_for(lambda: self.io_count == 0)
            shutil.rmtree(self.root)
        finally:
            self.closed.set()
