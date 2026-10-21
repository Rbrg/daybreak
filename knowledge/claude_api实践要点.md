# Claude API 实践要点

本项目构建过程中验证过的 Messages API 关键机制，按主题整理。

## 工具调用循环（手写 agentic loop）

本项目手写 agentic loop 而非直接用 SDK 的 Tool Runner，目的是拿到
流式输出能力：`client.messages.stream` 逐事件消费，文本/思维增量
通过回调实时渲染，循环控制（tool_use 执行续跑、pause_turn 重发、
max_tokens 截断）完全自主。工具用 `@beta_tool` 装饰器定义，
但普通端点需要字典格式的工具参数——`BetaFunctionTool.to_dict()`
可以完成转换（直接传装饰器对象会报 not JSON serializable）。

循环里有两个容易错的处理：

1. assistant 消息必须追加完整的 content blocks（含 thinking blocks），
   只提取文本存储会导致多轮对话出错；
2. `pause_turn`（服务端暂停的长回合）需要带着已有 history 重发续跑，
   并设置次数上限防止死循环。

## thinking blocks 的完整回传

API 是无状态的，每一轮都要发送完整对话历史。assistant 消息必须
原样追加完整的 content blocks 列表，其中可能包含 thinking blocks
（思维块）。如果只提取文本存储，多轮对话会在后续请求中出错。
这是大多数教程会踩的坑。

## Opus 5.5 的 thinking 与 effort

claude-opus-5-5 的 thinking 不可关闭：发送 `{"type": "disabled"}`
或 `budget_tokens` 都会返回 400。正确做法是省略 thinking 参数
（adaptive 自动开启），用 `output_config={"effort": ...}` 控制
思考深度，可选 low/medium/high/xhigh/max，该模型默认 medium。

强制工具调用（`tool_choice` 为 any 或 tool）在 Opus 5.5 上会返回
400，应保持默认的 auto，通过提示词引导模型使用工具。

## 凭证解析顺序

SDK 按以下顺序解析凭证：`ANTHROPIC_API_KEY` →
`ANTHROPIC_AUTH_TOKEN` → `ant auth login` 配置文件。
`ANTHROPIC_BASE_URL` 可指向兼容网关。注意某些 IDE 插件会向终端
注入这两个变量，抢在用户自设的 key 之前生效。

## Windows 管道编码陷阱

Windows 下 Python 的标准输入默认按本地代码页（简体中文系统为
GBK）解码，且使用 surrogateescape 错误处理。当管道传入的是 UTF-8
字节时，多字节序列会被拆出代理字符（lone surrogate），后续
JSON 序列化请求体时直接抛出 UnicodeEncodeError。

解决方案：管道场景（`not sys.stdin.isatty()`）下把 stdin/stdout
reconfigure 为 UTF-8，并对输入做代理字符消毒作为兜底。
