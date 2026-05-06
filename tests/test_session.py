import os
import json
import shutil
import pytest

from session import (
    save_session, load_session, list_sessions, delete_session,
    generate_session_id, get_session_dir
)


@pytest.fixture(autouse=True)
def clean_sessions():
    """清理测试会话"""
    session_dir = get_session_dir()
    yield
    for f in session_dir.glob("test_*.json"):
        f.unlink(missing_ok=True)


class TestGenerateSessionId:
    def test_unique_ids(self):
        ids = set()
        for _ in range(50):
            sid = generate_session_id()
            assert sid not in ids
            ids.add(sid)

    def test_format(self):
        sid = generate_session_id()
        parts = sid.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert parts[2].isdigit() and len(parts[2]) >= 10  # 纳秒后缀


class TestSaveLoadSession:
    def test_save_and_load(self):
        sid = "test_" + generate_session_id()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
        result = save_session(sid, messages)
        assert result is True

        loaded = load_session(sid)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"

    def test_load_nonexistent(self):
        loaded = load_session("nonexistent_session_id")
        assert loaded is None


class TestListSessions:
    def test_list_sessions(self):
        sid1 = "test_" + generate_session_id()
        sid2 = "test_" + generate_session_id()
        save_session(sid1, [{"role": "user", "content": "a"}])
        save_session(sid2, [{"role": "user", "content": "b"}])

        sessions = list_sessions()
        test_sessions = [s for s in sessions if s["id"].startswith("test_")]
        assert len(test_sessions) >= 2


class TestDeleteSession:
    def test_delete_session(self):
        sid = "test_" + generate_session_id()
        save_session(sid, [{"role": "user", "content": "test"}])
        assert os.path.exists(get_session_dir() / f"{sid}.json")

        result = delete_session(sid)
        assert result is True
        assert not os.path.exists(get_session_dir() / f"{sid}.json")

    def test_delete_nonexistent(self):
        result = delete_session("nonexistent_session_id")
        assert result is False
