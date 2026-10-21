# daybreak 使用手册

## 快速开始

agent 是一个基于 Claude API 的命令行 LLM 智能体。启动前需要配置凭证：
推荐把 `.env.example` 复制为 `.env` 并填入令牌，这样任何终端直接运行
`python -m daybreak` 即可，无需每次设置环境变量。

如果使用官方 Anthropic API，在 `.env` 中设置 `ANTHROPIC_API_KEY`；
如果使用 StepFun 等 Anthropic 兼容网关，则设置 `ANTHROPIC_BASE_URL` 和
`ANTHROPIC_AUTH_TOKEN`，并把 `AGENT_MODEL` 改为网关提供的模型 ID
（例如 `step-5-preview`）。

## 内置命令

REPL 启动后可以使用以下斜杠命令：

- `/help` 显示全部命令的帮助
- `/tools` 列出当前可用的工具及其说明
- `/kb` 查看知识库中的文档清单和分块数量
- `/reindex` 重建知识库索引；往 knowledge/ 目录新增或修改文档后，
  需要执行这个命令才能让新内容可被检索到
- `/reset` 清空对话上下文，开始全新会话
- `/quit` 退出程序，Ctrl+C 或 Ctrl+D 也可以退出

## 如何添加自己的工具

添加工具只需要三步，全部在 `daybreak/tools.py` 中完成：

1. 写一个带类型注解和 docstring 的普通 Python 函数；
2. 给它加上 `@beta_tool` 装饰器；
3. 把函数名加进文件底部的 `BASE_TOOLS` 列表（所有 Agent 都会获得它；
   若只给主 Agent 用，则加进 `TOOLS`）。

工具的 JSON Schema 由函数签名和 docstring 自动生成，其中 docstring 的
Args 段会被模型用来理解参数含义，所以必须写清楚。例如：

```python
@beta_tool
def get_weather(location: str) -> str:
    """查询某个城市的天气。

    Args:
        location: 城市名，例如 "北京"。
    """
    return f"{location}：晴，25℃"
```

工具函数内部应该自行 try/except 并返回错误字符串，这样工具出错时
模型能看到错误信息并换一种方式回答，而不会让整个 REPL 崩溃。

## 知识库（RAG）使用说明

知识库目录默认为项目根目录下的 `knowledge/`，可用环境变量
`AGENT_KNOWLEDGE_DIR` 指向其他目录。支持 `.md`、`.txt`、`.pdf`
三种格式，PDF 通过 pypdf 按页抽取文本。

检索采用 BM25 词法检索（jieba 中文分词），不依赖 embedding 模型，
完全离线可用。文档会被按段落切成不超过 500 字的块，块之间保留
50 字重叠窗口，避免答案跨越块边界时检索不到。

向 agent 提问时，涉及文档内容的问题应优先触发
`search_knowledge_base` 工具，回答会附带来源文件名，方便核对。
