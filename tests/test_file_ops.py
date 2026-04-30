import os
import tempfile
import shutil
import pytest

from file_ops import (
    move_file, copy_file, delete_file, create_folder, create_file,
    read_file, write_file, rename_file, search_files, list_files
)


@pytest.fixture
def tmp_dir():
    """创建临时目录"""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tmp_file(tmp_dir):
    """创建临时文件"""
    f = os.path.join(tmp_dir, "test.txt")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write("Hello")
    return f


class TestMoveFile:
    def test_move_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "a.txt")
        dst = os.path.join(tmp_dir, "b.txt")
        with open(src, "w") as f:
            f.write("test")
        result = move_file(src, dst)
        assert result["success"] is True
        assert not os.path.exists(src)
        assert os.path.exists(dst)

    def test_move_nonexistent(self):
        result = move_file("/nonexistent/file", "/tmp/dst")
        assert result["success"] is False


class TestCopyFile:
    def test_copy_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "a.txt")
        dst = os.path.join(tmp_dir, "b.txt")
        with open(src, "w") as f:
            f.write("test")
        result = copy_file(src, dst)
        assert result["success"] is True
        assert os.path.exists(src)
        assert os.path.exists(dst)

    def test_copy_folder(self, tmp_dir):
        src = os.path.join(tmp_dir, "folder")
        dst = os.path.join(tmp_dir, "folder_copy")
        os.makedirs(src)
        with open(os.path.join(src, "file.txt"), "w") as f:
            f.write("test")
        result = copy_file(src, dst)
        assert result["success"] is True
        assert os.path.exists(dst)


class TestDeleteFile:
    def test_delete_file(self, tmp_dir):
        f = os.path.join(tmp_dir, "to_delete.txt")
        with open(f, "w") as fh:
            fh.write("test")
        result = delete_file(f)
        assert result["success"] is True
        assert not os.path.exists(f)

    def test_delete_folder(self, tmp_dir):
        d = os.path.join(tmp_dir, "to_delete_dir")
        os.makedirs(d)
        result = delete_file(d)
        assert result["success"] is True
        assert not os.path.exists(d)


class TestCreateFolder:
    def test_create_folder(self, tmp_dir):
        path = os.path.join(tmp_dir, "new", "nested", "folder")
        result = create_folder(path)
        assert result["success"] is True
        assert os.path.isdir(path)


class TestCreateFile:
    def test_create_file_empty(self, tmp_dir):
        path = os.path.join(tmp_dir, "new.txt")
        result = create_file(path)
        assert result["success"] is True
        assert os.path.isfile(path)

    def test_create_file_with_content(self, tmp_dir):
        path = os.path.join(tmp_dir, "new.txt")
        result = create_file(path, "content here")
        assert result["success"] is True
        with open(path, "r") as f:
            assert f.read() == "content here"


class TestReadWriteFile:
    def test_read_file(self, tmp_file):
        result = read_file(tmp_file)
        assert result["success"] is True
        assert result["content"] == "Hello"

    def test_read_nonexistent(self):
        result = read_file("/nonexistent/file")
        assert result["success"] is False

    def test_write_file_overwrite(self, tmp_file):
        result = write_file(tmp_file, "World", append=False)
        assert result["success"] is True
        with open(tmp_file, "r") as f:
            assert f.read() == "World"

    def test_write_file_append(self, tmp_file):
        result = write_file(tmp_file, " World", append=True)
        assert result["success"] is True
        with open(tmp_file, "r") as f:
            assert f.read() == "Hello World"


class TestRenameFile:
    def test_rename_file(self, tmp_dir):
        src = os.path.join(tmp_dir, "old.txt")
        dst = os.path.join(tmp_dir, "new.txt")
        with open(src, "w") as f:
            f.write("test")
        result = rename_file(src, dst)
        assert result["success"] is True
        assert not os.path.exists(src)
        assert os.path.exists(dst)


class TestSearchFiles:
    def test_search_files(self, tmp_dir):
        for name in ["a.txt", "b.log", "c.txt"]:
            with open(os.path.join(tmp_dir, name), "w") as f:
                f.write("test")
        result = search_files(tmp_dir, ".txt")
        assert result["success"] is True
        assert len(result["results"]) == 2

    def test_search_files_by_type(self, tmp_dir):
        os.makedirs(os.path.join(tmp_dir, "subdir"))
        with open(os.path.join(tmp_dir, "file.txt"), "w") as f:
            f.write("test")
        result = search_files(tmp_dir, "sub", search_type="folder")
        assert result["success"] is True
        assert len(result["results"]) == 1


class TestListFiles:
    def test_list_files(self, tmp_dir):
        for name in ["a.txt", "b.txt"]:
            with open(os.path.join(tmp_dir, name), "w") as f:
                f.write("test")
        os.makedirs(os.path.join(tmp_dir, "subdir"))
        result = list_files(tmp_dir)
        assert result["success"] is True
        assert len(result["files"]) == 3

    def test_list_nonexistent(self):
        result = list_files("/nonexistent/dir")
        assert result["success"] is False
