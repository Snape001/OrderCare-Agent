# 模拟售后政策版本记录

这些文件仅用于 OrderCare-Agent 的客服 Agent 和 RAG 实验，不代表真实商家政策。

## v1（历史基线）

- 冻结文本：`data/evaluation/rag/three-way-comparison-v1/frozen-policy-v1.md`，SHA256 `f0aa9a1dd22120d0d1eccd59a464c4d25201132826d126bf611324e535053e80`。
- 当前线上默认路径：`data/policies/customer_service_policy.md`，在 v1 实验后仅顶层标题变更；对应 SHA256 `bd19858c6878739542bfbc420c7155a00b3ac88b286821af980427cd6e2c85bf`。二级章节文本与冻结版本相同。
- 旧数据集 `data/evaluation/rag/dataset-v1.json` 和第一轮报告保持原样，不用 v2 政策重算旧分数。

## v2（独立实验语料）

- 目录：`data/policies/v2/`。`base-policy.md` 是当前默认政策的字节级副本；另有退换货、物流、保修、财务和工单 5 份补充政策。
- 6 文件、41 章节、当前按 220 字符/40 重叠切为 41 个 Chunk。
- 目录内容哈希（按文件名排序，对每个文件拼接 `name + NUL + bytes + NUL` 后计算 SHA256）：`15772bb3dae52d80bc19b5562bae5698ca8711abd4d5cb452797541239ee0b5f`。
- 90题标注见 `data/evaluation/rag/dataset-v2.json`；其中旧 40 题的答案事实不改，仅重映射到字节相同的基础文档并按场景组重新划分开发/留出集。新增 50 题由开发助手依据政策逐条编写，尚未经独立人工复核。
- 此版本由评测脚本显式指定，不替换线上 `get_policy_knowledge_base()` 默认读取的单文件政策。

| 文件 | SHA256 |
| --- | --- |
| `base-policy.md` | `bd19858c6878739542bfbc420c7155a00b3ac88b286821af980427cd6e2c85bf` |
| `finance.md` | `1eec17cc2015dbe7da6757da1a3277e0e94c6e5b783c4dec07e84e4173c33ddd` |
| `returns.md` | `dbf5245e7cea4cac5c08c9d7594daa17e4ea6c247fa6225d14d843d82e6a428a` |
| `shipping.md` | `6d5ee0b711f573d8f226c08310b23a612ba3db1c4362e5d6643023d329ed3651` |
| `tickets.md` | `b5b21e5421762277528749bc4c9ec0d23f25d738b73d572d1f08a9c1d395b6ad` |
| `warranty.md` | `05bb303c5bb0280731606ea2382a47984b1ffe53b28ac4bb48de074581ac582d` |

改动任何 v2 政策文件后，必须重新审核标注并发布新的数据集版本；现有数据集的 SHA256 校验会拒绝继续评测。
