"""评估评分逻辑测试：纯函数，离线。"""

from evals.__main__ import KEYWORD_PASS_RATE, score_case


def _case(**kwargs):
    base = {"id": "t", "question": "q", "expect_tools": [], "expect_keywords": []}
    base.update(kwargs)
    return base


class TestToolSelection:
    def test_expected_tool_called(self):
        s = score_case(_case(expect_tools=["calculator"]), ["calculator"], "8192")
        assert s["tool_ok"] and s["passed"]

    def test_expected_tool_missing(self):
        s = score_case(_case(expect_tools=["calculator"]), ["get_current_time"], "")
        assert not s["tool_ok"] and not s["passed"]

    def test_extra_tools_still_pass_but_recorded(self):
        s = score_case(_case(expect_tools=["calculator"]), ["calculator", "read_file"], "")
        assert s["tool_ok"]
        assert s["extra_tools"] == ["read_file"]

    def test_empty_expectation_requires_zero_calls(self):
        s = score_case(_case(expect_tools=[]), [], "你好")
        assert s["tool_ok"] and s["passed"]

    def test_empty_expectation_with_calls_fails(self):
        s = score_case(_case(expect_tools=[]), ["calculator"], "8192")
        assert not s["tool_ok"] and not s["passed"]

    def test_multi_tool_subset(self):
        s = score_case(
            _case(expect_tools=["get_current_time", "calculator"]),
            ["get_current_time", "calculator"],
            "",
        )
        assert s["tool_ok"]


class TestKeywordScoring:
    def test_all_keywords_hit(self):
        s = score_case(_case(expect_keywords=["8192", "结果"]), [], "结果是 8192")
        assert s["kw_rate"] == 1.0

    def test_partial_keywords(self):
        s = score_case(_case(expect_keywords=["8192", "不存在"]), [], "8192")
        assert s["kw_rate"] == 0.5

    def test_no_keywords_not_scored(self):
        s = score_case(_case(expect_keywords=[]), [], "任意回答")
        assert s["kw_rate"] == 1.0

    def test_keyword_at_threshold_passes(self):
        # 命中率恰好等于阈值（0.5 >= 0.5）应判通过
        s = score_case(_case(expect_keywords=["甲", "乙"]), [], "只有甲")
        assert s["kw_rate"] == 0.5
        assert s["passed"]
        assert KEYWORD_PASS_RATE == 0.5
