import builtins
import io
import sys

from src.ui import tui


class TestCanUseArrowKeys:
    def test_returns_false_when_stdout_not_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert tui._can_use_arrow_keys() is False

    def test_returns_false_when_stdin_not_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert tui._can_use_arrow_keys() is False


class TestSelectOptionFallback:
    """非真 console 环境下的数字+回车选择"""

    def test_pick_first(self, monkeypatch, capsys):
        inputs = iter(["1"])
        monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
        idx = tui._select_option_fallback("title", ["a", "b", "c"], default=0)
        assert idx == 0

    def test_pick_last(self, monkeypatch, capsys):
        inputs = iter(["3"])
        monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
        idx = tui._select_option_fallback("title", ["a", "b", "c"], default=0)
        assert idx == 2

    def test_blank_returns_default(self, monkeypatch, capsys):
        inputs = iter([""])
        monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
        idx = tui._select_option_fallback("title", ["a", "b", "c"], default=1)
        assert idx == 1

    def test_invalid_then_valid(self, monkeypatch, capsys):
        inputs = iter(["abc", "9", "0", "2"])
        monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
        idx = tui._select_option_fallback("title", ["a", "b", "c"], default=0)
        assert idx == 1

    def test_eof_returns_none(self, monkeypatch, capsys):
        def raise_eof(_):
            raise EOFError
        monkeypatch.setattr(builtins, "input", raise_eof)
        assert tui._select_option_fallback("title", ["a", "b"], default=0) is None

    def test_ctrl_c_returns_none(self, monkeypatch, capsys):
        def raise_kbi(_):
            raise KeyboardInterrupt
        monkeypatch.setattr(builtins, "input", raise_kbi)
        assert tui._select_option_fallback("title", ["a", "b"], default=0) is None


class TestSelectOptionDispatch:
    """select_option 根据环境自动选择 arrow / fallback"""

    def test_uses_fallback_when_arrow_unavailable(self, monkeypatch):
        called = {"arrow": False, "fallback": False}

        def fake_arrow(*a, **kw):
            called["arrow"] = True
            return 0

        def fake_fallback(*a, **kw):
            called["fallback"] = True
            return 1

        monkeypatch.setattr(tui, "_can_use_arrow_keys", lambda: False)
        monkeypatch.setattr(tui, "_select_option_arrow", fake_arrow)
        monkeypatch.setattr(tui, "_select_option_fallback", fake_fallback)

        result = tui.select_option("t", ["x", "y"], default=0)
        assert result == 1
        assert called["fallback"] is True
        assert called["arrow"] is False

    def test_uses_arrow_when_available(self, monkeypatch):
        called = {"arrow": False, "fallback": False}

        def fake_arrow(*a, **kw):
            called["arrow"] = True
            return 0

        def fake_fallback(*a, **kw):
            called["fallback"] = True
            return 1

        monkeypatch.setattr(tui, "_can_use_arrow_keys", lambda: True)
        monkeypatch.setattr(tui, "_select_option_arrow", fake_arrow)
        monkeypatch.setattr(tui, "_select_option_fallback", fake_fallback)

        result = tui.select_option("t", ["x", "y"], default=0)
        assert result == 0
        assert called["arrow"] is True
        assert called["fallback"] is False

    def test_empty_options_returns_none(self):
        assert tui.select_option("t", [], default=0) is None
