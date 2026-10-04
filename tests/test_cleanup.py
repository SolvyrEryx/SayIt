import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sayit.utils.cleanup import (
    _generate_linux_script,
    _generate_windows_script,
    _is_safe_path,
    generate_cleanup_script,
)


class TestCleanupScriptGeneration:
    def test_linux_script_content(self, tmp_path):
        paths = [tmp_path / "dir1", tmp_path / "file1.txt"]
        pid = 12345

        script_path = _generate_linux_script(paths, pid)

        assert script_path.exists()
        content = script_path.read_text()

        assert "#!/bin/bash" in content
        assert f"tail --pid={pid} -f /dev/null" in content
        assert f'rm -rf "{paths[0]}"' in content
        assert f'rm -rf "{paths[1]}"' in content
        assert 'rm -- "$0"' in content

        script_path.unlink()

    def test_windows_script_content(self, tmp_path):
        paths = [tmp_path / "dir1", tmp_path / "file1.txt"]
        pid = 12345

        script_path = _generate_windows_script(paths, pid)

        assert script_path.exists()
        content = script_path.read_text()

        assert 'tasklist /FI "PID eq' in content
        assert f"{pid}" in content
        win_path_0 = str(paths[0]).replace("/", "\\")
        assert f'rmdir /s /q "{win_path_0}"' in content
        assert 'del "%~f0"' in content

        script_path.unlink()

    @patch("src.sayit.utils.cleanup.platform.system")
    @patch("src.sayit.utils.cleanup.os.getpid")
    def test_generate_cleanup_script_dispatches_correctly(
        self, mock_getpid, mock_system, tmp_path
    ):
        mock_getpid.return_value = 12345
        paths = [tmp_path / "test"]
        paths[0].mkdir()

        mock_system.return_value = "Linux"
        script = generate_cleanup_script(paths)
        assert script.suffix == ".sh"
        script.unlink()

        mock_system.return_value = "Windows"
        script = generate_cleanup_script(paths)
        assert script.suffix == ".bat"
        script.unlink()

    @patch("src.sayit.utils.cleanup.Path.exists")
    def test_safeguards_exclude_critical_paths(self, mock_exists, tmp_path):

        mock_exists.return_value = True

        root_path = Path(Path(tmp_path).root)
        home_path = Path.home()
        safe_path = tmp_path / "safe_to_delete"

        unsafe_paths = [root_path, home_path, safe_path]

        with patch(
            "src.sayit.utils.cleanup.platform.system", return_value="Linux"
        ):
            with patch("src.sayit.utils.cleanup.os.getpid", return_value=12345):
                script_path = generate_cleanup_script(unsafe_paths)

        assert script_path.exists()
        content = script_path.read_text()

        assert str(safe_path) in content

        assert f'rm -rf "{root_path}"' not in content

        assert f'rm -rf "{home_path}"' not in content

        script_path.unlink()


class TestIsSafePath:
    def test_filesystem_root_rejected(self):
        # Anchor root (POSIX "/" or current drive on Windows).
        assert _is_safe_path(Path(Path.cwd().anchor)) is False

    def test_drive_root_rejected(self, tmp_path):
        # The root of whatever drive tmp_path lives on.
        assert _is_safe_path(Path(Path(tmp_path).anchor)) is False

    def test_home_rejected(self):
        assert _is_safe_path(Path.home()) is False

    def test_shallow_path_rejected(self):
        # One component below the anchor is too shallow to delete recursively.
        shallow = Path(Path.cwd().anchor) / "single_component"
        assert _is_safe_path(shallow) is False

    def test_deep_app_data_path_allowed(self, tmp_path):
        # A realistic app-data target several levels deep is safe.
        deep = tmp_path / "SayIt" / "models"
        assert _is_safe_path(deep) is True
