"""工具层测试：全部离线运行，不调用 API。"""

from agent.tools import calculator, get_current_time, read_file


class TestCalculator:
    def test_basic_arithmetic(self):
        assert calculator("(3+5)*2**10") == "(3+5)*2**10 = 8192"

    def test_functions(self):
        assert "10" in calculator("abs(-7) + max(1, 2, 3)")

    def test_rejects_import_injection(self):
        result = calculator("__import__('os')")
        assert "计算失败" in result

    def test_rejects_attribute_access(self):
        result = calculator("(1).__class__")
        assert "计算失败" in result

    def test_rejects_huge_exponent(self):
        result = calculator("2**99999")
        assert "计算失败" in result
        assert "指数过大" in result

    def test_rejects_name_node(self):
        result = calculator("x + 1")
        assert "计算失败" in result


class TestGetCurrentTime:
    def test_contains_local_and_utc(self):
        result = get_current_time()
        assert "本地时间" in result
        assert "UTC" in result


class TestReadFile:
    def test_reads_file_in_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path))
        (tmp_path / "hello.txt").write_text("你好，世界", encoding="utf-8")
        assert read_file("hello.txt") == "你好，世界"

    def test_rejects_path_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path / "ws"))
        (tmp_path / "ws").mkdir()
        (tmp_path / "secret.txt").write_text("机密", encoding="utf-8")
        result = read_file("../secret.txt")
        assert "错误" in result
        assert "机密" not in result

    def test_rejects_absolute_escape(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path / "ws"))
        (tmp_path / "ws").mkdir()
        result = read_file("C:/Windows/win.ini")
        assert "错误" in result

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path))
        result = read_file("不存在.txt")
        assert "不存在" in result

    def test_rejects_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_WORKSPACE", str(tmp_path))
        (tmp_path / "subdir").mkdir()
        result = read_file("subdir")
        assert "错误" in result
