"""Small Windows file-system helpers."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def documents_dir() -> Path:
    """The user's Documents folder, following OneDrive/folder redirection."""
    if sys.platform == "win32":
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return Path(os.path.expandvars(winreg.QueryValueEx(k, "Personal")[0]))
        except OSError:
            pass
    return Path.home() / "Documents"


def appdata_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / ".config")


def move_to_trash(path: Path) -> None:
    """Send a file or folder to the Recycle Bin (permanent delete off Windows)."""
    if sys.platform != "win32":
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        return

    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(
        wFunc=FO_DELETE,
        pFrom=str(path) + "\0",  # list must be double-null terminated
        fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0 or op.fAnyOperationsAborted:
        raise OSError(f"could not move {path.name} to the Recycle Bin (code {result})")


def reveal_in_explorer(path: Path) -> None:
    if path.is_dir():
        os.startfile(path)
    else:
        subprocess.Popen(["explorer", "/select,", str(path)])


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temporary file so a crash never leaves a half-written file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    try:
        os.replace(tmp, path)
    except PermissionError:
        # Target locked by another program (e.g. antivirus scan); write in place.
        tmp.unlink(missing_ok=True)
        path.write_bytes(data)
