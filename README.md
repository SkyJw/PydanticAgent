# Pydantic Agent CLI

一个基于 Textual 和 Pydantic AI 的底软问题辅助定位 agent。

## 能力

- 支持 OpenAI-compatible 大模型服务商。
- 先做意图识别：闲聊直接回答，问题定位进入定位流程。
- 问题定位会抽取结构化字段：
  - 日志路径
  - 问题网元 IP
  - 账号
  - 密码
  - SSH IP
  - 问题描述
- TUI 界面支持流式输出，能实时看到 agent 的生成过程。
- 密码字段会在展示和发送给模型的上下文中脱敏，保留在结构化对象里供后续本地 SSH 工具使用。

## 安装

```powershell
uv sync --extra dev
```

## 配置模型

默认使用 OpenAI-compatible Chat Completions 接口，可接 OpenAI、DeepSeek、
DashScope 兼容模式、OpenRouter、Ollama 等服务：

仓库提供了最新默认配置模板 `.env.example`。可以先复制为 `.env`，
再按本地服务商填写模型、base URL 和 API key；`.env` 会被忽略，请勿提交真实密钥。

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "openai-compatible"
$env:PYDANTIC_AGENT_MODEL = "deepseek-chat"
$env:PYDANTIC_AGENT_OPENAI_BASE_URL = "https://api.deepseek.com/v1"
$env:PYDANTIC_AGENT_OPENAI_API_KEY = "your-api-key"
```

也可以命令行临时覆盖：

```powershell
uv run pa-agent run "帮我定位这个问题" `
  --model deepseek-chat `
  --base-url https://api.deepseek.com/v1 `
  --api-key your-api-key
```

如果想使用 Pydantic AI 原生模型字符串：

```powershell
$env:PYDANTIC_AGENT_MODEL_PROVIDER = "pydantic-ai"
$env:PYDANTIC_AGENT_MODEL = "openai:gpt-5.2"
```

## 使用

运行问题定位请求：

```powershell
uv run pa-agent run "请定位问题，网元 192.168.1.10 业务中断，日志路径 /var/log/otn/fault.log，账号 admin 密码 xxx ssh 10.10.10.8"
```

不调用模型、只检查路由和抽取：

```powershell
uv run pa-agent run "日志路径 /tmp/fault.log 网元 192.168.1.10 故障定位" --mock
```

启动 Textual 界面：

```powershell
uv run pa-agent tui
```

## 扩展方向

后续可以在 `src/pydantic_agent/agent.py` 的问题定位流程后面接入只读工具：

- SSH 连通性检查
- 自动拉取日志
- 按时间窗口 grep 关键错误
- 检查进程、端口、主备状态、倒换记录
- 输出定位报告和待补充信息清单

## 详细文档

完整设计、架构、配置、安全边界和扩展建议见：

- [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)
- [AGENTS.md](AGENTS.md)
