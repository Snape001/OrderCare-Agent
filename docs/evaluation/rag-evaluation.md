# RAG Evaluation Framework

## 目的与边界

将检索评测从线上客服执行链解耦。默认只调用本地BGE/Chroma，不调用生成模型或付费API；测试替身仅用于pytest，提交的实验报告使用真实Embedding和向量库。订单查询、退款资格、工单写入、LangGraph及人工确认接口均未修改。

## 当前真实架构

1. `load_policy_sections` 按Markdown二级标题解析单一政策文件；当前16章节，按220字符、40字符重叠切片，当前实际16个chunk。
2. FastEmbed使用 `BAAI/bge-small-zh-v1.5`，文档调用`passage_embed`，问题调用`query_embed`，ONNX执行、默认2线程；Chroma使用cosine空间。
3. dense召回候选数量为 `min(max(3*K,5), chunk_count)`；K=2时最多6条。向量相似度仅表示相关，不证明上下文可以完整回答。
4. lexical在全部切片上比较中文二元字组与ASCII词/数字token；分数为问题token与“标题+正文”token交集数 / 问题token数。这不是BM25。中文字符在清洗后拼接，跨标点也可能形成二元组。
5. dense贡献 `1/(10+rank)`；hybrid词法贡献 `w * min(1, 2*lexical_score)/(10+rank)`，默认w=1。仅lexical时不按分数缩放排名贡献。这是自定义排名融合，不是标准BM25+RRF。
6. dense/hybrid保留 `dense_relevance >= 0.50 OR lexical_score >= 0.30` 的候选，再截取Top-K；纯lexical没有此过滤，仅过滤零重合。默认search K=3，业务`search_policy`显式K=2，本框架默认K=2。
7. 索引指纹包含政策文本、chunk ID、Embedding类和模型名；指纹与条数均相同时复用Chroma。进程内缓存KB对象，但每次search仍检查文件与条数。模型名相同而权重更新不必然触发原有索引重建，实验记录权重哈希，换权重时须使用独立索引或`--rebuild`。
8. `search_policy`返回最佳片段与完整references；没有命中时返回转人工提示。Agent根据工具证据生成回答并被要求标来源。检索引用和模型最终引用支持是不同层面的事实。

新增的`lexical_weight`与`lexical_threshold`构造参数默认值保持旧行为。术语扩展仅存在`evaluation/experiments.py`，不是线上自动改写。尚未实现Cross-Encoder、Query Rewrite LLM、Adaptive Retrieval或证据充分性模型。

## 数据集及Ground Truth

[data/evaluation/rag/dataset-v1.json](../../data/evaluation/rag/dataset-v1.json) 包含40题：30可答、10无答案，覆盖退货、特殊商品、质量售后、退款、物流、维修、发票、支付、优惠券、多条件与业务无关问题。

每题包含query、relevant_documents（文件、章节、原文证据）、relevance_scores、expected_answer、expected_facts、should_abstain、category、id、split。章节ID为`source#section`，相关性3=直接支持主要诉求、2=支持补充事实、1=弱背景、0=无支持（未列出章节默认为0）。

标签由本轮开发助手逐条对照政策原文编写，未调用待测检索系统或生成模型制作标准答案，尚未经独立人工复审。题目是构造测试数据，不能冒充真实客户记录或真实平台政策。程序验证原文引用存在、等级有效、无重复ID、无答案题不含支持标签，并校验政策SHA-256；这些检查不等于独立人工语义复审。

冻结前按编号奇偶分dev/test，每份15可答+5无答案。多条件题需要多个章节完整覆盖。无答案题包括“只知道相关政策，却缺少完成该问题所必需的事实”；允许最终回答说明已知边界并明确拒绝未知部分，但不能编造缺失信息。改变政策或修正标注必须发布新数据集版本，不能覆盖基线以提升分数。

## 指标定义

评价单元是来源+章节；先按原始chunk预算截取K，再按首次出现对章节去重。重复chunk占用上下文预算但不能重复获得相关性分数；章节排序在去重后的列表中计算。

| 指标 | 定义与分母 |
| --- | --- |
| Recall@K | Top-K去重章节中相关章节数 / 该题所有标注相关章节数；仅可答题宏平均 |
| MRR@K | 首个相关章节的倒数排名，K内无相关为0；仅可答题宏平均，不冒充全库无截断MRR |
| nDCG@K | gain=`2^grade-1`，折扣=`log2(rank+1)`，用该题理想排序归一化；仅可答题 |
| Context Relevance（标注版） | 返回章节相关等级/3的均值；空上下文=0，汇总覆盖全部题。这是基于人工标签的上下文相关度，不是LLM评分 |
| Retrieval Abstention Accuracy | 是否无检索结果与should_abstain一致的比例，分母为全部题 |
| No-answer Rejection Rate | 无答案题中无检索结果的比例 |
| Answerable False Rejection Rate | 可答题中被返回空结果的比例 |
| Answer Correctness（可选Judge） | 对每个标准核心事实逐项判定正确，取比例，再按题宏平均 |
| Faithfulness（可选Judge） | Judge拆分答案原子事实，证据支持的事实数/全部事实数；没有事实的拒答为null |
| Citation Support Rate（可选Judge） | Judge判断每条claim的引用章节是否实际支持它，并校验引用存在于检索上下文、claim确为答案原文；无引用的非拒答答案=0，无引用的拒答=null |
| Abstention Accuracy（生成层） | 模型实际abstained字段与标签一致的比例，与检索空结果率分开 |

检索异常与生成/Judge异常分别记录，显示总数、有效数、错误数，绝不默默记成正确或伪造分数。生成没运行时所有相关指标与延迟为null。只有存在有效样本才平均；全无答案集的Recall/MRR/nDCG为null。异常会令CLI返回非零。

## 运行方式

在项目根目录运行，先用`uv sync --frozen --python 3.12`安装依赖。首次Embedding模型未缓存时需联网下载；此操作不是生成API调用。模型已缓存时可在PowerShell设置`$env:HF_HUB_OFFLINE="1"`限制模型下载联网。

```powershell
# 默认：40题、lexical/dense/hybrid、K=2，每题检索3次，无LLM请求
uv run --frozen python scripts/evaluate_rag.py

# 指定全新结果目录；同名目录已存在会拒绝覆盖
uv run --frozen python scripts/evaluate_rag.py --output data/evaluation/rag/runs/my-baseline

# 开发集消融
uv run --frozen python scripts/evaluate_rag.py --split dev --methods hybrid --lexical-weight 0.25
uv run --frozen python scripts/evaluate_rag.py --split dev --methods hybrid --threshold 0.65

# 本轮候选：保留原问题、追加术语，仍保持默认融合和阈值
uv run --frozen python scripts/evaluate_rag.py --methods hybrid --expand-query

# 自动成对对比：使用同一数据集、模型、K和case顺序
uv run --frozen python scripts/compare_rag.py data/evaluation/rag/baseline-v1/results.json data/evaluation/rag/candidate-v1/results.json --output data/evaluation/rag/runs/my-comparison.json
```

输出为JSON逐题详情和Markdown汇总。包含每条问题的rank、chunk_id、source、title、content、融合score、dense/lexical各自rank及score、有效query、错误类别；另记录数据版本、源文/数据集/源代码/锁文件/ONNX SHA-256、依赖版本、Python与平台、全部检索参数。输出目录默认带UTC时间戳；旧实验不覆盖。

索引默认位于`.tmp/rag-evaluation-index`，与线上`data/chroma`分离。初始化和热身时间单列，查询延迟为3次稳态测量，P95使用nearest-rank法。首次建库开销不应被包装为稳态延迟，也不承诺所有硬件上时间一致。Chroma近似检索与同分排序可能受版本影响，逐题记录重复运行排名是否一致。

旧72题的`data/evaluation/rag_cases.json`和`rag_report.json`作为历史产物保留，不自动覆盖，也不能直接当作新版多章节分级数据集输入；旧Hit@K不能与新Recall@K直接比较。

## 可选生成与LLM Judge

默认不生成。明确指定`--generate --judge`才同时执行旧版回答和Judge，默认两者都走本机Ollama：

```powershell
uv run --frozen python scripts/evaluate_rag.py --methods hybrid --generate --judge --ollama-model qwen3:4b --judge-ollama-model qwen3:4b
```

每次调用120秒截止；Ollama temperature=0、seed=42，输出必须符合JSON结构。生成Prompt只接收问题与检索证据，绝不提供标准答案；Judge才接收标准事实，并逐条评价回答断言和引用支持。保存答案、判定理由与生成/Judge耗时；解析失败、连接失败或不完整判定均记录错误，不回退到规则生成或捏造分数。

使用已配置的真实Provider（例如`.env`中`DEFAULT_MODEL=deepseek-chat`和相应Key）必须显式授权：

```powershell
uv run --frozen python scripts/evaluate_rag.py --methods hybrid --generate --judge --generator-provider configured --judge-provider configured --allow-paid-api
```

默认40题、每题一次生成和一次Judge，每个method单独运行，使用三个method可能达到240次请求；按需先用`--split dev --methods hybrid`。模型和实际temperature会写入元数据，不承诺云模型位级确定性；API Key不会写入报告。不同生成/Judge配置不能直接归因于检索优化。

本轮未执行真实生成/Judge评测，所以回答正确率、引用支持率、忠实性及生成延迟没有实测结论。使用同一模型自评会有偏差，建议不同Judge和独立人工抽查；即使输出合法JSON也不代表判定绝对正确。框架未串联线上Agent订单工具，评估的是政策回答链路。

## 工程验证

```powershell
# 避免当前机器系统临时目录权限问题，先建立项目内父目录
New-Item -ItemType Directory -Force .tmp
uv run --frozen pytest -q -ra --basetemp=.tmp/pytest-rag-validation
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src scripts/evaluate_rag.py scripts/compare_rag.py
git diff --check
```

pytest覆盖手算分级指标、去重与来源匹配、空结果、无答案、无样本、检索异常、非法标注、数据漂移、生成失败、Judge结构、付费开关、标准答案不泄露给生成器、比较配置约束及旧检索默认行为。

实验结论与尚未解决的问题见 [优化报告](rag-optimization-report.md)。

第二阶段复用线上 Prompt 的独立生成入口及实测见 [生成质量评测](rag-generation-evaluation.md)。以上“未执行真实生成”描述仅指第一阶段。
