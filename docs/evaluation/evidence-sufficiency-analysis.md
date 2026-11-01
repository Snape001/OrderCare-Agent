# Evidence Sufficiency 诊断与生成优化实验

## 结论

当前问题分为证据缺失、生成越界和评审不可靠三层。相似政策被召回并不意味着用户所需的每个条件都存在。候选只试验结构化证据块和明确的证据边界/部分拒答指令；不部署到线上。

尤其不能把本轮 Judge 给出的高正确率当成真实正确率：开发集已有反例，且不少断言/引用抽取不符合原文。下表是通过结构和文本锚点校验的同模型估计，有效 N 与语义可靠性是两回事；本轮无法可靠证明正确率或忠实性提升。无答案题的综合 Judge 格式失败导致对应指标 null，不能声称拒答能力已验证。

## 全量与分组实测

40题沿用原冻结标签，dev/test各20。候选选择记录在 `generation-selection-v1.json`，依据仅为开发集。未修改Ground Truth，未对留出集调参。

| Split | 结果 | Baseline | Candidate |
| --- | --- | ---: | ---: |
| all | generated | 40 | 35 |
| all | judged | 30 | 25 |
| all | judge_warning_cases | 29 | 28 |
| all | generation_latency_ms | 11123.954757499996 | 15904.677757500001 |
| all | judge_latency_ms | 8864.956622499449 | 9342.617805714264 |
| dev | generated | 20 | 16 |
| dev | judged | 15 | 11 |
| dev | judge_warning_cases | 14 | 15 |
| dev | generation_latency_ms | 12406.330665000132 | 17522.986129999994 |
| dev | judge_latency_ms | 9560.776949999854 | 9907.82812500001 |
| test | generated | 20 | 19 |
| test | judged | 15 | 14 |
| test | judge_warning_cases | 15 | 13 |
| test | generation_latency_ms | 9841.57884999986 | 14286.369385000013 |
| test | judge_latency_ms | 8169.1362949990435 | 8866.651221052585 |

[完整配对指标、检索延迟与token对比](../../data/evaluation/rag/generation-comparison-v1/comparison.md)

| Split | 指标 | Baseline (有效N) | Candidate (有效N) |
| --- | --- | ---: | ---: |
| all | answer_correctness | 1.0000 (23) | 1.0000 (22) |
| all | faithfulness | 1.0000 (11) | 1.0000 (11) |
| all | citation_support_rate | 0.7778 (9) | 0.8750 (8) |
| all | abstention_accuracy | 1.0000 (30) | 1.0000 (25) |
| all | evidence_sufficiency | 0.6389 (36) | 0.6389 (36) |
| all | fact_evidence_coverage | 0.9295 (26) | 0.9295 (26) |
| all | evidence_abstention_accuracy | 0.8846 (26) | 0.9091 (22) |
| dev | answer_correctness | 1.0000 (13) | 1.0000 (11) |
| dev | faithfulness | 1.0000 (7) | 1.0000 (6) |
| dev | citation_support_rate | 1.0000 (3) | 0.7500 (4) |
| dev | abstention_accuracy | 1.0000 (15) | 1.0000 (11) |
| dev | evidence_sufficiency | 0.6316 (19) | 0.6316 (19) |
| dev | fact_evidence_coverage | 0.8929 (14) | 0.8929 (14) |
| dev | evidence_abstention_accuracy | 0.8571 (14) | 0.9000 (10) |
| test | answer_correctness | 1.0000 (10) | 1.0000 (11) |
| test | faithfulness | 1.0000 (4) | 1.0000 (5) |
| test | citation_support_rate | 0.6667 (6) | 1.0000 (4) |
| test | abstention_accuracy | 1.0000 (15) | 1.0000 (14) |
| test | evidence_sufficiency | 0.6471 (17) | 0.6471 (17) |
| test | fact_evidence_coverage | 0.9722 (12) | 0.9722 (12) |
| test | evidence_abstention_accuracy | 0.9167 (12) | 0.9167 (12) |

上表两列有效样本可能不同，不能直接相减判断收益。完整对比报告另列双方有效的同一批问题上的配对差值和N。检索结果完全相同，Recall@2/MRR/nDCG没有变化；检索延迟沿用第一阶段测量，并非本阶段重新计时。证据内容相同，所以独立审计复用，证据充分性没有被提示词“提升”。

## 证据与失败案例

独立审计40题中39题输出结构有效，1题异常；逐事实原文锚点校验后，23题充分、13题不足、4题未知。13题不足包含10题知识库本身无答案，以及3题有答案但当前召回缺关键事实。该审计不看模型答案，仍受小模型语义判断误差影响。

- rag-003（dev）：运输中退款只召回同主题政策，缺少“物流拦截，失败后签收按退货政策处理”，属于 Retrieval Miss，不能仅凭七天政策推断全部处理流程。
- rag-011（dev）：缺少“仓库验收通过后原路退款”。Baseline把换货补发照片核验用于退款，说明检索缺失之后还有生成越界。
- rag-015（dev）：政策是24小时内联系承运商核查，Baseline说核查24小时内完成，还引入未经确认的自动工单表述；证据已在上下文中，属于条件理解/生成问题，不能归因于Chunk。综合Judge没有可靠捕捉这一反例。
- rag-019（dev）：Baseline把故障称为正常损耗并直接确认保修资格，原文还要求以商品页面和保修凭证为准；独立审计调用异常，不能为此题制造充分性评分。
- rag-031等10题：运费承担、过期发票流程、门店地址、实时订单时刻等不在当前政策库中；扩大召回不能创造信息。

16章对应16个完整Chunk，本轮没有章节切碎证据，也没有发现已召回章节被上下文预算截断。因此未合并相邻Chunk。仅做格式去重与保留来源/章节，是对输入组织的可控实验。

候选在rag-019补回以商品页面和保修凭证为准，去掉直接确认资格的表述；但只用简称文件名，严格来源匹配可能记为引用不足。这是开发集局部观察，不是总体收益证明。rag-003仍没有补齐物流拦截条件。

## 优化选择与未启用项

实际实现的可选 `--mode structured` 将重复的最佳命中+references JSON改为带来源、章节、编号的证据块，并增加条件核对、部分拒答和逐事实引用指令。两个改动作为一个组合实验，未分别消融，不能分开归因。线上仍使用原来的Prompt和工具格式。

不启用候选作为默认：本轮Judge可靠性与有效样本覆盖不足，并存在生成输出截断，尚不能证明留出集的综合收益。未引入Cross-Encoder（无新的排序失败证据）、自适应二次检索（充分性判断尚不稳定）、Chunk合并（没有碎片化证据）。这些属于缺少实施依据，不是已经实验证明永远无收益。

## 下一阶段

先建立小规模独立复核的Judge校准集，验证事实遗漏、时限起算/完成混淆、资格承诺、部分拒答与引用绑定；再使用更可靠的评审协议或不同模型复审。下一项线上RAG能力应是按缺失条件触发、最多一轮的补检索，但必须与知识库缺失区分，并在新盲测集证明收益后再启用。

当前评测是检索后政策回答回放，未覆盖业务工具执行和人工确认的端到端生成行为；现有工程回归测试覆盖它们的接口。

## 产物与验证

[Baseline逐题报告](../../data/evaluation/rag/generation-comparison-v1/baseline-summary.md) · [Candidate逐题报告](../../data/evaluation/rag/generation-comparison-v1/candidate-summary.md) · [运行与指标定义](rag-generation-evaluation.md)

完整pytest：286 passed、2 skipped（需显式启用Docker）、8条依赖弃用警告；Ruff检查及格式检查通过；mypy通过；git diff --check通过。评测模型运行失败与代码测试失败分别记录，测试通过不代表生成质量已经达标。

## 固定预算下的运行代价

Baseline成功40/40；Candidate成功35/40，截断题为rag-001、006、011、015、017。生成平均延迟11.12秒→15.90秒；生成总token为67,526→75,916。独立证据审计成本另见evidence-audit-v1.json中的逐调用usage，未算作生成token。候选成功率下降且成本增加，是本轮不启用的直接工程依据。

配对可用样本：正确性16题、忠实性4题、引用支持2题；无答案题拒答评分全部缺失。这些样本上的高分不具有整体代表性，也无法证明候选更好或没有回退。生成质量评估的自动执行能力已具备，但可靠的语义评分覆盖仍未完成，下一阶段必须解决Judge校准。
