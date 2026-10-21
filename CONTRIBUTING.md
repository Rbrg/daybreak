# 贡献指南

感谢关注本项目！

## 开发环境

```bash
# Python 3.10+
pip install -e .
pip install pytest ruff
```

## 提交前检查

```bash
pytest -v        # 45 个单元测试全部通过
ruff check .     # lint 零告警
```

如果改动涉及提示词或工具行为，再跑一次评估确认无回归：

```bash
python -m evals
```

## 如何贡献

- **加工具**：在 `agent/tools.py` 写一个 `@beta_tool` 函数，注册进 `BASE_TOOLS`
- **加评估用例**：往 `evals/cases.json` 里加一个对象（问题 → 期望工具/关键词）
- **加子 Agent 角色**：在 `agent/subagents.py` 的 `ROLE_PROMPTS` 里加一段系统提示词
- **换检索实现**：`agent/rag/index.py` 是唯一需要改的文件（接口不变）

## Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新功能    fix: 修 bug    docs: 文档
test: 测试      refactor: 重构  chore: 杂务
```

## 提 PR

Fork → 新建分支 → 提交 → 开 PR，说明改动动机与验证方式。
