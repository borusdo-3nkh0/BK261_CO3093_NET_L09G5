"""Windows kill-on-close job for owned test descendants, including venv shims."""

import ctypes
import os
import subprocess
import sys
import uuid
from ctypes import wintypes


class WindowsJob:
    def __init__(self):
        self.handle = None
        self.name = None
        if os.name != "nt":
            return

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_longlong),
                ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD),
                ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in (
                    "read_ops",
                    "write_ops",
                    "other_ops",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                )
            ]

        class Limits(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", IO),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.name = "Connect-P3-" + uuid.uuid4().hex
        self.handle = self.api.CreateJobObjectW(None, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def attach(self, process):
        if self.handle and not self.api.AssignProcessToJobObject(
            self.handle, wintypes.HANDLE(process._handle)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def command(self, command):
        if not self.name:
            return command
        return [sys._base_executable, "-B", __file__, self.name, *map(str, command)]

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def main():
    # Join before spawning even a fast venv shim, so descendants cannot escape.
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    api.OpenJobObjectW.restype = wintypes.HANDLE
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenJobObjectW(1, False, sys.argv[1])
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not api.AssignProcessToJobObject(handle, api.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        api.CloseHandle(handle)  # The supervisor owns the only lifetime handle.
    return subprocess.call(sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
