import json
import os
import pytest

from utils import log_action, get_recent_logs, get_log_path


@pytest.fixture(autouse=True)
def clean_logs():
    """测试后清理日志"""
    yield
    log_path = get_log_path()
    if log_path.exists():
        log_path.unlink()


class TestLogAction:
    def test_log_action_creates_file(self):
        log_action("test_action", {"key": "value"}, {"success": True})
        assert os.path.exists(get_log_path())

    def test_log_action_appends(self):
        log_action("action1", {}, {"success": True})
        log_action("action2", {}, {"success": True})

        logs = get_recent_logs(10)
        assert len(logs) >= 2
        # get_recent_logs 返回最新在前
        assert logs[0]["action_type"] == "action2"
        assert logs[1]["action_type"] == "action1"

    def test_log_entry_format(self):
        log_action("test_action", {"param": 123}, {"result": "ok"})
        logs = get_recent_logs(1)
        assert len(logs) == 1
        log = logs[0]
        assert "timestamp" in log
        assert log["action_type"] == "test_action"
        assert log["params"] == {"param": 123}
        assert log["result"] == {"result": "ok"}


class TestGetRecentLogs:
    def test_empty_logs(self):
        logs = get_recent_logs(10)
        assert logs == []

    def test_limit(self):
        for i in range(20):
            log_action(f"action_{i}", {}, {"success": True})
        logs = get_recent_logs(5)
        assert len(logs) == 5

    def test_order(self):
        for i in range(5):
            log_action(f"action_{i}", {}, {"success": True})
        logs = get_recent_logs(5)
        timestamps = [log["timestamp"] for log in logs]
        # get_recent_logs 返回最新在前
        assert timestamps == sorted(timestamps, reverse=True)
