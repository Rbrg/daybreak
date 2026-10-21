"""子 Agent 编排：主 Agent 通过 delegate_task 工具派生专业子 Agent。

每个子 Agent 是独立的 Agent 实例：自有系统提示词（角色定位）、
全新对话上下文（看不到主对话，任务必须自包含）、持有基础工具集。
深度上限由 core.MAX_DELEGATE_DEPTH 控制——子 Agent 不再持有
delegate_task，从机制上杜绝递归派生爆炸。
"""

from __future__ import annotations

from .core import Agent

RESEARCHER_PROMPT = """你是一个研究型子 Agent，代号 researcher。

独立完成一个调研子任务并输出结论。你可以使用工具检索知识库、
读取文件、进行计算。要求：
- 结论结构化：先给核心发现（要点列表），再给依据；
- 引用知识库内容时注明来源文件名；
- 检索不到的内容直说，不要编造；
- 你的输出会返回给主 Agent 汇总，不要向用户提问，不要寒暄。"""

CODER_PROMPT = """你是一个编码与技术型子 Agent，代号 coder。

独立完成一个编码或技术分析子任务。你可以使用工具检索知识库、
读取文件、进行计算。要求：
- 代码片段必须可直接运行，关键处加注释；
- 涉及多种方案时说明取舍和复杂度；
- 引用知识库内容时注明来源文件名；
- 你的输出会返回给主 Agent 汇总，不要向用户提问，不要寒暄。"""

ROLE_PROMPTS = {
    "researcher": RESEARCHER_PROMPT,
    "coder": CODER_PROMPT,
}


def spawn_subagent(role: str, task: str) -> str:
    """派生一个专业子 Agent 执行任务，返回其结论文本。"""
    prompt = ROLE_PROMPTS.get(role)
    if prompt is None:
        return f"错误: 未知角色 {role!r}，可用角色: {', '.join(ROLE_PROMPTS)}"

    # depth=1：子 Agent 不持有 delegate_task，无法再派生
    sub = Agent(system_prompt=prompt, depth=1)
    return sub.chat(task)
