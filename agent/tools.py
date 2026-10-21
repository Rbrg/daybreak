"""Agent 工具层。

用 ``@beta_tool`` 装饰器定义工具，JSON Schema 由函数签名和 docstring 自动生成，
因此每个工具的 docstring（尤其是 Args 段）要写清楚——模型靠它理解何时以及如何调用。

添加新工具的方式：写一个带类型注解和 docstring 的函数，加 ``@beta_tool``，
再把它加进本文件底部的 ``TOOLS`` 列表。
"""

from __future__ import annotations

import ast
import operator
import os
from datetime import datetime, timezone
from pathlib import Path

from anthropic import beta_tool

# read_file 的沙箱根目录：默认当前工作目录，可用环境变量 AGENT_WORKSPACE 覆盖
MAX_FILE_BYTES = 100_000


def _workspace_root() -> Path:
    return Path(os.environ.get("AGENT_WORKSPACE", Path.cwd())).resolve()


def _resolve_in_workspace(path: str) -> Path:
    """把用户给的路径解析到沙箱根目录内，拒绝一切逃逸（..、绝对路径、符号链接）。"""
    root = _workspace_root()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(
            f"路径 {path!r} 越出了工作区 {root}，已拒绝读取"
        )
    return candidate


# ---------------------------------------------------------------------------
# 工具 1：获取当前时间
# ---------------------------------------------------------------------------

@beta_tool
def get_current_time() -> str:
    """获取当前的日期和时间（本地时区与 UTC）。

    Returns:
        包含本地时间和 UTC 时间的 ISO 格式字符串。
    """
    try:
        now_local = datetime.now().astimezone()
        now_utc = datetime.now(timezone.utc)
        return f"本地时间: {now_local.isoformat()}\nUTC 时间: {now_utc.isoformat()}"
    except Exception as exc:  # 工具异常转为错误文本返回给模型，避免 REPL 崩溃
        return f"获取时间失败: {exc}"


# ---------------------------------------------------------------------------
# 工具 2：安全计算器（AST 白名单，禁用 eval）
# ---------------------------------------------------------------------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}
_MAX_EXPONENT = 1000


def _eval_node(node: ast.AST) -> float:
    """递归求值：只放行白名单内的节点，其余一律拒绝。"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"不支持的常量: {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOPS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if op_type is ast.Pow and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"指数过大（上限 {_MAX_EXPONENT}），已拒绝计算")
        return _ALLOWED_BINOPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARYOPS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        return _ALLOWED_UNARYOPS[op_type](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("只允许调用 abs / round / min / max")
        if node.keywords:
            raise ValueError("不支持关键字参数")
        args = [_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


@beta_tool
def calculator(expression: str) -> str:
    """计算一个数学表达式，支持 + - * / // % ** 、括号以及 abs/round/min/max 函数。

    Args:
        expression: 数学表达式，例如 "(3+5)*2**10" 或 "abs(-7) + max(1, 2, 3)"。
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree)
        return f"{expression.strip()} = {result}"
    except Exception as exc:
        return f"计算失败: {exc}（仅支持数学表达式，可用函数：abs/round/min/max）"


# ---------------------------------------------------------------------------
# 工具 3：沙箱内读取文件
# ---------------------------------------------------------------------------

@beta_tool
def read_file(path: str) -> str:
    """读取工作区内一个文本文件的内容（限制在 AGENT_WORKSPACE 根目录内，最大 100KB）。

    Args:
        path: 相对于工作区根目录的文件路径，例如 "README.md" 或 "src/main.py"。
    """
    try:
        candidate = _resolve_in_workspace(path)
        if not candidate.is_file():
            return f"错误: {path!r} 不存在或不是文件"
        if candidate.stat().st_size > MAX_FILE_BYTES:
            return f"错误: 文件超过 {MAX_FILE_BYTES} 字节上限，拒绝读取"
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"错误: {path!r} 不是 UTF-8 编码的文本文件，无法读取"
        if len(content) > MAX_FILE_BYTES:
            content = content[:MAX_FILE_BYTES] + "\n...（内容过长，已截断）"
        return content
    except ValueError as exc:
        return f"错误: {exc}"
    except Exception as exc:
        return f"读取失败: {exc}"


# ---------------------------------------------------------------------------
# 工具 4/5：知识库检索（RAG）
# ---------------------------------------------------------------------------

@beta_tool
def search_knowledge_base(query: str) -> str:
    """在本地文档知识库中检索与问题相关的内容片段，结果带来源标注。

    涉及项目文档、使用手册、技术资料的问题应优先使用本工具，
    回答时必须注明内容来源（文件名）。

    Args:
        query: 检索问题或关键词，例如 "如何添加新工具" 或 "thinking blocks 注意事项"。
    """
    try:
        from .rag import get_knowledge_base

        kb = get_knowledge_base()
        if kb.is_empty:
            return (
                f"知识库为空（目录: {kb.root}）。"
                "请把 .md/.txt/.pdf 文档放入该目录后用 /reindex 重建索引。"
            )
        results = kb.search(query, top_k=3)
        if not results:
            return "知识库中没有找到与该问题相关的内容，请换用其他关键词或工具。"
        parts = []
        for i, (chunk, _score) in enumerate(results, 1):
            parts.append(f"[{i}] 来源: {chunk.source}\n{chunk.text}")
        return "\n\n---\n\n".join(parts)
    except Exception as exc:
        return f"检索失败: {exc}"


@beta_tool
def list_documents() -> str:
    """列出知识库中已索引的文档清单（文件名与分块数量）。"""
    try:
        from .rag import get_knowledge_base

        return get_knowledge_base().describe()
    except Exception as exc:
        return f"获取文档清单失败: {exc}"


# ---------------------------------------------------------------------------
# 工具 6：子 Agent 派生（多 Agent 编排）
# ---------------------------------------------------------------------------

@beta_tool
def delegate_task(role: str, task: str) -> str:
    """把独立子任务派发给专业子 Agent 执行，返回其结论。

    适合复杂任务的分解：需要多角度资料调研的派给 researcher，
    需要写代码或技术分析的派给 coder，然后综合结论回答用户。
    子 Agent 看不到主对话上下文，task 必须是自包含的完整描述。

    Args:
        role: 子 Agent 类型，"researcher"（资料调研）或 "coder"（编码与技术）。
        task: 自包含的子任务描述，包含背景、目标、输出要求。
    """
    try:
        from .subagents import spawn_subagent

        return spawn_subagent(role, task)
    except Exception as exc:
        return f"子 Agent 执行失败: {exc}"


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

# 基础工具：所有 Agent（含子 Agent）都持有
BASE_TOOLS = [
    get_current_time,
    calculator,
    read_file,
    search_knowledge_base,
    list_documents,
]

# 完整工具集：仅主 Agent 持有（子 Agent 到 MAX_DELEGATE_DEPTH 即不再派生）
TOOLS = BASE_TOOLS + [delegate_task]
