# RAG 生成质量评测

## 范围与调用链

本阶段复用冻结的 `dataset-v1.json` 40 题及第一阶段 `baseline-v1/results.json` 的 hybrid Top-2 真实检索结果。生成器接收线上 `SYSTEM_PROMPT`、原始问题、模拟完成的 `search_policy` 工具消息和真实检索证据；工具返回格式由线上与评测共用的 `format_policy_hits` 构建。标准事实只进入 Judge，绝不进入回答 Prompt。

这里回放的是**检索后政策生成阶段**，不执行订单工具、不写工单、不覆盖整条 Agent 的路由、Checkpoint 或人工确认。线上仅抽取了原样 Prompt 常量和原样格式化函数，LangGraph 流程、业务数据库、工具定义不变。最终可见答案复用 `public_answer`，原始模型输出另外保存。

原链路仍为 Markdown 章节 → 220 字符/40 重叠切片 → BGE-small-zh-v1.5 → 持久化 Chroma → dense 与中文二元字组词法召回 → 自定义倒数排名融合 → 阈值过滤 → Top-2 工具证据 → 真实模型。没有新增线上 Rewrite、Cross-Encoder 或自适应检索。16 个章节当前都小于切片长度，每节恰好一个 Chunk。

## 运行入口与费用开关

从项目根目录运行，需要已安装本地 `qwen3:4b` 且 Ollama 服务可用。先检查 `ollama list`；本阶段不会自行下载或回退模型。

```powershell
# 默认只生成；不调用 Judge，也不重新执行向量检索
uv run --frozen python scripts/evaluate_rag_generation.py --output data/evaluation/rag/runs/my-generation

# 显式启用生成 + Judge，本地模型无外部 API 费用
uv run --frozen python scripts/evaluate_rag_generation.py --output data/evaluation/rag/runs/my-baseline --stage both --judge

# 对保存的成功答案单独评审，不再生成
uv run --frozen python scripts/evaluate_rag_generation.py --input data/evaluation/rag/runs/my-generation/results.json --output data/evaluation/rag/runs/my-judge --stage judge --judge

# 可选 Context Engineering，保留 baseline 默认行为
uv run --frozen python scripts/evaluate_rag_generation.py --output data/evaluation/rag/runs/my-candidate --mode structured --stage both --judge

# 不看模型答案的独立证据充分性评审；30 可答题调用 Judge，10 无答案题沿用冻结标签
uv run --frozen python scripts/audit_rag_evidence.py --input data/evaluation/rag/runs/my-baseline/results.json --output data/evaluation/rag/runs/my-evidence.json --judge

# 离线生成汇总、逐题诊断和配对比较，不调用任何模型
uv run --frozen python scripts/report_rag_generation.py --baseline data/evaluation/rag/runs/my-baseline/results.json --candidate data/evaluation/rag/runs/my-candidate/results.json --evidence data/evaluation/rag/runs/my-evidence.json --output data/evaluation/rag/runs/my-comparison
```

云 Provider 需额外显式 `--provider configured --allow-paid-api`，复用项目 `DEFAULT_MODEL` 工厂（如 DeepSeek）。默认绝不调用付费 API。旧入口 `evaluate_rag.py --generate` 现在也必须显式加 `--judge`；新实验应优先用上述独立生成入口。

`--split dev|test`、`--limit N` 可用于小规模运行。已存在目录拒绝覆盖；中断后同一命令加 `--resume` 只续跑未完成项，已有失败不会静默重试。数据、输入报告、代码、Prompt、模型参数或模型 digest 变化会拒绝混合续跑。重试失败应写入新目录，保留原失败结果。

## 固定参数与追溯

本机 Ollama Qwen3:4b、temperature=0、seed=42、reasoning=False、num_ctx=8192；生成最多1536 token，综合 Judge 最多1800 token，独立证据 Judge 最多1000 token。HTTP 客户端120秒、异步调用总截止180秒；连接、格式、截断、空最终答案等异常显式记录并使命令非零退出，不生成替代答案。

每次运行保存：模型名称/digest/量化信息、参数、Prompt版本及全文、源码快照/hash、数据/政策/Embedding ONNX/锁文件 hash、原检索配置、每条排名/分数/来源/原文、实际上下文、原始模型输出、可见回答、Judge原始JSON/结构化判定/理由、调用延迟与token usage。temperature=0和seed不代表跨硬件、版本或远程Provider位级确定性。

生成 Prompt 版本为 `production-policy-replay-v1`；综合 Judge 为 `evidence-claims-v2.1-bounded`；独立证据评审为 `answer-blind-evidence-v1`；离线有效性校验为 `anchored-judge-review-v1`。JSON Schema 与 Pydantic 禁止未知字段，校验类型、长度、逐事实索引；证据引用必须匹配实际原文。

## 指标定义

检索指标沿用第一阶段，禁止和生成指标合成一个总分。生成指标先逐题计算，再宏平均；每个均值同时报告有效 N，null 不按0或1填补。比较只对双方均有效的相同问题计算配对差值，避免有效样本改变造成虚假提升。

| 指标 | 计算定义 | 无法判断时 |
| --- | --- | --- |
| Answer Correctness | 被完整正确表达的标准事实数 / 标准事实数；无答案题判断是否正确说明知识边界 | 任一事实未知，或 Judge 编造/改写答案断言，整题 null |
| Faithfulness | 有证据支持的可核验回答断言数 / 提取的业务断言数 | 无断言、原文锚点缺失或不可信抽取则 null；非完整断言抽取仍有漏检风险 |
| Citation Support Rate | 实际引用中，来源/章节/对应事实及证据均支持的引用数 / 提取引用数 | 有业务断言但答案无引用为0；纯拒答无引用为null；Judge漏识别可见引用、编造引用断言则null |
| Abstention Accuracy | 明确说明全部或部分所需信息无依据的拒答判定，与冻结 `should_abstain` 一致记1，否则0 | Judge 无确定判断或拒答原文不存在则null |
| Evidence Sufficiency | 独立评审确认所有标准事实、包括复合事实全部条件，都被上下文支持记1；至少一项缺失/不完整记0 | 无已知缺失但有不确定项则null；冻结无答案题为0 |
| Fact Evidence Coverage | 被完整支持的标准事实数 / 标准事实数 | 无答案题或任一事实未知则null |
| Evidence-conditioned Abstention Accuracy | 根据**实际证据**不足时是否明确拒答/部分拒答评分；足够时不拒答记1 | 充分性或拒答判定未知则null |

后两种拒答口径不同：知识库可回答但Top-2漏证据时，基于当前上下文部分拒答可以是正确行为，不能仅因冻结标签为可答就否定它。因此同时报告两种口径、无答案拒答率及可答题拒答率。部分拒答不证明剩余答案正确，需要结合 Faithfulness。

所有语义指标是 LLM Judge 估计，不是独立人工认证。原文锚点只能验证文本存在，不能证明蕴含关系。离线校验保留 `raw_metrics`，不篡改原始判定；无可靠判定的指标明确为null。独立证据评审只看问题、标准事实、上下文，不看生成答案；在证据内容完全相同的对比中复用同一份审计，校验逐题上下文SHA-256，防止模型答案影响“证据充分性”。

## 诊断分层

- Retrieval Miss：冻结标签要求的章节未召回，属于标签级定位，未必说明每个事实都无法支持。
- Chunk Fragmentation：相关章节已召回，但切片并集不能覆盖完整章节，且证据不足；重叠片段按位置并集判断。
- Missing Evidence：冻结无答案题表明整个知识库缺少所需事实；不能靠扩大Top-K创造信息。
- Context Assembly：应使用的已召回章节未进入生成上下文。
- Generation Failure：独立证据充分，而回答正确性不足。
- Citation Mismatch：回答正确，但有效的引用评审发现支持率不足。
- Abstention Failure：独立证据不足，回答仍没有说明所需信息缺失。

允许多标签，且这些是诊断线索，不等于已证明因果。Judge抽取失真另列 `judge_warnings`，不冒充上述业务失败。每条报告包含问题、关键事实、召回、实际回答、缺失证据、失败类型和建议；不依赖人工逐条运行。

## 实验结果与限制

正式40题结果、开发集/留出集对比及优化选择见 [证据充分性分析](evidence-sufficiency-analysis.md)。第一轮未完成的 Judge 截断尝试保留在 `generation-baseline-incomplete-attempt1`，不纳入正式比较。格式约束修复后使用新目录重新运行完整 Baseline，未覆盖失败输出。

数据是项目内政策构造的40题，不是真实客服日志；标签由此前开发助手对照原文编写，尚无独立人工复核。奇偶拆分只有每组15可答+5无答案，题材相近，留出集不是全新盲测集。生成器与Judge同为4B模型，有自评偏差；有效样本少、输出不一致或局部成功都不能证明生产收益。

## 评审协议的已知缺陷

本轮综合Judge在无答案题上违反fact_support必须为空的约定，框架拒绝整题评分并保留raw_response。没有把合法JSON等同于可靠判断。独立证据审计采用先理由后枚举判定的结构，已单独完成40题；更简化的独立答案Judge尚未实现，不能在交付中声称已经修好综合Judge。

Baseline与Candidate在同机不同时段顺序执行，均保留首次调用开销，延迟不是严格控制硬件负载的基准测试。只有一次生成试验，没有多随机种子置信区间。

正式实验源码快照位于各结果目录的 `generation.py.txt`；随后仅为 configured Provider 补充Schema提示，本机Ollama路径不变。严格重放或续跑旧实验应匹配其源码hash，当前代码拒绝跨hash续跑属于预期保护。
