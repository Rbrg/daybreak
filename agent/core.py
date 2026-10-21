"""Agent 核心：手写 agentic loop + 流式输出 + 多轮对话历史管理。

API 是无状态的——每一轮都把完整 history 发给服务端。assistant 消息必须原样
追加完整的 content blocks（其中可能包含 thinking blocks），不能只存文本。

这里手写 agentic loop（而非 SDK 的 Tool Runner），是为了拿到流式输出能力：
文本/思维增量通过回调实时推给调用方，循环本身完全可控。
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic

from .tools import BASE_TOOLS, TOOLS

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
DEFAULT_EFFORT = "medium"

# 子 Agent 派生深度上限：主 Agent(0) 可派生，子 Agent(1) 不再派生
MAX_DELEGATE_DEPTH = 1
# pause_turn 续跑次数上限，防止服务端反复暂停导致死循环
MAX_PAUSE_RESUMES = 5

# 项目根目录（agent 包的上一级）下的 .env 文件
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

SYSTEM_PROMPT = """你是一个运行在命令行中的 AI 助手，名叫 agent。

你可以使用以下工具来帮助用户：
- get_current_time：获取当前日期和时间
- calculator：计算数学表达式
- read_file：读取工作区内的文本文件
- search_knowledge_base：检索本地文档知识库（knowledge/ 目录）
- list_documents：查看知识库中有哪些文档
- delegate_task：把独立子任务派发给专业子 Agent（researcher 调研 / coder 编码）

工作守则：
- 用用户所用的语言回答。
- 回答简洁直接，不要复述工具已经给出的内容。
- 需要工具时就调用，不要凭空编造时间、计算结果或文件内容。
- 涉及文档、手册、资料的问题，优先用 search_knowledge_base 检索，
  并在回答中注明来源文件名；知识库没有的内容不要编造。
- 复杂任务可以分解：需要专门调研的派给 researcher，需要写代码/
  技术分析的派给 coder，然后综合子 Agent 的结论回答。
- 如果用户的问题超出了工具能力，直接说明，不要猜测。"""


def _load_dotenv() -> None:
    """把项目根目录 .env 文件里的键值载入环境变量。

    已存在的环境变量优先，不会被 .env 覆盖——这样临时用 $env: 设的变量
    仍然可以盖过 .env。支持 ``KEY=value``、引号包裹的值、# 注释和 export 前缀。
    """
    if not _ENV_FILE.is_file():
        return
    for raw_line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Agent:
    """一个基于 Claude Messages API 的命令行 Agent。

    Args:
        model: 模型 ID，默认读环境变量 AGENT_MODEL，再回退到 claude-opus-5-5。
        system_prompt: 系统提示词。
        max_tokens: 单次响应上限（非流式请求默认 16000）。
        effort: 思考深度，low/medium/high/xhigh/max，默认 medium。
        depth: 派生深度。0 为主 Agent（含 delegate_task 工具），
            达到 MAX_DELEGATE_DEPTH 的子 Agent 不再持有派生工具。
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = MAX_TOKENS,
        effort: str = DEFAULT_EFFORT,
        depth: int = 0,
    ) -> None:
        _load_dotenv()
        self._client: anthropic.Anthropic | None = None  # 懒加载：无凭证也能构造（便于测试）
        self.model = model or os.environ.get("AGENT_MODEL", DEFAULT_MODEL)
        base_prompt = system_prompt or SYSTEM_PROMPT
        # 模型对自身身份没有自省能力——把运行模型写进系统提示词，
        # 被问"你是什么模型"时才能如实回答（而非编造或拒答）
        self.system_prompt = (
            f"{base_prompt}\n\n你当前运行在模型 {self.model} 上，被问及时如实告知。"
        )
        self.max_tokens = max_tokens
        self.effort = effort
        self.depth = depth
        self.tools = TOOLS if depth < MAX_DELEGATE_DEPTH else BASE_TOOLS
        # 普通（非 beta）端点需要字典格式的工具参数；BetaFunctionTool 自带转换
        self._tool_params = [t.to_dict() for t in self.tools]
        self._tool_map = {t.name: t for t in self.tools}
        self.messages: list[dict] = []
        self.last_tool_calls: list[str] = []
        self.last_stop_reason: str | None = None
        self._prebuild_knowledge_base()

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def _prebuild_knowledge_base(self) -> None:
        """知识库目录存在时启动即建索引，让首问零等待、横幅可显示文档数。"""
        from .rag import get_knowledge_base

        kb = get_knowledge_base()
        if kb.root.is_dir():
            kb.build()

    def reindex(self) -> str:
        """重建知识库索引（新增/修改文档后调用），返回概况描述。"""
        from .rag import get_knowledge_base

        kb = get_knowledge_base()
        kb.build()
        return kb.describe()

    def reset(self) -> None:
        """清空对话历史，开始新会话。"""
        self.messages.clear()

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        tool = self._tool_map.get(name)
        if tool is None:
            return f"错误: 未知工具 {name!r}"
        try:
            result = tool.call(tool_input)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:
            return f"错误: 工具 {name} 执行失败: {exc}"

    def chat(
        self,
        user_text: str,
        on_text=None,
        on_thinking=None,
        on_tool=None,
    ) -> str:
        """发送一轮用户消息，驱动 agentic loop 直到模型给出最终回答。

        Args:
            on_text: 文本增量回调，签名 (delta: str) -> None，用于流式显示。
            on_thinking: 思维增量回调，签名同上。
            on_tool: 工具调用回调，签名 (name: str, tool_input: dict) -> None，
                在执行工具前触发。

        Returns:
            最终回答文本。每轮实际发生的工具调用记录在 self.last_tool_calls。
        """
        self.messages.append({"role": "user", "content": user_text})
        self.last_tool_calls = []
        self.last_stop_reason = None
        text_parts: list[str] = []
        pause_resumes = 0

        while True:
            # ---- 流式请求：增量推给回调，完整响应用于循环控制 ----
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                output_config={"effort": self.effort},
                system=self.system_prompt,
                tools=self._tool_params,
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    delta = event.delta
                    if delta.type == "thinking_delta" and on_thinking:
                        on_thinking(getattr(delta, "thinking", ""))
                    elif delta.type == "text_delta":
                        text_parts.append(delta.text)
                        if on_text:
                            on_text(delta.text)
                response = stream.get_final_message()

            self.last_stop_reason = response.stop_reason
            # 追加完整 content blocks（含 thinking blocks），不能只存文本
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "pause_turn":
                # 服务端暂停的长回合：带着已有 history 重发即续跑
                pause_resumes += 1
                if pause_resumes > MAX_PAUSE_RESUMES:
                    break
                continue

            if response.stop_reason == "max_tokens":
                break  # 输出被截断，返回已有内容，由调用方提示用户

            # ---- stop_reason == "tool_use"：执行工具并继续循环 ----
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                self.last_tool_calls.append(block.name)
                if on_tool:
                    on_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": self._execute_tool(block.name, block.input),
                })
            if not tool_results:
                break  # 没有可执行的工具，避免死循环
            self.messages.append({"role": "user", "content": tool_results})

        return "".join(text_parts)
