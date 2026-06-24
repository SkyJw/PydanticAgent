# AGENTS.md

本文档面向在本仓库中工作的 AI coding agent。请先阅读本文，再修改代码。

## 项目概览

这是一个底软问题辅助定位 agent，基于 Textual + Typer + Pydantic AI + Pydantic。

核心目标：

- 在 CLI/TUI 中接收用户输入。
- 识别输入是闲聊还是问题定位。
- 对问题定位请求抽取结构化字段。
- 生成底软定位建议。
- 在 TUI 中流式展示大模型输出。

当前项目不是通用 workflow 框架。不要重新引入 `workflow/general/summarize/plan` 这类预置工作流概念，除非用户明确要求重新设计为多工作流产品。

## 关键文件

- `src/pydantic_agent/agent.py`
  - 核心 runner：`ProblemLocatorAgentRunner`
  - 意图识别、结构化抽取、流式输出、mock 模式
- `src/pydantic_agent/models.py`
  - Pydantic 数据模型
- `src/pydantic_agent/config.py`
  - 环境变量和 `.env` 配置
- `src/pydantic_agent/cli.py`
  - Typer CLI
- `src/pydantic_agent/tui.py`
  - Textual TUI
- `tests/test_agent.py`
  - agent 行为测试
- `tests/test_tui.py`
  - TUI 交互测试
- `docs/PROJECT_DOCUMENTATION.md`
  - 详细项目文档

## 常用命令

安装依赖：

```powershell
uv sync --extra dev
```

运行测试：

```powershell
uv run pytest
```

运行 lint：

```powershell
uv run ruff check .
```

运行 CLI mock：

```powershell
uv run pa-agent run "日志路径 /tmp/a.log 网元 1.1.1.1 故障定位" --mock
```

启动 TUI：

```powershell
uv run pa-agent tui
```

Windows 上如果 `pa-agent.exe` 被占用导致 `uv run` 重装失败，可直接运行：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pydantic_agent run "日志路径 /tmp/a.log 网元 1.1.1.1 故障定位" --mock
```

## 代码风格

- 使用 Python 3.11+ 类型标注。
- 使用 Pydantic 模型承载结构化数据，不要用裸 dict 在模块间传递核心业务对象。
- 使用 `apply_patch` 做人工编辑。
- 运行 `ruff check .` 和 `pytest` 后再交付。
- 保持 `pyproject.toml` 中的 Ruff 规则通过。
- 保持 Textual headless 测试可运行。

## 架构边界

### Agent runner

`ProblemLocatorAgentRunner` 是核心业务入口。新增能力优先挂在 runner 后面，而不是绕过 runner 写到 CLI/TUI 中。

推荐入口：

- 非流式：`handle_request()`
- 流式：`stream_request()`
- 结构化意图识别：`classify_intent()`
- 结构化字段抽取：`extract_troubleshooting_context()`

### CLI/TUI

CLI 和 TUI 应保持薄层：

- 读取用户输入。
- 读取或覆盖配置。
- 调用 runner。
- 展示结果。

不要在 CLI/TUI 中复制问题定位逻辑。

### 模型配置

支持两种模式：

- `openai-compatible`
- `pydantic-ai`

不要把某个具体服务商硬编码为唯一入口。新增服务商时优先通过 `openai_base_url`、`model`、`api_key` 配置支持。

## 安全要求

本项目会处理账号、密码、SSH IP、网元 IP、日志路径等敏感信息。修改代码时必须遵守：

- 不要在输出中回显密码。
- 不要把密码写入日志、测试 snapshot、文档示例真实值或异常信息。
- 发送给大模型的上下文应排除 `password` 字段。
- 如果问题描述中包含密码文本，应替换为 `***`。
- 当前阶段不要执行真实 SSH。
- 不要假装已经连接设备或读取日志。
- 后续如接入 SSH，默认只允许只读命令。
- 禁止默认执行重启、删除、修改配置、倒换等高风险操作。

## TUI 注意事项

TUI 当前行为：

- 提交后清空输入框。
- 保持输入框焦点。
- 运行中显示 LoadingIndicator。
- 运行中禁用 Run 按钮。
- 运行中阻止重复提交。
- 支持小键盘输入映射。

修改 TUI 后请至少运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_tui.py
```

## 测试要求

新增功能时优先补充测试：

- 结构化字段新增或变化：补 `tests/test_agent.py`
- TUI 交互变化：补 `tests/test_tui.py`
- 安全脱敏变化：必须补测试，确认输出不含明文密码

交付前建议运行：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```

## 文档维护

当修改以下内容时，请同步更新 `docs/PROJECT_DOCUMENTATION.md`：

- CLI 命令或参数
- 环境变量
- TUI 行为
- agent 处理流程
- 安全边界
- 新增工具层或 SSH 能力

当修改 agent 协作规则、测试命令、项目边界时，请同步更新本 `AGENTS.md`。
