# 从这里开始：真实 LLM 电商客服

客服运行必须使用 Ollama、Qwen、DeepSeek 或通用真实 LLM Provider。不再提供规则客服或自动降级；旧的 `mock` / `auto` 配置会报错。

## 1. 选择模型并配置

- Ollama：安装并启动 Ollama，运行 `ollama pull qwen3:4b`，首次将 `.env.ollama.example` 复制为 `.env`。
- DeepSeek：参考 `.env.deepseek.example`，设置 `LLM_PROVIDER=deepseek` 和自己的 API Key。
- Qwen：参考 `.env.qwen.example`，设置 `CUSTOMER_SUPPORT_MODE=qwen` 及完整的 DASHSCOPE 配置。
- 其他 Provider：设置 `CUSTOMER_SUPPORT_MODE=llm`、`DEFAULT_MODEL` 与对应密钥。模型须支持工具调用。

已有 `.env` 请直接编辑，不要覆盖其中的密钥。移除旧的 `DEFAULT_MODEL=fake` 和 `USE_FAKE_MODEL=true` 设置。运行模式只选择真实模型，连接失败不会返回模拟答复。

## 2. 安装和启动

Windows 安装 Python 3.12、uv 后，在项目目录运行：

```powershell
.\scripts\setup_demo.cmd
.\scripts\start_demo.cmd
```

首次需要下载依赖和中文 Embedding 模型。聊天页面为 http://127.0.0.1:8501；API 文档为 http://127.0.0.1:8080/docs。

## 3. 验证业务链路

```text
七天无理由退款有什么要求？请标注政策来源。
查询订单 ORD1001，手机号后四位 8821
订单 ORD1002 能退款吗？手机号后四位 8821
为 ORD1001 创建人工客服工单，手机号后四位 8821
确认
```

订单是样例业务数据，但理解、工具选择与回答由真实模型完成。创建工单仍需人工确认；也可回复“取消”验证拒绝分支。

```powershell
.\scripts\run_tests.cmd
uv run python scripts/evaluate_rag.py
uv run python scripts/evaluate_agent.py
```

单元测试使用测试替身，不调用云端模型；确定性 Agent 评测检查路由和业务规则，不代表真实模型准确率。真实 HTTP 检查需显式运行 `uv run python scripts/demo_check.py`，可能产生 API 费用并创建演示工单。

## 4. 停止与排错

```powershell
.\scripts\stop_demo.cmd
```

查看 `data/logs/service.err.log` 与 `data/logs/app.err.log`。Ollama 不可达或模型未安装会阻止客服启动；云端模型连接或认证失败会返回明确调用错误。修正配置后重启，不会自动切换模型。

[完整安装与技术说明](README.md) · [Docker + MySQL](docs/deployment/docker-mysql.md) · [Olist 数据准备](docs/data/olist-dataset.md)
