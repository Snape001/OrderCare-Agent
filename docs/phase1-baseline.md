# OrderCare-Agent：第一阶段运行与安全基线

## 环境和安装

项目支持 Python >=3.12,<3.15，建议与 Docker 一致使用 3.12。
从仓库根目录执行，不要使用系统 Python 3.11 运行服务。

```powershell
uv python install 3.12
uv sync --frozen --python 3.12
.\.venv\Scripts\python.exe --version
```

`uv sync` 安装项目和 dev 组；`--no-dev` 用于服务镜像。
`--only-group client` 用于前端镜像，包含 HTTP、Streamlit 和可选语音所需的 OpenAI SDK。
dev 组包括 pytest、Ruff、mypy 及 PyMySQL/pandas 类型声明。
不需要为了本阶段更换 LangChain、LangGraph 或数据库。

首次运行且 `.env` 不存在时：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.mock.example .env }
.\.venv\Scripts\python.exe src/run_service.py
```

另一个终端启动聊天界面：

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/streamlit_app.py
```

访问 http://127.0.0.1:8501 。不涉及政策检索的问候/演示订单不需要下载 BGE；
政策检索第一次运行需要下载模型和构建索引。独立 Agent 入口为 `src/run_agent.py`，
现在会先加载 Agent 并接入 Checkpoint。

Qwen 使用 `CUSTOMER_SUPPORT_MODE=qwen` 和完整的 `DASHSCOPE_API_KEY`、
`DASHSCOPE_BASE_URL`、`DASHSCOPE_MODEL`。无需通过额外假模型绕过配置校验。
部分 Qwen 配置在 auto/qwen 模式下直接报配置错误；可选 Agent 加载失败会被剔除，
默认客服加载失败会阻止服务启动。不要提交真实密钥。

## 权限与兼容行为

- `AUTH_SECRET` 是应用访问密钥，Compose 会将其传给聊天前端。
- `DATABASE_ADMIN_SECRET` 是独立数据库浏览权限，必须与应用密钥不同。
  未设置时两个数据库浏览 API 返回 503；缺凭据返回 401；错误凭据返回 403。
  数据浏览器只获得管理员密钥，聊天前端不会获得它。
- Compose 仍仅绑定 127.0.0.1。数据库浏览器是本机管理员工具，不要将其 Streamlit
  端口直接公开；界面后端持有管理员凭据。这不是面向互联网的登录/RBAC系统。
- `/invoke`、`/stream`、`/history` 要求 `X-Session-Token`，为客户端使用
  `secrets.token_hex(32)` 生成的 64 位小写十六进制随机凭证。
  `AgentClient` 自动生成并保存在实例中；可信客户端可以通过 `session_token=` 恢复。
  保管该凭证等同保管会话访问权，不要打印、写日志或放入 URL。
- 服务端通过凭证、Agent ID、公开 thread_id 派生内部 Checkpoint 标识。
  请求中的 user_id 不参与授权，长期记忆使用派生身份。不同凭证即使传相同 thread_id
  也只会看到自己的空间；历史为空，新调用不会恢复他人的待确认操作。
- 服务重启后，同一凭证及 thread_id 仍映射到相同持久化会话。
  原来的未隔离 Checkpoint 不自动迁移/开放，也不会删除。
- Streamlit 凭证存在服务端会话实例里；刷新/重启丢失实例后不能仅凭旧链接恢复。
  该阶段没有新增账户登录或跨设备凭证恢复功能。
- history 请求支持 `agent_id`，默认为 customer-support。不同 Agent 的会话分离。
- `agent_config` 禁止覆盖身份与 Checkpoint 字段，以及 `__` 前缀内部字段。
- 写操作只接受完整的“确认/同意/批准/执行”（允许末尾句号/感叹号）。
  “好的”“是”“我还没确认”等不会批准。Mock 无待确认操作时不会执行写入。
- SQLite 两个工单实现使用 BEGIN IMMEDIATE 串行化幂等检查与插入。
  锁等待仍受 SQLite 超时限制，不意味着支持无限吞吐量。

直接 API 调用请同时发送应用 Bearer（若已启用）和会话凭证；不要使用 user_id 代替凭证。
原有 HTTP 验收脚本已更新请求头。

## 测试入口

推荐一键运行全部现有测试与确定性业务评测，不需要启动服务、不调用付费模型：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_phase1.ps1
```

报告输出到被 Git 忽略的 `reports/phase1-tests.xml` 和 `reports/phase1-agent.json`。
测试失败会立即返回非零，不继续用业务评测掩盖失败。

仅验证收集：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_phase1.ps1 -CollectOnly
```

分项运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/service/test_access_control.py -q
.\.venv\Scripts\python.exe -m pytest tests/customer_support -q
.\.venv\Scripts\python.exe -m pytest tests/agents/test_knowledge_base_evidence.py tests/agents/test_run_agent.py tests/service/test_service_lifespan.py -q
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\mypy.exe src/
```

默认仅跳过仓库原有的两个 Docker 集成测试。Docker 验收需要安装 Docker、准备
Olist 数据库和 `.env`，启动 Compose 后单独运行 `scripts/verify_docker.py`。
现有 `tests/integration` 依赖 CI 的端口80部署，不能直接套到 Compose 的8080上。
`scripts/verify_qwen_docker.py` 会调用真实模型，需手动运行；
`scripts/demo_check.py` 会持久化会话并创建演示工单。
`scripts/evaluate_rag.py` 会下载/加载模型、构建索引并写报告，单独执行。
