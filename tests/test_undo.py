import os
import tempfile
import time
from pathlib import Path
import pytest

from file_ops import (
    move_file, copy_file, delete_file, create_folder, create_file,
    write_file, rename_file, extract_archive, create_archive, undo_last,
    get_undo_stack, clear_undo_stack, get_undo_history, batch_operations,
    set_active_session, cleanup_old_backups
)


@pytest.fixture(autouse=True)
def _clear_undo():
    """每个测试前清空全局撤销栈,避免相互污染"""
    clear_undo_stack()
    yield
    clear_undo_stack()


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(original_cwd)


class TestUndoBasic:
    def test_undo_stack_empty_initially(self):
        stack = get_undo_stack()
        assert len(stack) == 0

    def test_undo_when_nothing_to_undo(self):
        result = undo_last()
        assert not result["success"]


class TestUndoDeleteFile:
    def test_undo_delete_file(self, temp_workspace):
        # 创建测试文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("hello")
        assert test_file.exists()

        # 删除文件
        result = delete_file(str(test_file))
        assert result["success"]
        assert not test_file.exists()

        # 撤销删除
        undo_result = undo_last()
        assert undo_result["success"]
        assert test_file.exists()
        assert test_file.read_text() == "hello"

    def test_undo_delete_folder(self, temp_workspace):
        # 创建测试文件夹和文件
        test_folder = temp_workspace / "test_folder"
        test_folder.mkdir()
        test_file = test_folder / "test.txt"
        test_file.write_text("hello")
        assert test_folder.exists()

        # 删除文件夹
        result = delete_file(str(test_folder))
        assert result["success"]
        assert not test_folder.exists()

        # 撤销删除
        undo_result = undo_last()
        assert undo_result["success"]
        assert test_folder.exists()
        assert (test_folder / "test.txt").exists()


class TestUndoMove:
    def test_undo_move_file(self, temp_workspace):
        # 创建源文件
        src = temp_workspace / "src.txt"
        src.write_text("content")
        dst = temp_workspace / "dst.txt"

        # 移动文件
        result = move_file(str(src), str(dst))
        assert result["success"]
        assert not src.exists()
        assert dst.exists()

        # 撤销移动
        undo_result = undo_last()
        assert undo_result["success"]
        assert src.exists()
        assert not dst.exists()


class TestUndoRename:
    def test_undo_rename(self, temp_workspace):
        original = temp_workspace / "old.txt"
        original.write_text("data")
        new_name = temp_workspace / "new.txt"

        # 重命名
        result = rename_file(str(original), str(new_name))
        assert result["success"]
        assert not original.exists()
        assert new_name.exists()

        # 撤销重命名
        undo_result = undo_last()
        assert undo_result["success"]
        assert original.exists()
        assert not new_name.exists()


class TestUndoWrite:
    def test_undo_overwrite_file(self, temp_workspace):
        # 创建原始文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("original content")

        # 覆盖写入
        result = write_file(str(test_file), "new content", append=False)
        assert result["success"]
        assert test_file.read_text() == "new content"

        # 撤销写入
        undo_result = undo_last()
        assert undo_result["success"]
        assert test_file.read_text() == "original content"


class TestUndoCreate:
    def test_undo_create_file(self, temp_workspace):
        test_file = temp_workspace / "new_file.txt"
        assert not test_file.exists()

        # 创建文件
        result = create_file(str(test_file), "content")
        assert result["success"]
        assert test_file.exists()

        # 撤销创建
        undo_result = undo_last()
        assert undo_result["success"]
        assert not test_file.exists()

    def test_undo_create_folder(self, temp_workspace):
        test_folder = temp_workspace / "new_folder"
        assert not test_folder.exists()

        # 创建文件夹
        result = create_folder(str(test_folder))
        assert result["success"]
        assert test_folder.exists()

        # 撤销创建
        undo_result = undo_last()
        assert undo_result["success"]
        assert not test_folder.exists()


class TestUndoCopy:
    def test_undo_copy(self, temp_workspace):
        src = temp_workspace / "src.txt"
        src.write_text("content")
        dst = temp_workspace / "dst.txt"

        # 复制文件
        result = copy_file(str(src), str(dst))
        assert result["success"]
        assert dst.exists()

        # 撤销复制
        undo_result = undo_last()
        assert undo_result["success"]
        assert not dst.exists()
        assert src.exists()  # 源文件不应受影响


class TestMultiUndo:
    def test_multiple_undo(self, temp_workspace):
        # 操作1: 创建文件
        f1 = temp_workspace / "f1.txt"
        create_file(str(f1), "v1")

        # 操作2: 写入文件
        write_file(str(f1), "v2")

        # 操作3: 重命名
        f2 = temp_workspace / "f2.txt"
        rename_file(str(f1), str(f2))

        # 撤销3次
        undo_last()  # 撤销重命名
        assert f1.exists()
        assert not f2.exists()

        undo_last()  # 撤销写入
        assert f1.read_text() == "v1"

        undo_last()  # 撤销创建
        assert not f1.exists()

        # 没有更多可撤销
        result = undo_last()
        assert not result["success"]


class TestUndoCountArg:
    def test_undo_count_multiple(self, temp_workspace):
        f1 = temp_workspace / "a.txt"
        f2 = temp_workspace / "b.txt"
        f3 = temp_workspace / "c.txt"
        create_file(str(f1), "1")
        create_file(str(f2), "2")
        create_file(str(f3), "3")

        result = undo_last(count=3)
        assert result["success"] is True
        assert result["undone"] == 3
        assert not f1.exists() and not f2.exists() and not f3.exists()

    def test_undo_count_more_than_stack(self, temp_workspace):
        f1 = temp_workspace / "a.txt"
        create_file(str(f1), "1")

        result = undo_last(count=5)
        # 只有一个可撤销,但 count=5 不报错,只撤一个
        assert result["success"] is True
        assert result["undone"] == 1
        assert not f1.exists()

    def test_undo_count_invalid(self):
        assert undo_last(count=0)["success"] is False
        assert undo_last(count=-1)["success"] is False
        assert undo_last(count="abc")["success"] is False


class TestUndoHistory:
    def test_history_empty(self):
        h = get_undo_history()
        assert h["count"] == 0
        assert h["items"] == []

    def test_history_order_and_content(self, temp_workspace):
        f1 = temp_workspace / "a.txt"
        f2 = temp_workspace / "b.txt"
        create_file(str(f1), "1")
        create_file(str(f2), "2")

        h = get_undo_history()
        assert h["count"] == 2
        # 最近的在第一位
        assert h["items"][0]["type"] == "write_target"
        assert "b.txt" in h["items"][0]["description"]
        assert "a.txt" in h["items"][1]["description"]

    def test_history_limit(self, temp_workspace):
        for i in range(5):
            create_file(str(temp_workspace / f"f{i}.txt"))
        h = get_undo_history(limit=2)
        assert h["count"] == 5
        assert len(h["items"]) == 2


class TestBatchOperations:
    def test_batch_basic_create(self, temp_workspace):
        ops = [
            {"tool": "create_folder", "arguments": {"path": str(temp_workspace / "x")}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "x" / "a.txt"), "content": "A"}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "x" / "b.txt"), "content": "B"}},
        ]
        r = batch_operations(ops)
        assert r["success"] is True
        assert r["executed"] == 3
        assert (temp_workspace / "x" / "a.txt").read_text() == "A"
        assert (temp_workspace / "x" / "b.txt").read_text() == "B"

    def test_batch_pushes_single_undo_entry(self, temp_workspace):
        ops = [
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "u.txt")}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "v.txt")}},
        ]
        batch_operations(ops, label="setup")
        stack = get_undo_stack()
        assert len(stack) == 1
        assert stack[0]["type"] == "batch"
        assert stack[0]["label"] == "setup"
        assert len(stack[0]["sub_actions"]) == 2

    def test_batch_undo_rolls_back_all(self, temp_workspace):
        ops = [
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "x.txt"), "content": "1"}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "y.txt"), "content": "2"}},
            {"tool": "create_folder", "arguments": {"path": str(temp_workspace / "subdir")}},
        ]
        batch_operations(ops)
        assert (temp_workspace / "x.txt").exists()
        assert (temp_workspace / "y.txt").exists()
        assert (temp_workspace / "subdir").exists()

        undo_last()
        assert not (temp_workspace / "x.txt").exists()
        assert not (temp_workspace / "y.txt").exists()
        assert not (temp_workspace / "subdir").exists()

    def test_batch_stop_on_error(self, temp_workspace):
        ops = [
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "ok.txt")}},
            # 不存在的源,会失败
            {"tool": "move_file", "arguments": {"src": str(temp_workspace / "missing.txt"),
                                                  "dst": str(temp_workspace / "x.txt")}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "never.txt")}},
        ]
        r = batch_operations(ops, stop_on_error=True)
        assert r["success"] is False
        assert r["failures"] == 1
        assert r["halted_at"] == 1
        assert r["executed"] == 2  # 第三步未执行
        assert (temp_workspace / "ok.txt").exists()
        assert not (temp_workspace / "never.txt").exists()

    def test_batch_continue_on_error(self, temp_workspace):
        ops = [
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "a.txt")}},
            {"tool": "move_file", "arguments": {"src": str(temp_workspace / "missing.txt"),
                                                  "dst": str(temp_workspace / "x.txt")}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "c.txt")}},
        ]
        r = batch_operations(ops, stop_on_error=False)
        assert r["success"] is False
        assert r["failures"] == 1
        assert r["executed"] == 3
        assert (temp_workspace / "a.txt").exists()
        assert (temp_workspace / "c.txt").exists()

    def test_batch_undo_partial_success_ok(self, temp_workspace):
        # 即使部分成功,撤销也只回滚那部分成功的
        ops = [
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "ok.txt")}},
            {"tool": "move_file", "arguments": {"src": str(temp_workspace / "missing.txt"),
                                                  "dst": str(temp_workspace / "x.txt")}},
        ]
        batch_operations(ops, stop_on_error=False)
        assert (temp_workspace / "ok.txt").exists()
        undo_last()
        assert not (temp_workspace / "ok.txt").exists()

    def test_batch_rejects_disallowed_tool(self, temp_workspace):
        ops = [
            {"tool": "scan_disk", "arguments": {"path": str(temp_workspace)}},
        ]
        r = batch_operations(ops, stop_on_error=False)
        assert r["failures"] == 1
        assert "不允许" in r["results"][0]["error"]

    def test_batch_rejects_nested(self, temp_workspace):
        # 通过直接调用 TOOL_REGISTRY 模拟嵌套不会再走到 batch_operations,但显式参数检查保留
        ops = [
            {"tool": "batch_operations", "arguments": {"operations": []}},
        ]
        r = batch_operations(ops)
        # batch_operations 不在 _BATCH_ALLOWED_TOOLS 中
        assert r["success"] is False

    def test_batch_empty_rejected(self):
        r = batch_operations([])
        assert r["success"] is False

    def test_batch_with_count_undo(self, temp_workspace):
        # 单步 + batch + 单步,undo count=3 应一次清理所有
        f1 = temp_workspace / "single1.txt"
        create_file(str(f1))
        batch_operations([
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "b1.txt")}},
            {"tool": "create_file", "arguments": {"path": str(temp_workspace / "b2.txt")}},
        ])
        f2 = temp_workspace / "single2.txt"
        create_file(str(f2))

        r = undo_last(count=3)
        assert r["success"] is True
        assert r["undone"] == 3
        assert not f1.exists()
        assert not f2.exists()
        assert not (temp_workspace / "b1.txt").exists()
        assert not (temp_workspace / "b2.txt").exists()


class TestOverwriteUndo:
    def test_undo_create_file_overwrite_existing(self, temp_workspace):
        target = temp_workspace / "existing.txt"
        target.write_text("original")
        result = create_file(str(target), "new content")
        assert result["success"]
        assert target.read_text() == "new content"
        undo_last()
        assert target.read_text() == "original"

    def test_undo_move_restores_existing_dst(self, temp_workspace):
        src = temp_workspace / "src.txt"
        dst = temp_workspace / "dst.txt"
        src.write_text("src_data")
        dst.write_text("dst_data")
        move_file(str(src), str(dst))
        assert not src.exists()
        assert dst.read_text() == "src_data"
        undo_last()
        assert src.exists() and src.read_text() == "src_data"
        assert dst.exists() and dst.read_text() == "dst_data"


class TestSessionIsolation:
    def test_separate_sessions_have_separate_stacks(self, temp_workspace):
        # 会话 A 创建文件
        set_active_session("session_a")
        fa = temp_workspace / "a.txt"
        create_file(str(fa), "A")
        assert get_undo_history()["count"] == 1

        # 会话 B 创建文件
        set_active_session("session_b")
        fb = temp_workspace / "b.txt"
        create_file(str(fb), "B")
        assert get_undo_history()["count"] == 1

        # A 的栈不应受 B 影响
        set_active_session("session_a")
        assert get_undo_history()["count"] == 1
        undo_last()
        assert not fa.exists()

        # B 的栈仍然完好
        set_active_session("session_b")
        assert get_undo_history()["count"] == 1

    def test_clear_undo_stack_by_session(self, temp_workspace):
        set_active_session("s1")
        create_file(str(temp_workspace / "s1.txt"))
        set_active_session("s2")
        create_file(str(temp_workspace / "s2.txt"))

        clear_undo_stack("s1")
        set_active_session("s1")
        assert get_undo_history()["count"] == 0
        set_active_session("s2")
        assert get_undo_history()["count"] == 1

    def test_agent_set_session(self):
        from agent import FileAgent
        from providers.base import BaseLLMProvider

        class DummyProvider(BaseLLMProvider):
            def chat_with_tools(self, **kwargs):
                return {"content": "ok", "tool_calls": []}
            def chat(self, **kwargs):
                return "ok"

        agent = FileAgent(DummyProvider(), session_id="sess_1")
        assert agent.session_id == "sess_1"
        agent.set_session("sess_2")
        assert agent.session_id == "sess_2"


class TestCleanupOldBackups:
    def test_cleans_only_old_backups(self, tmp_path, monkeypatch):
        from file_ops import cleanup_old_backups
        # 伪造临时目录
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        old_dir = tmp_path / "toolsagent_backup_old"
        old_dir.mkdir()
        new_dir = tmp_path / "toolsagent_backup_new"
        new_dir.mkdir()
        other_dir = tmp_path / "other_backup"
        other_dir.mkdir()

        # 伪造旧目录的创建时间
        old_time = time.time() - 48 * 3600
        os.utime(old_dir, (old_time, old_time))

        count = cleanup_old_backups(max_age_hours=24)
        assert count == 1
        assert not old_dir.exists()
        assert new_dir.exists()
        assert other_dir.exists()


class TestUndoExtract:
    def test_undo_extract_zip(self, temp_workspace):
        import zipfile
        # 创建 zip 文件
        zip_path = temp_workspace / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        # 解压
        output = temp_workspace / "output"
        result = extract_archive(str(zip_path), str(output))
        assert result["success"]
        assert (output / "test.txt").exists()

        # 撤销解压
        undo_result = undo_last()
        assert undo_result["success"]
        assert not output.exists()

    def test_undo_extract_overwrite_existing(self, temp_workspace):
        import zipfile
        # 创建 zip 文件
        zip_path = temp_workspace / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "new content")

        # 先创建同名目录和文件
        output = temp_workspace / "output"
        output.mkdir()
        existing_file = output / "existing.txt"
        existing_file.write_text("old content")

        # 解压，不会覆盖现有文件
        result = extract_archive(str(zip_path), str(output))
        assert result["success"]
        assert (output / "test.txt").exists()
        assert existing_file.exists()

        # 撤销解压，删除新解压的内容，保留原有内容
        undo_result = undo_last()
        assert undo_result["success"]
        assert output.exists()
        assert existing_file.exists()
        assert existing_file.read_text() == "old content"
        assert not (output / "test.txt").exists()

    def test_undo_history_shows_extract(self, temp_workspace):
        import zipfile
        zip_path = temp_workspace / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        extract_archive(str(zip_path))

        history = get_undo_history()
        assert history["count"] == 1
        assert "解压" in history["items"][0]["description"]


class TestUndoCreateArchive:
    def test_undo_create_zip(self, temp_workspace):
        # 创建测试文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test content")
        assert test_file.exists()

        # 压缩
        zip_path = temp_workspace / "test.zip"
        result = create_archive(str(test_file), str(zip_path))
        assert result["success"]
        assert zip_path.exists()

        # 撤销压缩
        undo_result = undo_last()
        assert undo_result["success"]
        assert not zip_path.exists()

    def test_undo_history_shows_create_archive(self, temp_workspace):
        # 创建测试文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test")
        zip_path = temp_workspace / "archive.zip"

        create_archive(str(test_file), str(zip_path))

        history = get_undo_history()
        assert history["count"] == 1
        assert "压缩" in history["items"][0]["description"]

    def test_undo_overwrite_existing(self, temp_workspace):
        # 先创建一个已存在的压缩文件
        existing_zip = temp_workspace / "existing.zip"
        import zipfile
        with zipfile.ZipFile(existing_zip, "w") as zf:
            zf.writestr("old.txt", "old content")

        # 创建新的测试文件并压缩
        new_file = temp_workspace / "new.txt"
        new_file.write_text("new content")
        result = create_archive(str(new_file), str(existing_zip))
        assert result["success"]

        # 验证文件已被覆盖
        with zipfile.ZipFile(existing_zip, "r") as zf:
            assert "new.txt" in zf.namelist()

        # 撤销压缩，恢复原文件
        undo_result = undo_last()
        assert undo_result["success"]
        with zipfile.ZipFile(existing_zip, "r") as zf:
            assert "old.txt" in zf.namelist()
