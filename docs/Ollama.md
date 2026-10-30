# OrderCare-Agent：使用 Ollama

默认客服的本地真实模型模式使用 `ChatOllama`。推荐模型为 `qwen3:4b`，
配置示例见仓库根目录的 `.env.ollama.example`；模型不可用时服务会明确报错。

You can also use [Ollama](https://ollama.com) to run the LLM powering the agent service.

1. Install Ollama using instructions from https://github.com/ollama/ollama
1. Pull `qwen3:4b` with `ollama pull qwen3:4b`, then set `CUSTOMER_SUPPORT_MODE=ollama` and `OLLAMA_MODEL=qwen3:4b`.

If you are running the service locally (e.g. `python src/run_service.py`), you should be all set!

If you are running the service in Docker, you will also need to:

1. [Configure the Ollama server as described here](https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server), e.g. by running `launchctl setenv OLLAMA_HOST "0.0.0.0"` on MacOS and restart Ollama.
1. Set the `OLLAMA_BASE_URL` environment variable to the base URL of the Ollama server, e.g. `OLLAMA_BASE_URL=http://host.docker.internal:11434`
1. Alternatively, you can run `ollama/ollama` image in Docker and use a similar configuration (however it may be slower in some cases).
