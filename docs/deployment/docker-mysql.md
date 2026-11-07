# Docker + MySQL 部署与验收

## 最终结构

```text
浏览器
  │
  ▼
Streamlit :8501
  │ HTTP
  ▼
FastAPI + LangGraph Agent :8080
  ├─ Qwen：理解问题、选择工具、生成回答
  ├─ BGE + Chroma：检索商城政策
  ├─ Redis：带 TTL 的会话/工作记忆，AOF 卷持久化
  ├─ Chroma 独立 Collection：已验证客户的售后情景记忆
  ├─ SQLite：用户画像与售后摘要
  ├─ MySQL :3306：订单、支付、评价、工单
  └─ SQLite：保存 LangGraph 对话检查点
```

只读 MySQL 数据浏览器运行在 <http://127.0.0.1:8081>，只绑定本机地址。
页面可以选择表、分页查看数据，并可按 `OL` 演示订单号查询；不提供修改和删除能力。

MySQL 保存业务数据，因为订单查询、关联支付、工单写入需要关系型数据库。
SQLite 分别保存单机 Agent 对话检查点和用户画像，使用不同文件，减少 8GB 内存电脑同时运行的服务数量。
正常运行还默认启用 Redis、独立 Chroma 情景记忆 Collection 和 SQLite 用户画像；这些 Memory 数据与业务 MySQL、LangGraph Checkpoint 分开。`/ready` 会核对 Redis、画像数据库与 Chroma，依赖故障时返回 503。Redis 使用 AOF 和命名卷；`docker compose down` 不删除卷。

## 一键启动

确认 Docker Desktop 已启动后，在项目目录双击：

```text
scripts/start_docker.cmd
```

第一次启动会做四件事：

1. 下载 MySQL 8.4 和 Python 基础镜像；
2. 构建 Agent、数据迁移和 Streamlit 镜像；
3. 将 `data/olist_support.db` 中的真实匿名数据迁入 MySQL；
4. 等 MySQL、FastAPI 健康后启动网页。

首次启动耗时较长。以后再次启动时，迁移脚本通过源数据库 SHA-256 判断数据是否
已经导入，不会重复写入 9 万多条订单。

## 自动验收

容器都显示 `healthy` 后运行：

```text
scripts/verify_docker.cmd
```

期望看到：

```text
[通过] FastAPI + MySQL 就绪检查
[通过] Streamlit 健康检查
[通过] 只读 MySQL 浏览器
[通过] MySQL 真实订单: 99,441 条
[通过] MySQL 订单明细: 112,650 条
Docker 验收结果：5/5 项通过
```

然后打开 <http://127.0.0.1:8501>，用以下真实匿名订单验证 Agent：

```text
查询订单 OL099422，手机号后四位 3623
查询订单 OL099415，手机号后四位 4882
订单 OL080724 能退款吗？手机号后四位 0347
查询订单 OL099441，手机号后四位 6192
```

真实 Qwen、Function Calling、MySQL 和 RAG 的自动验收：

```text
scripts/verify_qwen_docker.cmd
```

该脚本会产生两次模型调用，用于检查订单工具链和政策 RAG 工具链。

## 常用排错命令

```powershell
# 查看所有容器状态
docker compose ps

# 查看 Agent 最近 100 行日志
docker compose logs --tail 100 agent_service

# 查看迁移日志
docker compose logs mysql_loader

# 查看 MySQL 日志
docker compose logs --tail 100 mysql

# 停止项目，但保留数据库数据
docker compose down
```

只有需要彻底重做数据库实验时，才执行 `docker compose down -v`。`-v` 会删除
MySQL 和 Agent 检查点卷，日常停止不要使用。

## 面试时怎么讲

一开始项目使用 SQLite 快速验证业务闭环；接入 9 万多笔 Olist 订单后，我把业务
存储抽象为可切换后端，并迁移到 MySQL 8.4。迁移脚本按批写入、建立外键和索引，
用源文件 SHA-256 保证重复启动不重复导入。Docker Compose 通过 healthcheck 和
`service_completed_successfully` 控制启动顺序，避免 Agent 在数据库未就绪时启动。

一个实际取舍是没有继续为 LangGraph 单独运行 PostgreSQL：在本地 8GB 内存环境中，
业务订单和工单使用 MySQL，对话检查点保留 SQLite，功能完整且资源成本更低。
