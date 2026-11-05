"""Windows Credential Manager as the environment store's backend, through advapi32 (v1.12).

Each variable is one generic credential, `organism:env:<NAME>`. It belongs to the signed-in user and
stays on this machine. Windows keeps the value encrypted under the user's logon. Only `envstore`
imports this module, and only on Windows.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from organism_sdk.envstore import NAME_PATTERN, EnvStoreError

ERROR_NOT_FOUND = 1168
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
DEFAULT_PREFIX = "organism:env:"


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredReadW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.POINTER(_Credential)),
]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL
_advapi32.CredEnumerateW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_Credential))),
]
_advapi32.CredEnumerateW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]
_advapi32.CredFree.restype = None


def _failed(action: str, code: int) -> str:
    return f"Windows could not {action} (error {code})"


class CredentialManager:
    """Variables as credentials under `prefix`. Tests use their own prefix and remove what they add."""

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        self.prefix = prefix

    def names(self) -> list[str]:
        count = wintypes.DWORD(0)
        entries = ctypes.POINTER(ctypes.POINTER(_Credential))()
        if not _advapi32.CredEnumerateW(
            self.prefix + "*", 0, ctypes.byref(count), ctypes.byref(entries)
        ):
            code = ctypes.get_last_error()
            if code == ERROR_NOT_FOUND:
                return []
            raise EnvStoreError(_failed("list the variables", code))
        try:
            found = []
            for index in range(count.value):
                target = entries[index].contents.TargetName or ""
                name = target[len(self.prefix) :]
                if target.startswith(self.prefix) and NAME_PATTERN.fullmatch(name):
                    found.append(name)
            return found
        finally:
            _advapi32.CredFree(ctypes.cast(entries, ctypes.c_void_p))

    def read(self, name: str) -> str | None:
        entry = ctypes.POINTER(_Credential)()
        if not _advapi32.CredReadW(self.prefix + name, CRED_TYPE_GENERIC, 0, ctypes.byref(entry)):
            code = ctypes.get_last_error()
            if code == ERROR_NOT_FOUND:
                return None
            raise EnvStoreError(_failed("read the variable", code))
        try:
            credential = entry.contents
            size = credential.CredentialBlobSize
            if size == 0:
                return ""
            raw = ctypes.string_at(ctypes.cast(credential.CredentialBlob, ctypes.c_void_p), size)
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise EnvStoreError("the stored value is not valid UTF-8") from None
        finally:
            _advapi32.CredFree(ctypes.cast(entry, ctypes.c_void_p))

    def write(self, name: str, value: str) -> None:
        data = value.encode("utf-8")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = _Credential()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self.prefix + name
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.CredentialBlobSize = len(data)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise EnvStoreError(_failed("save the variable", ctypes.get_last_error()))

    def delete(self, name: str) -> bool:
        if not _advapi32.CredDeleteW(self.prefix + name, CRED_TYPE_GENERIC, 0):
            code = ctypes.get_last_error()
            if code == ERROR_NOT_FOUND:
                return False
            raise EnvStoreError(_failed("remove the variable", code))
        return True
