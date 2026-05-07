import os
import tempfile
import shutil
import pytest

from file_ops import (
    move_file, copy_file, delete_file, create_folder, create_file,
    read_file, write_file, rename_file, search_files, list_files, scan_disk,
    extract_archive, create_archive
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
        result = search_files(pattern=".txt", path=tmp_dir)
        assert result["success"] is True
        assert len(result["results"]) == 2

    def test_search_files_by_type(self, tmp_dir):
        os.makedirs(os.path.join(tmp_dir, "subdir"))
        with open(os.path.join(tmp_dir, "file.txt"), "w") as f:
            f.write("test")
        result = search_files(pattern="sub", path=tmp_dir, search_type="folder")
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


class TestScanDisk:
    def test_empty_dir(self, tmp_dir):
        result = scan_disk(tmp_dir)
        assert result["success"] is True
        assert result["count"] >= 1  # 至少包含自身

    def test_nested_sizes(self, tmp_dir):
        # dir_a: 100B, dir_b: 200B
        for name, size in [("dir_a", 100), ("dir_b", 200)]:
            d = os.path.join(tmp_dir, name)
            os.makedirs(d)
            with open(os.path.join(d, "file.txt"), "w") as f:
                f.write("x" * size)
        result = scan_disk(tmp_dir)
        assert result["success"] is True
        names = {item["path"]: item["size_bytes"] for item in result["items"]}
        assert names[os.path.join(tmp_dir, "dir_b")] == 200
        assert names[os.path.join(tmp_dir, "dir_a")] == 100
        # 根目录总大小 = 300
        assert names[tmp_dir] == 300

    def test_max_depth(self, tmp_dir):
        deep = os.path.join(tmp_dir, "a", "b", "c")
        os.makedirs(deep)
        with open(os.path.join(deep, "deep.txt"), "w") as f:
            f.write("x")
        result = scan_disk(tmp_dir, max_depth=2)
        assert result["success"] is True
        paths = [item["path"] for item in result["items"]]
        assert deep not in paths

    def test_max_results(self, tmp_dir):
        for i in range(20):
            d = os.path.join(tmp_dir, f"dir_{i}")
            os.makedirs(d)
            with open(os.path.join(d, "f.txt"), "w") as f:
                f.write("x")
        result = scan_disk(tmp_dir, max_results=5)
        assert result["success"] is True
        assert result["truncated"] is True
        assert result["count"] == 5

    def test_min_size(self, tmp_dir):
        d1 = os.path.join(tmp_dir, "small")
        d2 = os.path.join(tmp_dir, "large")
        os.makedirs(d1)
        os.makedirs(d2)
        with open(os.path.join(d1, "a.txt"), "w") as f:
            f.write("x" * 10)
        with open(os.path.join(d2, "b.txt"), "w") as f:
            f.write("x" * 1000)
        result = scan_disk(tmp_dir, min_size=500)
        assert result["success"] is True
        names = {item["path"] for item in result["items"]}
        assert os.path.join(tmp_dir, "small") not in names
        assert os.path.join(tmp_dir, "large") in names

    def test_nonexistent(self):
        result = scan_disk("/nonexistent/scan")
        assert result["success"] is False


class TestExtractArchive:
    def test_extract_zip(self, tmp_dir):
        import zipfile
        # 创建测试 zip 文件
        zip_path = os.path.join(tmp_dir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "Hello World!")
            zf.writestr("subdir/file.txt", "Nested file!")

        output_path = os.path.join(tmp_dir, "extracted")
        result = extract_archive(zip_path, output_path)
        assert result["success"] is True
        assert os.path.exists(os.path.join(output_path, "test.txt"))
        assert os.path.exists(os.path.join(output_path, "subdir", "file.txt"))

    def test_extract_zip_default_path(self, tmp_dir):
        import zipfile
        zip_path = os.path.join(tmp_dir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "Hello World!")

        result = extract_archive(zip_path)
        assert result["success"] is True
        expected_path = os.path.join(tmp_dir, "test")
        assert os.path.exists(expected_path)
        assert os.path.exists(os.path.join(expected_path, "test.txt"))

    def test_extract_tar_gz(self, tmp_dir):
        import tarfile
        tar_path = os.path.join(tmp_dir, "test.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            test_file = os.path.join(tmp_dir, "temp_test.txt")
            with open(test_file, "w") as f:
                f.write("Tar GZ test")
            tf.add(test_file, arcname="test.txt")
            os.remove(test_file)

        output_path = os.path.join(tmp_dir, "extracted_tar")
        result = extract_archive(tar_path, output_path)
        assert result["success"] is True
        assert os.path.exists(os.path.join(output_path, "test.txt"))

    def test_extract_invalid_format(self, tmp_dir):
        invalid_path = os.path.join(tmp_dir, "invalid.xyz")
        with open(invalid_path, "w") as f:
            f.write("Invalid format")

        result = extract_archive(invalid_path)
        assert result["success"] is False
        assert "不支持" in result["error"]

    def test_extract_nonexistent(self):
        result = extract_archive("/nonexistent/archive.zip")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_extract_rar_support_info(self, tmp_dir):
        # 创建一个假的 .rar 文件（不是真正的 RAR，只是为了测试格式检测）
        rar_path = os.path.join(tmp_dir, "test.rar")
        with open(rar_path, "w") as f:
            f.write("fake rar file")

        # 尝试解压，会检查 RAR 支持
        result = extract_archive(rar_path)
        # 如果 rarfile 不可用或系统没有 unrar，会返回相应的错误
        # 我们不一定要它成功解压，只是验证错误信息是合理的
        assert "RAR" in result["error"] or not result["success"]


class TestCreateArchive:
    def test_create_zip_single_file(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("Test content")

        # 压缩
        archive_path = os.path.join(tmp_dir, "test.zip")
        result = create_archive(src_file, archive_path)
        assert result["success"] is True
        assert os.path.exists(archive_path)

        # 验证压缩文件包含正确内容
        import zipfile
        with zipfile.ZipFile(archive_path, "r") as zf:
            assert "test.txt" in zf.namelist()
            assert zf.read("test.txt") == b"Test content"

    def test_create_zip_multiple_files(self, tmp_dir):
        # 创建测试文件
        file1 = os.path.join(tmp_dir, "file1.txt")
        file2 = os.path.join(tmp_dir, "file2.txt")
        with open(file1, "w") as f:
            f.write("Content 1")
        with open(file2, "w") as f:
            f.write("Content 2")

        # 压缩
        archive_path = os.path.join(tmp_dir, "multi.zip")
        result = create_archive([file1, file2], archive_path)
        assert result["success"] is True
        assert os.path.exists(archive_path)

        # 验证
        import zipfile
        with zipfile.ZipFile(archive_path, "r") as zf:
            assert "file1.txt" in zf.namelist()
            assert "file2.txt" in zf.namelist()

    def test_create_zip_folder(self, tmp_dir):
        # 创建测试文件夹
        folder = os.path.join(tmp_dir, "test_dir")
        os.makedirs(folder)
        file1 = os.path.join(folder, "a.txt")
        file2 = os.path.join(folder, "sub", "b.txt")
        os.makedirs(os.path.dirname(file2))
        with open(file1, "w") as f:
            f.write("A content")
        with open(file2, "w") as f:
            f.write("B content")

        # 压缩
        archive_path = os.path.join(tmp_dir, "folder.zip")
        result = create_archive(folder, archive_path)
        assert result["success"] is True

        # 验证
        import zipfile
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            assert any("a.txt" in n for n in names)
            assert any("b.txt" in n for n in names)

    def test_create_tar_gz(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("Tar content")

        # 压缩
        archive_path = os.path.join(tmp_dir, "test.tar.gz")
        result = create_archive(src_file, archive_path)
        assert result["success"] is True
        assert os.path.exists(archive_path)

    def test_create_tgz(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("TGZ content")

        # 压缩
        archive_path = os.path.join(tmp_dir, "test.tgz")
        result = create_archive(src_file, archive_path)
        assert result["success"] is True

    def test_create_tar_bz2(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("BZ2 content")

        # 压缩
        archive_path = os.path.join(tmp_dir, "test.tar.bz2")
        result = create_archive(src_file, archive_path)
        assert result["success"] is True

    def test_create_with_format_param(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("Format test")

        # 使用 format 参数，文件没有后缀
        archive_path = os.path.join(tmp_dir, "archive")
        result = create_archive(src_file, archive_path, format="zip")
        assert result["success"] is True

    def test_create_invalid_format(self, tmp_dir):
        # 创建测试文件
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("test")

        # 尝试使用不支持的格式
        archive_path = os.path.join(tmp_dir, "test.xyz")
        result = create_archive(src_file, archive_path)
        assert result["success"] is False
        assert "不支持" in result["error"]

    def test_create_nonexistent_source(self, tmp_dir):
        # 尝试压缩不存在的文件
        archive_path = os.path.join(tmp_dir, "test.zip")
        result = create_archive("/nonexistent/file", archive_path)
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_create_rar_support_check(self, tmp_dir):
        # 测试 RAR 格式支持检查（不依赖真实的 RAR 工具）
        src_file = os.path.join(tmp_dir, "test.txt")
        with open(src_file, "w") as f:
            f.write("Test content")

        archive_path = os.path.join(tmp_dir, "test.rar")
        result = create_archive(src_file, archive_path)

        # 由于系统可能没有安装 RAR 工具，这里可能会失败，但我们可以验证错误信息的合理性
        if result["success"]:
            # 如果成功了，验证是 RAR 文件
            assert os.path.exists(archive_path)
        else:
            # 如果失败了，应该是关于 RAR 工具的提示
            assert "RAR" in result["error"]
