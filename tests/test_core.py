"""Agent 核心与子 Agent 编排测试：不触发 API 调用（客户端懒加载）。"""

from agent.core import MAX_DELEGATE_DEPTH, Agent
from agent.subagents import ROLE_PROMPTS, spawn_subagent
from agent.tools import BASE_TOOLS, TOOLS


class TestAgentConstruction:
    def test_constructs_without_credentials(self):
        # 客户端懒加载：无凭证也能构造 Agent（测试与库复用场景）
        agent = Agent()
        assert agent.model
        assert agent.messages == []
        assert agent.last_tool_calls == []

    def test_model_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "test-model-x")
        assert Agent().model == "test-model-x"

    def test_explicit_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "env-model")
        assert Agent(model="explicit-model").model == "explicit-model"

    def test_reset_clears_history(self):
        agent = Agent()
        agent.messages.append({"role": "user", "content": "hi"})
        agent.reset()
        assert agent.messages == []


class TestToolSurfaceByDepth:
    def test_main_agent_has_delegate(self):
        agent = Agent(depth=0)
        names = {t.name for t in agent.tools}
        assert "delegate_task" in names
        assert len(agent.tools) == len(TOOLS)

    def test_subagent_lacks_delegate(self):
        agent = Agent(depth=MAX_DELEGATE_DEPTH)
        names = {t.name for t in agent.tools}
        assert "delegate_task" not in names
        assert names == {t.name for t in BASE_TOOLS}

    def test_tool_params_serializable(self):
        # 普通端点需要字典格式工具参数
        agent = Agent()
        assert all(isinstance(p, dict) and "name" in p for p in agent._tool_params)


class TestSubagents:
    def test_unknown_role_rejected_without_api(self):
        result = spawn_subagent("不存在的角色", "任务")
        assert "错误" in result
        assert "researcher" in result  # 提示可用角色

    def test_role_prompts_exist(self):
        assert set(ROLE_PROMPTS) == {"researcher", "coder"}
        assert all(p.strip() for p in ROLE_PROMPTS.values())
