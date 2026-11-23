# 公共脱敏模块的外部基准验证

- R2 更新：[修复后冻结回归](../../experiments/privacy-benchmark-20261107-r2.md)，规则 `d832be12`，三基准全量新调用、完整工程回归已核验。基于 R1 错误开发，不能称独立未见评价；R1 记录保留。

- 日期与状态：2026-11-07，首轮冻结评测已覆盖中文正式/聊天与英文 test 共 13000 条、CredData 全部 11030 个文件；凭证超时作为未知结果单列。结果和完整分母见[正式实验记录](../../experiments/privacy-benchmark-20261107-r1.md)。测得漏遮、额外遮盖、拒绝和协议语义损失，**尚未通过隐私质量验收**，不把工程回归通过改写成识别准确率。
- 当前实现：已有可测的混合处理流程。Presidio/spaCy 负责识别与替换，Gitleaks 负责凭证扫描；GeneLoop 提供字段提示、协议值保护、嵌套 JSON、局部别名、拒绝规则和各入口接线。没有训练独立的 GeneLoop PII 模型，也没有自研识别算法优于上游的证据。
- 问题：在相同检测依赖和任务条件下，公共模块能否减少身份/联系方式/凭证泄漏，同时保留 RSI 所需语义？漏检、误删、过度拒绝、协议或引用破坏都可否定其适用性。

## 外部数据选择

| 数据 | 用途与首轮安排 | 来源、许可与限制 |
| --- | --- | --- |
| PII Bench ZH | 首轮中文：正式文本 5000 条、聊天/中英混写 3000 条，8 类实体；按正式/聊天和实体类型分别报告 | [作者数据卡](https://huggingface.co/datasets/wan9yu/pii-bench-zh)。Apache-2.0。模板合成，适合作压力测试，不能等同于真实语料或独立人工标注基准 |
| Gretel PII Masking EN v1 | 首轮英文：使用官方 test，覆盖姓名、联系方式、账户及多领域文本；数据卡标注 test 5000 条，执行前再核对实际文件 | [官方数据卡](https://huggingface.co/datasets/gretelai/gretel-pii-masking-en-v1)。Apache-2.0，合成数据。`entities` 为实体值/类型，转换为跨度前核验空白、重复出现和歧义，不能擅自修正测试金标 |
| CredData | 首轮凭证：复用标注、混淆和上游评分公式；旧 Gitleaks wrapper 的 Category 接缝失败单列，另报精确行区间与文件指标，不称历史榜单复现 | [Samsung 原仓库](https://github.com/Samsung/CredData)。含人工复核标签、凭证混淆及现成评测入口。仓库代码/元数据许可与原文件许可分别处理，原文件按其来源项目许可；在 Linux 隔离环境准备，不执行下载来的项目源码 |
| Nemotron-PII | 扩展英文覆盖，测试结构化/非结构化格式及更广的 PII/PHI 类别 | [NVIDIA 数据卡](https://huggingface.co/datasets/nvidia/Nemotron-PII)。CC-BY-4.0，合成、带跨度。公开卡片和查看器数量存在差异，执行时以固定版本的实际 split 文件为准，不直接沿用宣传总量 |
| REDACT | 后续多语言/披露形式诊断，可使用其固定评测切分及 exact/partial 指标 | [原仓库](https://github.com/guneeshvats/REDACT-PII-Benchmark)、[数据卡](https://huggingface.co/datasets/guneeshv/REDACT-PII-Benchmark)、[独立数据条款](https://github.com/guneeshvats/REDACT-PII-Benchmark/blob/main/DATASET_TERMS.md)。数据访问 gated，需要账号接受条款；未接受或下载，不作为首轮依赖。代码 MIT 不等于数据也为 MIT |

当前仅评价中英文。多语言数据的其他语言不合并进一个“总体准确率”来描述现有能力。医学状态、一般日期、车辆标识等标签未必等于当前模块的承诺范围，先固定类型映射与策略范围，报告全标签集和支持子集两种结果，保留不支持类型的数量与限制。

## 已核验的来源版本与数据质量

| 来源 | 固定 revision |
| --- | --- |
| `wan9yu/pii-bench-zh` | `c350b94897af668517ff5de237d89f2ce2eaa6f0` |
| `gretelai/gretel-pii-masking-en-v1` | `e06eb1499ca8d54470f085021cd8e54f9efac7fd` |
| `nvidia/Nemotron-PII` | `b70ffaf5ff39e079776134c5bf4381f00a9fd1ed` |
| `Samsung/CredData` | `86a918283f086baf9ca896a892519cd8462dfe0a` |
| REDACT GitHub 评测代码 / HF 元数据 | `252232ac29669beeb99cb6474eeb2736761be508` / `1d7fef611cbaad42ba19666e7d7238ed45b264dd`；未获取受限数据文件 |

已下载两个中文 JSONL 并逐项验证 `0 <= start < end <= len(text)` 和 `text[start:end] == entity.text`：正式集 15662 个实体，聊天集 7544 个实体，共 23206 个跨度，未发现跨度不一致。文件 SHA256 分别为 `bcaa54909fd69c6737b8e442c4d740ce1bf5b95b7d4af70b2f2692010e1ff7a5`、`4ddacd78dfac49b723032de5e1c29c432a44049245e03a8ea960c86bbf3b765c`。这只是标注格式审计，不证明检测器正确或语料无偏差。

原文件、公开元数据和审计摘要留在私有 `.local/debug/privacy-benchmark-20261107/`；不将语料、秘密值或逐条原文报告提交 Git。其他候选目前只核验来源与版本，尚未完成语料构建或评分。

## 评分与对照

1. **识别层**：原拟复用 [Presidio Evaluator](https://github.com/data-privacy-stack/presidio-research)，其 0.3.2 会额外引入 Pandas 3/Transformers 5 等未冻结依赖，首轮改用独立的 [nervaluate 1.2.1](https://github.com/MantisAI/nervaluate)，不另写 F1。中文使用 Unicode 字符跨度，观测官方替换前坐标，半开区间转评分器闭区间。报告 strict/exact/partial/type、micro/macro、每类支持量，以及不区分预测类型的实体完整覆盖和金标外字符额外遮盖；冻结类型映射有粒度限制，F1 涨跌不能直接等同于隐私漏遮变化。
2. **模块层**：将相同文本放入预先固定的普通文本与原生事件包裹，走实际 `learning_view` / Web / SDK / 离线入口。金标实体、类型、敏感级别只交评分器，不能作为输入字段提示。分别报告拒绝率、成功准入覆盖率、准入后残留泄漏、拒绝原因及整个样本是否仍可用于学习。被拒绝样本不计作成功脱敏，不允许用全部拒绝取得高分。
3. **语义与工程层**：补 GeneLoop 专用的固定不含隐私任务检查：公式、表格数值、代码/协议标识、JSON 可解析性、别名一致性与宿主原件回查；这部分单独称项目补充集，不冒充独立公开 benchmark。工具缺失、凭证命中、未知共享字段和取消继续检查安全拒绝。规则与公式保留仅是代理检查，真正的 RSI 后继质量另需独立任务验收。
4. **对照**：原生 Presidio 与 GeneLoop 增强识别使用相同 spaCy 模型、语言和阈值，公开配置差异；凭证比较原生 Gitleaks 与公共准入；完整模块再测端到端收益及代价。检测分数与样本拒绝分数不直接相减声称提升，不引用上游榜单数字作为本地复现实测。
5. **耗时**：记录冷启动与热运行、每文档长度、吞吐和 P50/P95。进程内 NLP 与实际 TypeScript Python-worker 路径分开计时，不能用前者延迟代替后者。正常任务关闭/取消和后台学习处理分别计时。

## 冻结与执行顺序

- 首轮不改识别规则，先固定生产同版 Presidio 2.2.365、spaCy 3.8.7/模型 3.8.0、Gitleaks 8.30.0、模块源码、类型映射与评分器版本；数据及参数快照与结果绑定。
- 首轮没有训练或调参，直接冻结全量压力诊断，未完成中文模板家族/凭证来源仓库的独立留出，不能称为该种留出验证。Gretel 使用官方 test。后续开发和独立评价须按模板家族/来源仓库隔离；看过错误并据此修改后，该批数据只作回归，不再称为未见测试集。
- 首轮运行中文正式/聊天、英文官方 test、凭证三部分，先做标签/坐标适配的小样本核对，再执行冻结集；发现标注错误时保留原金标结果，另报争议敏感性分析。只共享聚合计数和经审核的合成反例。
- 全部在服务器独立检出/Home/输出目录运行，只读复用依赖。元数据下载与本地评分不调用云模型、不开生产共享、不改正式服务；如后续比较实际 RSI 模型行为，使用真实 API 并另记有效配置与费用。
- 首轮完整结果、失败尝试和 120 s 凭证评测预算见正式记录；预算内未返回的调用不计作拒绝或安全通过。5 个事后差异样例确认原文/JSON 包装会改变 Gitleaks 扫描信号。下一轮须先修公共输入边界、有效任务拒绝和协议词丢失，再启用新规则版本与实验 ID，不覆盖本轮负面证据。
