"""命令行 REPL 交互界面（流式输出）。"""

from __future__ import annotations

import os
import sys

import anthropic

from .core import Agent
from .tools import TOOLS

HELP_TEXT = """可用命令：
  /help     显示本帮助
  /tools    列出可用工具
  /kb       查看知识库文档清单
  /reindex  重建知识库索引（新增/修改文档后使用）
  /reset    清空对话上下文，开始新会话
  /quit     退出（也可以用 Ctrl+C 或 Ctrl+D）"""

# ANSI：暗色（思维流）/ 重置
_DIM = "\033[2m"
_RESET = "\033[0m"


def _configure_streams() -> None:
    """管道场景下把标准输入/输出切换到 UTF-8。

    Windows 默认按本地代码页（如简体中文的 GBK）解码管道输入，来自 UTF-8
    源的多字节序列会被拆出代理字符（lone surrogate），后续 JSON 序列化请求体
    时直接崩溃。交互式控制台走 ReadConsoleW/WriteConsoleW，不受影响，不处理。
    """
    for stream in (sys.stdin, sys.stdout):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _enable_ansi_on_windows() -> None:
    """Win10+ 控制台默认不解析 ANSI 转义；os.system('') 触发 VT 模式启用。

    失败（旧系统）也无妨——只是没有暗色效果，文本照常输出。
    """
    if os.name == "nt":
        try:
            os.system("")
        except Exception:
            pass


class _StreamPrinter:
    """把流式增量渲染到终端：思维暗色、文本原色、工具调用一行提示。"""

    def __init__(self) -> None:
        self._thinking_started = False

    def on_thinking(self, delta: str) -> None:
        if not delta:
            return
        if not self._thinking_started:
            print(f"{_DIM}💭 思考中: ", end="", flush=True)
            self._thinking_started = True
        print(f"{_DIM}{delta}{_RESET}", end="", flush=True)

    def on_text(self, delta: str) -> None:
        if self._thinking_started:
            print()  # 思维结束后换行，正文另起
            self._thinking_started = False
        print(delta, end="", flush=True)

    def on_tool(self, name: str, tool_input: dict) -> None:
        if self._thinking_started:
            print()
            self._thinking_started = False
        brief = ""
        if name == "delegate_task":
            brief = f" ({tool_input.get('role', '')})"
        elif tool_input:
            first = next(iter(tool_input.values()))
            brief = f" ({str(first)[:30]})"
        print(f"{_DIM}🔧 调用工具: {name}{brief}{_RESET}", flush=True)


def _sanitize(text: str) -> str:
    """去掉解码过程中残留的代理字符，保证可以安全序列化进请求体。"""
    return text.encode("utf-8", "replace").decode("utf-8", "replace")


def _print_banner(agent: Agent) -> None:
    tool_names = "、".join(t.name for t in TOOLS)
    print("=" * 56)
    print("  daybreak —— 基于 Claude API 的命令行智能体")
    print(f"  模型: {agent.model}    工具: {tool_names}")
    try:
        from .rag import get_knowledge_base

        kb = get_knowledge_base()
        if not kb.is_empty:
            print(f"  {kb.describe().splitlines()[0]}")
    except Exception:
        pass  # 知识库不可用不影响主流程
    print("  输入 /help 查看命令，/quit 退出")
    print("=" * 56)


def _handle_command(command: str, agent: Agent) -> bool:
    """处理斜杠命令，返回 True 表示退出 REPL。"""
    if command in ("/quit", "/exit"):
        print("再见！")
        return True
    if command == "/help":
        print(HELP_TEXT)
    elif command == "/tools":
        for t in TOOLS:
            print(f"  - {t.name}: {t.description}")
    elif command == "/kb":
        try:
            from .rag import get_knowledge_base

            print(get_knowledge_base().describe())
        except Exception as exc:
            print(f"知识库状态获取失败: {exc}")
    elif command == "/reindex":
        try:
            print(f"已重建索引。{agent.reindex()}")
        except Exception as exc:
            print(f"重建索引失败: {exc}")
    elif command == "/reset":
        agent.reset()
        print("对话上下文已清空。")
    else:
        print(f"未知命令: {command}（输入 /help 查看可用命令）")
    return False


def main() -> None:
    _configure_streams()
    _enable_ansi_on_windows()

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("警告：未检测到 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN，调用 API 会失败。")
        print("      方法一：复制 .env.example 为 .env 并填入凭证（推荐，一次配置长期有效）")
        print("      方法二：$env:ANTHROPIC_API_KEY = \"sk-ant-...\"（仅当前窗口有效）")

    agent = Agent()
    _print_banner(agent)

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        user_input = _sanitize(user_input)
        if user_input.startswith("/"):
            if _handle_command(user_input, agent):
                break
            continue

        printer = _StreamPrinter()
        print("daybreak> ", end="", flush=True)
        try:
            reply = agent.chat(
                user_input,
                on_text=printer.on_text,
                on_thinking=printer.on_thinking,
                on_tool=printer.on_tool,
            )
        except KeyboardInterrupt:
            # 中断本次生成：如果历史里留下了孤立的 user 消息，先移除再继续
            print("\n（已中断本次生成）")
            if agent.messages and agent.messages[-1]["role"] == "user":
                agent.messages.pop()
            continue
        except anthropic.AuthenticationError:
            print("认证失败：请检查 ANTHROPIC_API_KEY 是否正确、是否有效。")
            continue
        except anthropic.RateLimitError:
            print("触发了 API 速率限制，请稍后再试。")
            continue
        except anthropic.APIConnectionError:
            print("网络错误：无法连接到 Claude API，请检查网络连接。")
            continue
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                print(f"Claude API 服务端错误（{exc.status_code}），请稍后再试。")
            elif exc.status_code == 404:
                print(f"模型不可用（404）：{exc.message}")
                print(f"      当前模型为 {agent.model}，可尝试用环境变量更换，例如：")
                print("      $env:AGENT_MODEL = \"step-5-preview\"")
            else:
                print(f"API 错误（{exc.status_code}）：{exc.message}")
            continue
        except Exception as exc:  # 保险丝：任何未预期错误都不应让 REPL 崩溃
            print(f"发生未知错误（{type(exc).__name__}）: {exc}")
            continue

        print()  # 流式输出结束后换行
        if agent.last_stop_reason == "max_tokens":
            print(f"{_DIM}（输出达到长度上限被截断，可让 agent「继续」或调大 max_tokens）{_RESET}")
        if not reply.strip():
            print("（本轮没有文本输出）")


if __name__ == "__main__":
    sys.exit(main())
