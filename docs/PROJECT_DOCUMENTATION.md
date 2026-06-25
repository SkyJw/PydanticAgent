# 底软问题辅助定位 Agent 项目文档

## 1. 项目定位

本项目是一个基于 Textual、Typer、Pydantic AI 和 Pydantic 的 CLI/TUI agent，用于辅助华为光传送底软问题定位工作。

当前版本聚焦三个核心能力：

- 识别用户输入意图：区分闲聊和问题定位。
- 对问题定位请求抽取结构化上下文。
- 通过 CLI 或 Textual TUI 输出定位建议，并在 TUI 中流式展示大模型回答。

当前阶段不会执行真实 SSH 操作，也不会假装读取日志。它只基于用户输入和抽取出的结构化信息给出定位建议。后续可以在现有 runner 后面接入只读 SSH、日志拉取、grep 分析、报告生成等工具能力。

## 2. 技术栈

- Python 3.11+
- Pydantic：结构化数据模型和校验
- Pydantic Settings：环境变量和 `.env` 配置
- Pydantic AI：大模型 agent、结构化输出、流式输出
- Textual：终端 TUI 界面
- Typer：CLI 命令入口
- Rich：CLI 输出面板
- pytest：测试
- Ruff：lint
- uv：依赖管理和运行

## 3. 目录结构

```text
.
├── AGENTS.md
├── .env.example
├── README.md
├── docs/
│   └── PROJECT_DOCUMENTATION.md
├── pyproject.toml
├── src/
│   └── pydantic_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── agent.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       └── tui.py
├── tests/
│   ├── test_agent.py
│   └── test_tui.py
└── uv.lock
```

## 4. 模块说明

### `src/pydantic_agent/config.py`

负责读取运行配置。

仓库根目录提供 `.env.example`，包含当前默认配置项和常见
OpenAI-compatible 服务商 base URL 示例。首次配置时可复制为 `.env`
后按需修改；`.env` 会被 `.gitignore` 忽略，不要提交包含真实 API key
或其他敏感信息的本地配置文件。

主要配置项：

- `PYDANTIC_AGENT_MODEL_PROVIDER`
  - `openai-compatible`：默认模式，使用 OpenAI-compatible Chat Completions 接口。
  - `pydantic-ai`：将 `PYDANTIC_AGENT_MODEL` 作为 Pydantic AI 原生模型字符串透传。
- `PYDANTIC_AGENT_MODEL`
  - 在 `openai-compatible` 模式下表示模型名，例如 `deepseek-chat`。
  - 在 `pydantic-ai` 模式下表示完整模型字符串，例如 `openai:gpt-5.2`。
- `PYDANTIC_AGENT_STRUCTURED_OUTPUT_MODE`
  - 结构化输出模式，默认 `auto`。
  - `auto`：按 `native -> tool -> prompted` 顺序尝试，当前模式超时或失败后自动降级。
  - `native`：使用模型原生 structured output / JSON schema。
  - `tool`：使用 tool calling 返回 Pydantic 结构化结果。
  - `prompted`：通过 prompt 要求模型返回可解析 JSON，兼容性最好。
- `PYDANTIC_AGENT_REQUEST_TIMEOUT_SECONDS`
  - 每次大模型请求尝试的超时时间，默认 `7` 秒。
- `PYDANTIC_AGENT_MODEL_RETRIES`
  - Pydantic AI 模型调用、结构化输出校验、工具调用等可重试环节的最大重试次数，默认 `3` 次。
  - 所有 `Agent` 构造、非流式 `run()` 和流式 `run_stream()` 调用都会显式使用该限制，避免调试时因无限或过多重试触发服务商限流。
- `PYDANTIC_AGENT_OPENAI_BASE_URL`
  - OpenAI-compatible 服务商 base URL。
  - 空字符串会被自动视为未配置。
- `PYDANTIC_AGENT_OPENAI_API_KEY`
  - OpenAI-compatible 服务商 API key。
  - 使用 `SecretStr` 保存，避免意外 repr 泄露。
- `PYDANTIC_AGENT_MOCK`
  - 设置为 true 时不调用模型，返回确定性 mock 输出。

### `src/pydantic_agent/models.py`

定义核心数据结构。

`IntentType`：

- `chat`
- `troubleshooting`

`IntentClassification`：

- `intent`
- `confidence`
- `reason`

`TroubleshootingContext`：

- `log_path`
- `network_element_ip`
- `username`
- `password`
- `ssh_ip`
- `problem_description`

该模型提供两个重要方法：

- `missing_fields()`：返回缺失字段的中文名称。
- `to_markdown()`：生成面向 CLI/TUI 展示的结构化 Markdown，并自动脱敏密码。

`AgentRunResult`：

- `status`
- `output`
- `model`
- `intent`
- `intent_reason`
- `troubleshooting_context`
- `started_at`
- `finished_at`

### `src/pydantic_agent/agent.py`

核心 runner：`ProblemLocatorAgentRunner`。

主要职责：

- 构造模型对象。
- 识别意图。
- 抽取问题定位上下文。
- 根据意图路由：
  - 闲聊：直接回答。
  - 问题定位：抽取字段后输出定位建议。
- 支持非流式 `handle_request()`。
- 支持流式 `stream_request()`。
- 支持 mock 模式。

关键方法：

- `build_model()`
  - `openai-compatible` 模式下返回 `OpenAIChatModel`。
  - `pydantic-ai` 模式下返回原始模型字符串。
- `classify_intent()`
  - 使用 Pydantic AI 的结构化输出返回 `IntentClassification`。
- `extract_troubleshooting_context()`
  - 使用 Pydantic AI 的结构化输出返回 `TroubleshootingContext`。
- 结构化输出模式
  - `auto` 模式优先尝试 `native`，失败或超时后尝试 `tool`，最后回退到
    `prompted`。
  - 每次尝试都受 `request_timeout_seconds` 限制，避免内网兼容接口长时间卡住。
- 重试限制
  - 所有 Pydantic AI `Agent` 都按 `model_retries` 构造。
  - 每次 `run()` / `run_stream()` 也会显式传入 `model_retries`，统一限制模型输出、结构化校验和工具调用等可重试路径的次数。
- `_build_troubleshooting_prompt()`
  - 生成定位建议阶段的提示词。
  - 会排除 `password` 字段，并对问题描述里的密码文本进行脱敏。
- `_mock_handle_request()`
  - 不调用大模型，用规则和正则做基本意图识别和字段抽取。

### `src/pydantic_agent/cli.py`

Typer CLI 入口。

可用命令：

```powershell
uv run pa-agent run "请定位问题，网元 192.168.1.10 业务中断，日志路径 /var/log/otn/fault.log"
uv run pa-agent tui
```

`run` 支持临时覆盖模型配置：

```powershell
uv run pa-agent run "帮我定位这个问题" `
  --model deepseek-chat `
  --base-url https://api.deepseek.com/v1 `
  --api-key your-api-key
```

也支持 mock：

```powershell
uv run pa-agent run "日志路径 /tmp/fault.log 网元 192.168.1.10 故障定位" --mock
```

### `src/pydantic_agent/tui.py`

Textual TUI 入口：`ProblemLocatorApp`。

界面结构：

- 顶部 Header。
- 标题：底软问题辅助定位 Agent。
- Markdown 输出区。
- 右侧调试信息窗口：展示当前执行步骤、超时配置、重试配置、结构化输出尝试模式、失败/完成状态等运行进度。
- 状态条：
  - `就绪`
  - `Agent 正在运行，大模型正在回答...`
  - `完成`
  - `运行失败`
- LoadingIndicator 动画。
- 输入框。
- Run 按钮。
- Footer 快捷键提示。

交互行为：

- 输入内容后按 Enter 或点击 Run 提交。
- 提交后输入框立即清空，并保持焦点。
- agent 运行中禁用 Run 按钮。
- agent 运行中再次提交会提示仍在运行。
- 大模型回答通过 `stream_request()` 流式刷新到 Markdown 输出区。
- 调试信息通过 `stream_request(..., debug=...)` 回调实时刷新到右侧窗口，便于在内网模型接口卡顿、超时或降级时判断当前运行到哪一步。
- 兼容小键盘输入：
  - 数字 `0-9`
  - `decimal -> .`
  - `add -> +`
  - `subtract -> -`
  - `multiply -> *`
  - `divide -> /`
  - `equal -> =`
  - `separator -> ,`
  - 小键盘 Enter 触发提交

### `tests/`

`tests/test_agent.py`：

- mock 模式配置。
- OpenAI-compatible 模型构造。
- Pydantic AI 原生模型字符串透传。
- 闲聊意图识别。
- 问题定位结构化字段抽取。
- 密码不在输出中回显。
- mock 流式输出。

`tests/test_tui.py`：

- 提交后清空输入框。
- 小键盘 decimal 输入映射。

## 5. 请求处理流程

### CLI 非流式流程

```text
用户输入
  -> Typer run 命令
  -> Settings
  -> ProblemLocatorAgentRunner.handle_request()
  -> 意图识别
      -> chat: 闲聊回答
      -> troubleshooting: 结构化抽取 -> 定位建议
  -> Rich Panel 输出
```

### TUI 流式流程

```text
用户输入
  -> Textual Input Submitted / Run Button
  -> 清空输入框
  -> 显示 LoadingIndicator 和运行状态
  -> ProblemLocatorAgentRunner.stream_request()
  -> 流式刷新 Markdown 输出区
  -> 完成后隐藏 LoadingIndicator，状态变为完成
```

## 6. 模型配置示例

### OpenAI-compatible 模式

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "openai-compatible"
$env:PYDANTIC_AGENT_MODEL = "deepseek-chat"
$env:PYDANTIC_AGENT_OPENAI_BASE_URL = "https://api.deepseek.com/v1"
$env:PYDANTIC_AGENT_OPENAI_API_KEY = "your-api-key"
$env:PYDANTIC_AGENT_STRUCTURED_OUTPUT_MODE = "auto"
$env:PYDANTIC_AGENT_REQUEST_TIMEOUT_SECONDS = "7"
$env:PYDANTIC_AGENT_MODEL_RETRIES = "3"
```

### DashScope 兼容模式示例

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "openai-compatible"
$env:PYDANTIC_AGENT_MODEL = "qwen-plus"
$env:PYDANTIC_AGENT_OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:PYDANTIC_AGENT_OPENAI_API_KEY = "your-api-key"
```

### Ollama 本地兼容接口示例

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "openai-compatible"
$env:PYDANTIC_AGENT_MODEL = "qwen2.5:7b"
$env:PYDANTIC_AGENT_OPENAI_BASE_URL = "http://localhost:11434/v1"
$env:PYDANTIC_AGENT_OPENAI_API_KEY = "ollama"
```

### Pydantic AI 原生模式

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "pydantic-ai"
$env:PYDANTIC_AGENT_MODEL = "openai:gpt-5.2"
```

## 7. 安全边界

当前实现有意保持保守边界：

- 不执行真实 SSH。
- 不读取用户文件系统中的日志路径。
- 不假装已经读取日志或连接设备。
- 输出中不回显密码。
- 发送给模型的问题定位上下文排除 `password` 字段。
- 如果原始问题描述中包含密码文本，会在发送和展示前替换为 `***`。

后续接入 SSH 工具时建议遵循：

- 默认只读命令。
- 明确区分“建议命令”和“已执行命令”。
- 执行命令前展示目标 IP、账号、命令和风险。
- 禁止执行重启、删除、修改配置、倒换等高风险命令，除非后续实现显式人工确认机制。
- 日志和凭据不要写入版本库。

## 8. 开发命令

安装依赖：

```powershell
uv sync --extra dev
```

运行测试：

```powershell
uv run pytest
```

如果 Windows 上 `pa-agent.exe` 被占用导致 `uv run` 重装失败，可以直接使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```

运行 lint：

```powershell
uv run ruff check .
```

运行 CLI：

```powershell
uv run pa-agent run "日志路径 /tmp/a.log 网元 1.1.1.1 故障定位" --mock
```

运行 TUI：

```powershell
uv run pa-agent tui
```

## 9. 扩展建议

### 9.1 SSH 工具层

可新增模块：

```text
src/pydantic_agent/tools/
├── __init__.py
├── ssh.py
├── log_fetch.py
└── parsers.py
```

建议第一阶段只做只读能力：

- 检查 SSH 连通性。
- 获取系统时间和主机名。
- 检查关键进程。
- 拉取指定日志路径的 tail 或按时间窗口 grep。
- 记录已执行命令和退出码。

### 9.2 日志分析层

可增加：

- 时间窗口解析。
- 错误关键词提取。
- core/reset/switchover/exception 关键模式扫描。
- 模块名归因。
- 多日志文件聚合摘要。

### 9.3 报告输出

可增加结构化报告模型：

- 问题摘要。
- 已知信息。
- 缺失信息。
- 已执行检查。
- 发现的异常。
- 初步结论。
- 下一步建议。

## 10. 已知限制

- 真实模型输出质量依赖服务商和模型能力。
- mock 模式只是基本规则和正则，不代表真实模型效果。
- 当前没有多轮会话记忆。
- 当前没有真实 SSH/日志工具。
- 当前 TUI 输出区是单次结果视图，不保存历史消息列表。
