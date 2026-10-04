import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

from .logger import get_logger

logger = get_logger(__name__)


# Minimum number of path components required BELOW the root/anchor before a
# path is considered safe to delete. This blocks filesystem roots, drive roots,
# and dangerously shallow paths (e.g. "C:\Foo" or "/foo") from ever being
# handed to a recursive delete. App data lives several levels deep
# (e.g. %LOCALAPPDATA%\SayIt\models), so this does not reject real targets.
_MIN_SAFE_DEPTH = 2


def _is_safe_path(path: Path) -> bool:
    """Return True only if ``path`` is clearly safe to recursively delete.

    Conservative by design: when anything is uncertain we return False so the
    caller skips the deletion. The check must be correct even when running on
    one OS while generating a cleanup script targeting another, so it relies on
    structural properties (``parent == self`` identifies any filesystem or
    drive root) rather than OS-specific string comparisons.
    """
    try:
        resolved = path.resolve()

        # Any filesystem root or drive root: its parent is itself.
        # Handles POSIX "/", Windows "C:\\", and UNC share roots.
        if resolved.parent == resolved:
            return False

        # User home directory (and, defensively, its direct parent).
        try:
            home = Path.home().resolve()
            if resolved == home or resolved == home.parent:
                return False
        except Exception:
            # If home cannot be resolved, fall through to the depth check.
            pass

        # Reject dangerously shallow paths. ``parts`` includes the anchor
        # (e.g. "C:\\" or "/"), so we require at least _MIN_SAFE_DEPTH
        # components in addition to the anchor.
        anchor_parts = 1 if resolved.anchor else 0
        if len(resolved.parts) - anchor_parts < _MIN_SAFE_DEPTH:
            return False

        return True
    except Exception:
        return False


def generate_cleanup_script(paths_to_delete: List[Path]) -> Path:
    system = platform.system()
    pid = os.getpid()

    valid_paths = []
    for p in paths_to_delete:
        if not p.exists():
            continue

        if not _is_safe_path(p):
            logger.warning(f"SKIPPING UNSAFE PATH cleanup request for: {p}")
            continue

        valid_paths.append(p)

    if not valid_paths:
        logger.warning(
            "No valid, safe paths to delete provided to cleanup script generator"
        )

    if system == "Windows":
        return _generate_windows_script(valid_paths, pid)
    else:
        return _generate_linux_script(valid_paths, pid)


def run_cleanup_script(script_path: Path) -> None:
    logger.info(f"Launching cleanup script: {script_path}")

    system = platform.system()

    try:
        if system == "Windows":
            subprocess.Popen(
                [str(script_path)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                shell=True,
                close_fds=True,
            )
        else:
            subprocess.Popen(
                ["/bin/bash", str(script_path)],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.error(f"Failed to launch cleanup script: {e}")
        raise


def _generate_windows_script(paths: List[Path], pid: int) -> Path:
    fd, path = tempfile.mkstemp(suffix=".bat", prefix="sayit_cleanup_")
    os.close(fd)
    script_path = Path(path)

    commands = [
        "@echo off",
        ":WAIT_LOOP",
        f'tasklist /FI "PID eq {pid}" 2>nul | find /i "{pid}" >nul',
        "if errorlevel 1 (",
        "    goto :DELETE_FILES",
        ") else (",
        "    timeout /t 1 /nobreak >nul",
        "    goto :WAIT_LOOP",
        ")",
        "",
        ":DELETE_FILES",
        "timeout /t 2 /nobreak >nul",
    ]

    for p in paths:
        win_path = str(p).replace("/", "\\")
        commands.append(f'if exist "{win_path}\\" rmdir /s /q "{win_path}" >nul 2>&1')
        commands.append(f'if exist "{win_path}" del /f /q "{win_path}" >nul 2>&1')

    commands.append(f'del "%~f0" >nul 2>&1')

    try:
        script_path.write_text("\n".join(commands), encoding="utf-8")
        return script_path
    except Exception as e:
        logger.error(f"Failed to write Windows cleanup script: {e}")
        raise


def _generate_linux_script(paths: List[Path], pid: int) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="sayit_cleanup_")
    os.close(fd)
    script_path = Path(path)

    commands = [
        "#!/bin/bash",
        "",
        f"tail --pid={pid} -f /dev/null",
        "sleep 2",
        "",
    ]

    for p in paths:
        commands.append(f'rm -rf "{p}"')

    commands.append("")
    commands.append(f'rm -- "$0"')

    try:
        script_path.write_text("\n".join(commands), encoding="utf-8")
        script_path.chmod(0o755)
        return script_path
    except Exception as e:
        logger.error(f"Failed to write Linux cleanup script: {e}")
        raise
