# daybreak

[English](README_EN.md) | 中文

一个基于 **Claude API** 的命令行 LLM Agent：手写 agentic loop（流式输出）、
RAG 检索增强、多 Agent 编排、评估体系——不依赖 LangChain 等框架，
唯一第三方依赖是 Anthropic 官方 SDK，带你从零理解/扩展一个 AI Agent 的完整闭环。

## 功能

- 命令行 REPL 多轮对话，带上下文记忆
- **流式输出**：思维过程暗色实时流、正文逐字流出、工具调用可见
- **多 Agent 编排**：主 Agent 可通过 `delegate_task` 派生 researcher/coder
  专业子 Agent 执行独立子任务（深度上限防递归爆炸）
- 六个内置工具：
  - `get_current_time` —— 获取当前时间（本地 + UTC）
  - `calculator` —— 安全计算数学表达式（AST 白名单，不用 `eval`）
  - `read_file` —— 读取工作区内的文本文件（沙箱限制，防路径穿越）
  - `search_knowledge_base` —— 检索本地文档知识库（BM25 + 中文分词，带来源引用）
  - `list_documents` —— 查看知识库文档清单
  - `delegate_task` —— 派生子 Agent 执行调研/编码子任务
- RAG 检索增强：`knowledge/` 目录放入 `.md`/`.txt`/`.pdf` 文档即可被检索
- 评估体系：`python -m evals` 自动跑测试集，量化工具选择准确率
- 工程化：45 个单元测试（pytest）、ruff  lint、GitHub Actions CI、Docker 镜像
- 结构清晰，加新工具只需在 [daybreak/tools.py](daybreak/tools.py) 写一个函数

## 环境要求

- Python 3.10 或更高版本
- 一个 Anthropic API Key（[点此申请](https://platform.claude.com/)）

## 安装

```bash
# 1. 安装依赖
pip install anthropic

# 2.（可选）以可编辑模式安装本项目，之后可以直接用 daybreak 命令启动
pip install -e .
```

## 配置

**推荐方式：`.env` 文件**（一次配置，任何终端直接可用）

```bash
# 1. 复制模板
copy .env.example .env

# 2. 编辑 .env，填入你的凭证（二选一）：
#    官方 API：  ANTHROPIC_API_KEY=sk-ant-...
#    兼容网关：  ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN
```

`.env` 已被 `.gitignore` 忽略。已经通过系统环境变量设置的值优先，不会被 `.env` 覆盖。

也可以只用环境变量（仅对当前窗口有效）：

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-...

# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

| 环境变量 | 作用 | 默认值 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | 官方 Claude API 密钥 | 无 |
| `ANTHROPIC_AUTH_TOKEN` | 兼容网关的令牌（配合 `ANTHROPIC_BASE_URL`） | 无 |
| `AGENT_MODEL` | 使用的模型 | `claude-opus-5-5` |
| `AGENT_WORKSPACE` | `read_file` 工具的沙箱根目录 | 当前工作目录 |
| `AGENT_KNOWLEDGE_DIR` | RAG 知识库目录 | 项目下 `knowledge/` |

注意：SDK 的凭证解析顺序是 `ANTHROPIC_API_KEY` → `ANTHROPIC_AUTH_TOKEN` →
`ant auth login` 配置文件。如果你的 shell 里已经被其他工具注入了
`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`（例如某些 IDE 插件），它们会
抢在你的 key 之前生效，导致请求打到错误的端点。用官方 API 时请先清掉它们：

```bash
# PowerShell
Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

### 使用第三方 Anthropic 兼容网关（如 StepFun）

如果本机已设置 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`（SDK 会自动读取，
无需额外配置），只需把模型换成网关提供的 ID 即可：

```powershell
$env:AGENT_MODEL = "step-5-preview"
python -m daybreak
```

已验证 `api.stepfun.com/step_plan` 网关支持本项目的全部用法：基础对话、
Tool Runner 工具调用、`output_config.effort` 参数。

## 运行

```bash
# 在项目根目录下
python -m daybreak

# 或（如果执行过 pip install -e .）
daybreak
```

启动后试试：

```
you> 现在几点了？
you> 帮我算一下 (3+5)*2**10 等于多少
you> 读一下 README.md 的开头，总结这个项目
```

## 命令

| 命令 | 作用 |
| --- | --- |
| `/help` | 显示帮助 |
| `/tools` | 列出可用工具 |
| `/kb` | 查看知识库文档清单 |
| `/reindex` | 重建知识库索引（新增/修改文档后使用） |
| `/reset` | 清空对话上下文 |
| `/quit` | 退出（Ctrl+C / Ctrl+D 也可以） |

## 知识库（RAG）

把文档放进 `knowledge/` 目录（可用 `AGENT_KNOWLEDGE_DIR` 环境变量改指向），
支持 `.md` / `.txt` / `.pdf`，然后对 agent 提问即可——涉及文档内容的问题
会自动触发 `search_knowledge_base` 检索，回答附带来源文件名。

```text
you> 怎么添加自己的新工具？
daybreak> 添加工具只需要三步（来源：agent使用手册.md）：1. 写一个带类型注解和
       Python 函数；2. 加 @beta_tool 装饰器；3. 注册进 TOOLS 列表……
```

新增或修改文档后执行 `/reindex` 重建索引。

**检索管线**：文档加载（pypdf 解析 PDF）→ 按段落分块（500 字上限、
50 字重叠窗口，防止答案跨越块边界）→ jieba 中文分词 → BM25 排序取
top-3。检索层（`daybreak/rag/index.py`）与上层解耦，以后可平滑替换为
向量检索（embedding + 余弦相似度），工具层无需改动。

## 评估体系（Evals）

```bash
python -m evals                          # 跑全部用例
python -m evals --model step-5-preview   # 指定模型
```

对 [evals/cases.json](evals/cases.json) 中的每个用例自动提问并打分：

- **工具选择准确率**：期望的工具是否被调用（期望为空时要求零调用，防过度触发）
- **关键词命中率**：最终回答是否包含期望的关键词（如计算结果 8192）
- **综合通过率**：两者同时达标才算通过

每个用例独立上下文、互不污染；结果按时间戳存入 `evals/results/`，
支撑“改 prompt → 重跑评测 → 对比指标”的迭代闭环。当前基线：
**8/8 通过，工具选择准确率 100%**。

新增回归用例只需往 `cases.json` 里加一个对象：

```json
{
  "id": "my-case",
  "question": "你的问题",
  "expect_tools": ["calculator"],
  "expect_keywords": ["42"],
  "note": "这题测什么"
}
```

## 多 Agent 编排

主 Agent 持有 `delegate_task` 工具，可把独立子任务派发给专业子 Agent：

- **researcher**（研究型）：资料调研，结论结构化并注明来源
- **coder**（编码与技术型）：写代码、技术分析、方案取舍

```text
you> 派 researcher 调研知识库里 RAG 管线怎么实现的
daybreak> 💭 思考中: 用户要求派 researcher 子 agent 调研……
       🔧 调用工具: delegate_task (researcher)
       **结论：** 知识库的 RAG 管线是纯离线词法检索……
```

设计要点：

- 子 Agent 是独立实例：自有角色系统提示词、全新上下文（看不到主对话，
  所以任务描述必须自包含）、持有基础工具集
- **深度上限**：子 Agent 不再持有 `delegate_task`（`MAX_DELEGATE_DEPTH=1`），
  从机制上杜绝递归派生爆炸
- 新增角色：在 [daybreak/subagents.py](daybreak/subagents.py) 的 `ROLE_PROMPTS`
  里加一段系统提示词即可

## 测试与 CI

```bash
pip install pytest ruff
pytest -v          # 45 个单元测试，全部离线
ruff check .       # lint
```

测试覆盖：计算器安全边界（注入/大指数/属性访问）、文件沙箱（穿越/绝对路径/
目录/缺失）、分块器（重叠/硬切/上限不变式）、BM25（排序/停用词/零结果）、
评分逻辑（工具子集/零调用/关键词阈值）、Agent 构造与深度工具面。

CI（[.github/workflows/ci.yml](.github/workflows/ci.yml)）：push/PR 自动跑
ruff + pytest；评估套件因需要真实凭证，设为手动触发（workflow_dispatch），
在仓库 Secrets 配置凭证后运行。

## Docker

```bash
docker build -t daybreak .
docker run -it --env-file .env daybreak              # 交互式 REPL
docker run --rm --env-file .env daybreak python -m evals   # 容器内跑评估
```

## 项目结构

```
daybreak/
├── daybreak/
│   ├── __init__.py
│   ├── __main__.py    # python -m daybreak 入口
│   ├── cli.py         # REPL 主循环、流式渲染、错误处理
│   ├── core.py        # Agent 类：手写 agentic loop + 流式 + 历史管理
│   ├── tools.py       # 工具定义（@beta_tool）与注册表
│   ├── subagents.py   # 子 Agent 角色与派生
│   └── rag/           # RAG 知识库子系统
│       ├── loader.py    # 文档加载（.md/.txt/.pdf）
│       ├── chunker.py   # 段落分块 + 重叠窗口
│       ├── index.py     # BM25 检索（可替换为向量检索）
│       └── __init__.py  # KnowledgeBase 门面 + 单例
├── knowledge/         # 知识库文档目录（放入 .md/.txt/.pdf）
├── evals/             # 评估体系
│   ├── cases.json       # 测试集（问题 → 期望工具/关键词）
│   ├── __main__.py      # 评测执行器（python -m evals）
│   └── results/         # 按时间戳保存的历次评测结果
├── tests/             # pytest 单元测试（45 个，全离线）
├── .github/workflows/ci.yml
├── Dockerfile
└── pyproject.toml
```

## 如何添加自己的工具

打开 [daybreak/tools.py](daybreak/tools.py)，仿照现有工具写一个函数，加 `@beta_tool`
装饰器，并把它加进文件底部的 `BASE_TOOLS` 列表（所有 Agent 都会获得它；
若只给主 Agent 用，则加进 `TOOLS`）：

```python
@beta_tool
def get_weather(location: str) -> str:
    """查询某个城市的天气。

    Args:
        location: 城市名，例如 "北京"。
    """
    return f"{location}：晴，25℃"

BASE_TOOLS = [get_current_time, calculator, read_file, get_weather, ...]
```

工具的 JSON Schema 由函数签名和 docstring 自动生成，所以 docstring 的
Args 段要写清楚——模型靠它决定何时以及如何调用这个工具。

## 实现要点

- **手写 agentic loop + 流式**：`client.messages.stream` 逐事件消费，
  文本/思维增量经回调实时渲染；循环控制（tool_use 执行续跑、
  pause_turn 重发续跑、max_tokens 截断提示）完全自主
- **无状态 API + 完整 history**：每一轮都发送全部对话历史；assistant 消息
  必须完整追加 content blocks（含 thinking blocks），不能只存文本
- **多 Agent 深度控制**：主 Agent 持 delegate_task，子 Agent（depth=1）
  只持基础工具，从工具面杜绝递归派生
- **Opus 5.5**：thinking 自适应开启且不可关闭，思考深度用
  `output_config={"effort": ...}` 控制（默认 `medium`）
- **RAG 管线**：加载 → 分块（段落聚合 + 重叠窗口，块长硬上限）→
  jieba 分词 → BM25 检索，检索层可替换为向量实现
- **安全**：计算器走 AST 白名单；`read_file` 限制在沙箱根目录内；
  子 Agent 深度上限防派生爆炸

## 许可证

[MIT](LICENSE)。欢迎 Issue 和 PR，贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。
