"""Private local-state files and a cross-process lock.

POSIX files are mode 0600 and directories mode 0700. The mode is read back
after chmod. Windows files and directories get a protected discretionary ACL
that allows only the current user, and that ACL is read back. Creating a file
is not evidence that the ACL is private.

What Windows does not guarantee:

- An administrator, or anyone with take-ownership or backup privilege, can
  still read or replace the file.
- This is not a substitute for disk encryption.
- An existing parent directory is left unchanged. Only a directory this module
  is asked to restrict is given a private ACL.
- os.chmod on Windows does not set an ACL. It is not used as proof.

Other operating systems fail closed. This process cannot enforce a private ACL
there, so a caller that asked for enforcement must not continue.
"""
from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

def replace_file(source: Path, destination: Path, *, attempts: int = 5) -> None:
    """Replace destination with source. Retry when Windows briefly locks either file.

    A scanner or the previous reader can return WinError 5 for a few milliseconds
    after a write. The replacement stays atomic on each attempt. A persistent
    denial still raises.
    """
    delay = 0.05
    last: PermissionError | None = None
    for attempt in range(max(1, attempts)):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            last = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(delay)
            delay = min(delay * 2, 0.4)
    assert last is not None
    raise last


class StatePermissionError(Exception):
    """Permission enforcement was requested and did not succeed."""


class StateLockError(Exception):
    """The cross-process state lock could not be acquired."""


def _refuse_link(path: Path) -> None:
    if path.is_symlink():
        raise StatePermissionError("state path must not be a symbolic link")


def assert_private(path: Path) -> None:
    """Raise unless the path currently has a private mode or ACL."""
    _refuse_link(path)
    if os.name == "nt":
        _assert_windows_private(path)
        return
    if os.name == "posix":
        if not path.exists():
            raise StatePermissionError("state path is missing")
        mode = stat.S_IMODE(path.stat().st_mode)
        expected = 0o700 if path.is_dir() else 0o600
        if mode != expected:
            raise StatePermissionError("state path is not private")
        return
    raise StatePermissionError("state permissions cannot be enforced on this operating system")


def restrict_private(path: Path) -> None:
    """Set a private mode or ACL, then verify it. Failure raises."""
    _refuse_link(path)
    if not path.exists():
        raise StatePermissionError("state path is missing")
    try:
        if os.name == "nt":
            _restrict_windows(path)
        elif os.name == "posix":
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        else:
            raise StatePermissionError("state permissions cannot be enforced on this operating system")
    except StatePermissionError:
        raise
    except OSError as exc:
        raise StatePermissionError("state permissions could not be enforced") from exc
    assert_private(path)


class CrossProcessLock:
    """Exclusive lock held across processes. One thread must not re-enter it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()

    def __enter__(self) -> "CrossProcessLock":
        parent = self.path.parent
        if parent.is_symlink():
            raise StateLockError("state lock directory must not be a link")
        if not parent.is_dir():
            raise StateLockError("state lock directory is missing")
        _refuse_link(self.path)
        if self.path.exists() and not self.path.is_file():
            raise StateLockError("state lock must be a regular file")
        held_file = None
        held_handle = None
        try:
            if os.name == "nt":
                held_handle = _windows_lock(self.path)
            else:
                held_file = open(self.path, "a+b")
                if os.name == "posix":
                    import fcntl
                    fcntl.flock(held_file.fileno(), fcntl.LOCK_EX)
                else:
                    raise StateLockError("state file lock is not available on this operating system")
            self._local.file = held_file
            self._local.handle = held_handle
            restrict_private(self.path)
        except StatePermissionError as exc:
            self._release_pair(held_file, held_handle)
            raise StateLockError("state lock permissions could not be enforced") from exc
        except OSError as exc:
            self._release_pair(held_file, held_handle)
            raise StateLockError("state file lock could not be acquired") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._release_pair(getattr(self._local, "file", None), getattr(self._local, "handle", None))
        self._local.file = None
        self._local.handle = None

    def _release_pair(self, held_file: object, held_handle: object) -> None:
        try:
            if os.name == "nt" and held_handle is not None:
                _windows_unlock(held_handle)
            elif held_file is not None and os.name == "posix":
                import fcntl
                fcntl.flock(held_file.fileno(), fcntl.LOCK_UN)
        finally:
            if held_file is not None:
                held_file.close()
            if held_handle is not None:
                _windows_close(held_handle)


def _windows_libs():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel32.LockFileEx.restype = wintypes.BOOL
    kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel32.UnlockFileEx.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi32.GetLengthSid.restype = wintypes.DWORD
    advapi32.CopySid.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi32.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
    advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return kernel32, advapi32


def _current_user_sid() -> bytes:
    import ctypes
    from ctypes import wintypes

    kernel32, advapi32 = _windows_libs()

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken")
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation")
        user = ctypes.cast(buffer, ctypes.POINTER(SidAndAttributes)).contents
        length = advapi32.GetLengthSid(user.Sid)
        if not length:
            raise OSError(ctypes.get_last_error(), "GetLengthSid")
        copy = ctypes.create_string_buffer(length)
        if not advapi32.CopySid(length, copy, user.Sid):
            raise OSError(ctypes.get_last_error(), "CopySid")
        return copy.raw
    finally:
        kernel32.CloseHandle(token)


def _restrict_windows(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32, advapi32 = _windows_libs()

    class Acl(ctypes.Structure):
        _fields_ = [
            ("AclRevision", ctypes.c_byte),
            ("Sbz1", ctypes.c_byte),
            ("AclSize", wintypes.WORD),
            ("AceCount", wintypes.WORD),
            ("Sbz2", wintypes.WORD),
        ]

    class AceHeader(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_byte),
            ("AceFlags", ctypes.c_byte),
            ("AceSize", wintypes.WORD),
        ]

    class AccessAllowedAce(ctypes.Structure):
        _fields_ = [
            ("Header", AceHeader),
            ("Mask", wintypes.DWORD),
            ("SidStart", wintypes.DWORD),
        ]

    sid = _current_user_sid()
    sid_buf = ctypes.create_string_buffer(sid)
    acl_size = ctypes.sizeof(Acl) + ctypes.sizeof(AccessAllowedAce) + len(sid) + 64
    acl_buf = ctypes.create_string_buffer(acl_size)
    if not advapi32.InitializeAcl(acl_buf, acl_size, 2):
        raise OSError(ctypes.get_last_error(), "InitializeAcl")
    if not advapi32.AddAccessAllowedAceEx(acl_buf, 2, 0, 0x1F01FF, sid_buf):
        raise OSError(ctypes.get_last_error(), "AddAccessAllowedAceEx")
    status = advapi32.SetNamedSecurityInfoW(
        str(path),
        1,
        0x4 | 0x80000000,
        None,
        None,
        acl_buf,
        None,
    )
    if status != 0:
        raise OSError(status, "SetNamedSecurityInfoW")


def _assert_windows_private(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32, advapi32 = _windows_libs()

    class AceHeader(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_byte),
            ("AceFlags", ctypes.c_byte),
            ("AceSize", wintypes.WORD),
        ]

    class AccessAllowedAce(ctypes.Structure):
        _fields_ = [
            ("Header", AceHeader),
            ("Mask", wintypes.DWORD),
            ("SidStart", wintypes.DWORD),
        ]

    class AclSize(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    sacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = advapi32.GetNamedSecurityInfoW(
        str(path),
        1,
        0x4,
        ctypes.byref(owner),
        ctypes.byref(group),
        ctypes.byref(dacl),
        ctypes.byref(sacl),
        ctypes.byref(descriptor),
    )
    if status != 0 or not descriptor.value or not dacl.value:
        raise StatePermissionError("state ACL could not be read")
    try:
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not advapi32.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise StatePermissionError("state ACL could not be read")
        if not (control.value & 0x0004) or not (control.value & 0x1000):
            raise StatePermissionError("state ACL is not protected")
        info = AclSize()
        if not advapi32.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
            raise StatePermissionError("state ACL could not be read")
        if info.AceCount != 1:
            raise StatePermissionError("state ACL allows more than the current user")
        ace = ctypes.c_void_p()
        if not advapi32.GetAce(dacl, 0, ctypes.byref(ace)):
            raise StatePermissionError("state ACL could not be read")
        header = ctypes.cast(ace, ctypes.POINTER(AceHeader)).contents
        allowed = ctypes.cast(ace, ctypes.POINTER(AccessAllowedAce)).contents
        if header.AceType != 0 or header.AceFlags != 0 or allowed.Mask != 0x1F01FF:
            raise StatePermissionError("state ACL is not limited to the current user")
        sid_ptr = ctypes.c_void_p(ace.value + ctypes.sizeof(AceHeader) + ctypes.sizeof(wintypes.DWORD))
        expected = ctypes.create_string_buffer(_current_user_sid())
        if not advapi32.EqualSid(sid_ptr, expected):
            raise StatePermissionError("state ACL is not limited to the current user")
    finally:
        kernel32.LocalFree(descriptor)


def _overlapped():
    import ctypes
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    return Overlapped()


def _invalid_handle(handle: object) -> bool:
    import ctypes
    if not handle:
        return True
    invalid = ctypes.c_void_p(-1).value
    return handle == invalid or handle == -1


def _windows_lock(path: Path) -> object:
    kernel32, _advapi32 = _windows_libs()
    handle = kernel32.CreateFileW(
        str(path),
        0x80000000 | 0x40000000,
        0x1 | 0x2 | 0x4,
        None,
        4,
        0x80,
        None,
    )
    if _invalid_handle(handle):
        import ctypes
        raise OSError(ctypes.get_last_error(), "CreateFileW")
    overlapped = _overlapped()
    if not kernel32.LockFileEx(handle, 0x2, 0, 1, 0, ctypes_byref(overlapped)):
        import ctypes
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise OSError(error, "LockFileEx")
    return handle


def ctypes_byref(value: object) -> object:
    import ctypes
    return ctypes.byref(value)


def _windows_unlock(handle: object) -> None:
    kernel32, _advapi32 = _windows_libs()
    kernel32.UnlockFileEx(handle, 0, 1, 0, ctypes_byref(_overlapped()))


def _windows_close(handle: object) -> None:
    kernel32, _advapi32 = _windows_libs()
    kernel32.CloseHandle(handle)
