import os
import sys
import tempfile
import pytest

from path_safety import (
    assert_safe_write_path, PathSafetyError, _is_drive_root, _is_under
)


class TestIsDriveRoot:
    def test_windows_c_drive(self):
        assert _is_drive_root(__import__('pathlib').Path("C:\\")) is True

    def test_windows_d_drive(self):
        assert _is_drive_root(__import__('pathlib').Path("D:\\")) is True

    def test_windows_colon_only(self):
        assert _is_drive_root(__import__('pathlib').Path("E:")) is True

    def test_windows_forward_slash(self):
        assert _is_drive_root(__import__('pathlib').Path("F:/")) is True

    def test_unix_root(self):
        assert _is_drive_root(__import__('pathlib').Path("/")) is (sys.platform != "win32")

    def test_normal_path(self):
        assert _is_drive_root(__import__('pathlib').Path("C:\\Users")) is False


class TestIsUnder:
    def test_direct_child(self):
        assert _is_under(__import__('pathlib').Path("/a/b"), __import__('pathlib').Path("/a")) is True

    def test_same_path(self):
        assert _is_under(__import__('pathlib').Path("/a"), __import__('pathlib').Path("/a")) is True

    def test_not_under(self):
        assert _is_under(__import__('pathlib').Path("/b"), __import__('pathlib').Path("/a")) is False

    def test_prefix_trap(self):
        assert _is_under(__import__('pathlib').Path("/ab"), __import__('pathlib').Path("/a")) is False


class TestAssertSafeWritePathBlacklist:
    def test_blocks_windows_system_dir(self):
        with pytest.raises(PathSafetyError):
            assert_safe_write_path(r"C:\Windows\System32\foo.txt")

    def test_blocks_program_files(self):
        with pytest.raises(PathSafetyError):
            assert_safe_write_path(r"C:\Program Files\app")

    def test_blocks_drive_root(self):
        with pytest.raises(PathSafetyError):
            assert_safe_write_path("D:\\")

    def test_allows_temp(self):
        tmp = tempfile.mkdtemp()
        try:
            assert_safe_write_path(os.path.join(tmp, "test.txt"))
        finally:
            os.rmdir(tmp)


class TestAssertSafeWritePathWhitelist:
    def test_allows_inside_whitelist(self):
        tmp = tempfile.mkdtemp()
        try:
            assert_safe_write_path(os.path.join(tmp, "sub", "file.txt"), config={"allowed_roots": [tmp]})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rejects_outside_whitelist(self):
        with pytest.raises(PathSafetyError):
            assert_safe_write_path("C:\\outside", config={"allowed_roots": ["D:\\project"]})


class TestSymlinkRejection:
    def test_rejects_symlink(self, tmp_path):
        if sys.platform == "win32":
            pytest.skip("Windows 创建符号链接需要管理员权限")
        real = tmp_path / "real.txt"
        real.write_text("x")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        with pytest.raises(PathSafetyError) as exc:
            assert_safe_write_path(str(link))
        assert "符号链接" in str(exc.value)
