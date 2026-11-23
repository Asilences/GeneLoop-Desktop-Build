# 公共脱敏 R4：实现与冻结复测

状态：本轮实现、候选筛选、三套基准全量、修正后的完整工程回归及通用入口补充核验已完成；输入与标注摘要在最终回归后再次核对一致。PR162保持Draft，隐私质量仍未验收，未合并或部署。[R1](privacy-benchmark-20261107-r1.md)、[R2](privacy-benchmark-20261107-r2.md)、[R3](privacy-benchmark-20261108-r3.md)及本轮首次失败均保留。本轮是已见数据开发及回归，不是独立匿名化或真实RSI质量认证。

## 实现与冻结边界

检测内核冻结到 `a4923292c874d2832bd10ed75fd42b4610d74a88`；离线/SDK编排为 `dcd1a99097ed831fe64408d3e1a5697fe7ced06d`，最新验收快照为 `b39eac69d7fa765ecdec47f54e5901bf10d768ce`。三者的识别器、共同JSON内核、策略、依赖信任表及schema字节相同。a492之后统一单次子进程期限/输出、Python `-B`和单调时钟检查；b39相对dcd仅修改Motif示例的退出等待及其两项测试，正常SDK关闭与检测规则不改。基准、冷热测量、首轮及修正后工程回归分别记录源码，不能混写为同一次运行。

- 数字形式的text保持字符串；事件JSONL、工具参数及catalog首次解析拒绝重复/转义同名键，避免在进入共同内核前丢失材料。
- `config/geneloop-privacy-policy-v1.json`及schema固定类别、字段、替换动作和保护词；策略语义SHA256为 `b65ff24fbdb5d28f9e2809c5f3b46113451e845f0a12f58a30d9ecf677977602`。日期、年龄、组织等身份上下文规则仍标记未实现，不因配置列名便宣称支持。
- 保留Presidio2.2.365、spaCy3.8.7/中英文small3.8.0、Gitleaks8.30.0和0.4阈值。每次扫描核验实际Gitleaks二进制字节；包/模型版本在初始化时核验，未知平台或漂移拒绝学习准入。当前资产表仅验Linux/Windows x64，Mac集成另验。
- 金融和证件补充复用官方 `CreditCardRecognizer`、`UsPassportRecognizer`、`IbanRecognizer`的模式，通过Presidio `PatternRecognizer`接入中文边界、上下文及明确字段标签。没有全局遮盖长数字，校验失败也不自动证明可以披露。
- 在线有界worker串行复用模型，别名每包重建；spaCy使用每次文本调用的memory zone。SDK、离线导入CLI及派生文件采集使用可终止的120秒单次子进程，先完成后输出/原子发布；同步Python函数的外层预算仍由宿主提供。正常任务、证据、版本守卫和账本继续使用原件。

工具来源、适用版本、安装及调用见[公共模块](../rsi-data-privacy.md)和[接口](../interfaces.md#rsi-学习数据投影)。这是一套成熟识别器、项目策略与宿主适配组成的模块，没有新增训练出的GeneLoop PII模型。

## 上下文候选：固定600条开发复核

先以 `f808fd31`在原R3选择的600条PII和24组语义控制运行真实工具，4个worker；非独立留出。原生预测600条均与R3相同，文本内核无处理错误。以下完整遮盖按实际替换区间计算，不要求预测标签恰等于金标标签。

| 数据，每组200条 | 银行卡完整遮盖 R3→候选 | 证件完整遮盖 R3→候选 | 新增金标外遮盖字符 | 原完整遮盖丢失 |
| --- | ---: | ---: | ---: | ---: |
| 中文正式 | 6→36 / 36 | 68→70 / 87 | 0 | 0 |
| 中文聊天 | 7→12 / 28 | 28→31 / 47 | 0 | 0 |
| 英文 | 17→18 / 24 | 未改变 | 0 | 0 |

合计增加41处完整遮盖，不据此声称姓名或地址已改善。准入迁移完全不变：200/200、200/200、199准入及1拒绝。同准入599条的字面残留869→828；这一口径与区间完整遮盖分别计算。24/24语义控制准入、120/120要求保留、标注身份值字面残留0，两项凭证字段控制拒绝。600条复核墙钟703.54秒，语义控制82.98秒；并发时延不当作生产SLA。

对应[开发聚合](artifacts/privacy-benchmark-20261108-r4/context-cohort-summary.json)、[同准入比较](artifacts/privacy-benchmark-20261108-r4/context-cohort-admissions.json)和[语义控制](artifacts/privacy-benchmark-20261108-r4/context-cohort-semantics.json)均不含原文或逐条预测。

首个上下文候选 `74f2b8d3`在真实工具专项中10通过/2失败，中文明确银行卡标签仍漏识别；保留原日志后，以成熟模式加局部字段前缀修正，`f808fd31`专项12/12通过。没有删除失败或降低验收线。

## 官方GLiNER PERSON-only：不采用

候选配置[model-person-r4.json](../../scripts/privacy-benchmark/model-person-r4.json)在评分前冻结。采用官方Presidio `GLiNERRecognizer`及 `TokenizerBasedTextChunker`，每块192 token、重叠32，单块额外校验384词/512 encoder token容量和全文覆盖；超限记未知，不静默截前缀。模型为固定 `urchade/gliner_multi-v2.1@443d26d6`及 `microsoft/mdeberta-v3-base@a0484667`，已核验safetensors、本地严格加载，不执行仓库代码或下载新权重。仅提交person标签，金标交独立评分进程。

独立候选环境复用已核验包的只读位置，不安装到产品环境；实际Presidio2.2.365、GLiNER0.2.22、Torch2.5.1+cpu、Transformers4.48.3、spaCy3.8.7、jieba0.42.1、NumPy2.4.6。所有624条均完成，两个历史development/confirmation分组都已见，不称独立验证。

并集是候选跨度与基线实际替换跨度经官方Anonymizer重放的文本层对照，沿用评分器固定替换分数；不是已把GLiNER装入完整公共准入链路。它检验本配置的额外遮盖代价，不证明所有GLiNER配置都不可用。

| 数据 | 上下文版姓名完整遮盖 | 加PERSON候选 | 新增金标外遮盖率 | 正文块保留 |
| --- | ---: | ---: | ---: | ---: |
| 中文正式 | 119/216 | 214/216 | +0.4029个百分点 | 8→8 / 8 |
| 中文聊天 | 67/189 | 181/189 | +1.0456个百分点 | 2→2 / 2 |
| 英文 | 93/129 | 127/129 | +1.5821个百分点 | 537→499 / 586 |

姓名增加243处完整遮盖，旧完整覆盖没有丢失，但金标外遮盖都超过预冻结0.1个百分点门槛，英文正文保留率下降6.4846个百分点，超过0.5个百分点；任务要求仅保留116/120，未满足120/120。**本配置不采用，不并入默认依赖，也不为本次结果重调阈值。** 金标外字符与正文块是误删代理，不表示所有被遮字符都允许公开；失败门槛与完整候选分数仍保留。

完整结果见[模型聚合](artifacts/privacy-benchmark-20261108-r4/person-candidate-scores.json)及[门槛判定](artifacts/privacy-benchmark-20261108-r4/person-candidate-adoption.json)。模型源码/权重文件摘要与已公开R3来源逐项相同，未把新的本地路径当作模型升级。

## 凭证残留归因：未盲加规则

用冻结R3规则，从1181个有字面残留的准入文件中按预定seed/hash取64个文件，4个worker、120秒期限复核。检测器不接收标注，64/64准入；219行可提取T标注中189行仍有字面残留，无不可提取行。这里是已知漏检文件诊断，不是代表性总体抽样；计数是标注行，不能等同于189个不同秘密。

残留长度4–7/8–15/16–31/32+字符分别31/36/71/51行；188行没有上游PredefinedPattern，1行标记aws-id。标注类别混有Password、Token、Key、Nonce、AppID等，不能从“长字符串”或“看起来像hash”直接推断动作。仍保留原T/F/X分母，不在看到成绩后排除某类。字面出现也不是对输出中原标注位置的测量。

本轮没有证据支持安全地全局降低熵阈值或取消allowlist；保留Gitleaks默认规则及显式秘密字段拒绝，不增加未经对照验证的凭证规则。模块仍会漏掉原生扫描也未识别的材料，这一缺口不以更多拒绝或超时修饰。

[诊断聚合](artifacts/privacy-benchmark-20261108-r4/credential-diagnostic-summary.json)仅发布标注类别/格式和样本选择摘要，原始值及逐文件结果保留私有目录。

## 三基准及工程验收

全量协议为[protocol-r4.json](../../scripts/privacy-benchmark/protocol-r4.json)和[credential-budget-r4.json](../../scripts/privacy-benchmark/credential-budget-r4.json)。PII13000条、CredData337来源/11030文件/67896行全部保留；32个PII worker，随后16个凭证worker/120秒，空prior，所有模块调用重新执行。原生Gitleaks新扫8350个命中，规则/位置与旧基线一致，48.86秒；全量回归与大基准分开。

协议由R3复制后冻结，`preceding_baseline`/`change`两项历史描述仍来自原R3配置，不能用它们认定本轮对照是R2或只改了姓名；R4实际由 `rule_commit`、策略摘要和 `candidate_adoption`绑定，逐条比较的上一版本为R3。保留执行文件，不在评分过程中追改这些描述。Windows传输配置的CRLF字节摘要与仓库LF摘要分别记录，并核对JSON语义。

PII全量2069.00秒完成，原生预测13000条与R3逐条一致，原生/公共文本处理错误均为0。新增1150处完整遮盖，其中银行卡954、证件196；全标签下旧完整遮盖丢失0，金标外遮盖字符和正文块保留均未改变，准入迁移也未改变。以下是预先声明10类的视图，全标签与标准strict/exact/partial/type仍在完整聚合中保留。

[PII完整聚合](artifacts/privacy-benchmark-20261108-r4/pii-summary.json)包含全标签、声明范围、逐类分数、时延和准入后残留，不发布逐条原始数据。

| 数据 | 声明类别实体 | R3未完整遮盖 | R4未完整遮盖 | R4金标外遮盖字符 | 模块拒绝 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 中文正式 | 15207 | 4706 | 3928 (25.83%) | 3088/63620 | 0/5000 |
| 中文聊天 | 7305 | 2938 | 2725 (37.30%) | 752/30305 | 0/3000 |
| 英文test | 10937 | 3858 | 3699 (33.82%) | 19340/798401 | 42/5000 |

| 已声明类别 | 金标实体 | R3完整遮盖 | R4完整遮盖 |
| --- | ---: | ---: | ---: |
| `PERSON` | 11529 | 6865 | 6865 (59.55%) |
| `PHONE_NUMBER` | 7565 | 6690 | 6690 (88.43%) |
| `EMAIL_ADDRESS` | 2473 | 2473 | 2473 (100.00%) |
| `LOCATION` | 3531 | 637 | 637 (18.04%) |
| `IDENTITY_NUMBER` | 4787 | 3368 | 3564 (74.45%) |
| `CREDIT_CARD` | 2029 | 669 | 1623 (79.99%) |
| `FINANCIAL_ACCOUNT` | 426 | 225 | 225 (52.82%) |
| `IP_ADDRESS` | 962 | 957 | 957 (99.48%) |
| `PRIVATE_REFERENCE` | 23 | 23 | 23 (100.00%) |
| `CREDENTIAL` | 124 | 40 | 40 (32.26%) |

正文块保留为169/169、23/25、12353/13830；同准入12958条的字面残留18546→17399，减少1147，分母与区间覆盖分别计数。`PRIVATE_REFERENCE`金标在这里仅为URL，不外推所有私人路径；CREDENTIAL文本遮盖也不是整包秘密拒绝率。姓名、地址等弱类没有因此改善，当前仍不满足隐私质量认证。

CredData全部11030文件完成新调用，T/F/X分母15753/48061/4082不变。8796准入、2101拒绝、133评测超时、0评测执行错误，分别占全量79.75%/19.05%/1.21%；只看10897个已完成结果，拒绝率19.28%。R3为8636/2101/293/0。共8629文件两版均准入，4971行可提取阳性标注的字面残留2603→2596。167个旧超时本次准入，同时7个旧准入本次超时；不能用总残留或更少未知数断言算法或worker造成可用性提升。

本轮准入文件总计仍有2645行T值字面残留，涉及1193文件；字面匹配不检查输出位置，重复标注不等同不同秘密。原生Gitleaks已标记且本轮模块准入的文件中，残留文件为0，不意味着原生漏掉的凭证已处理。完成结果的文件级拒绝矩阵为TP1272/FP764/TN5712/FN2024，未知及不确定金标另计；模块动作是拒绝，不能与原生逐行秘密识别的precision/recall混作同一指标。

固定内部原因码将2101次拒绝细分为credential_detected1768、policy_rejected298、scanner_timeout27、ambiguous_json6、processing_failed2。PII英文42次拒绝为credential_detected41、ambiguous_json1。旧聚合的legacy分类仍原样保留，诊断采用[逐条重算的原因聚合](artifacts/privacy-benchmark-20261108-r4/r3-r4-comparison.json)，不把工具超时算成功检出。凭证检测阶段墙钟4966.86秒，含子进程启动的编排4967.62秒。

[凭证完整聚合](artifacts/privacy-benchmark-20261108-r4/credential-summary.json)、[新扫回执](artifacts/privacy-benchmark-20261108-r4/native-scan-receipt.json)、[完整性核验](artifacts/privacy-benchmark-20261108-r4/verification.json)及[执行摘要](artifacts/privacy-benchmark-20261108-r4/execution-receipt.json)分别保留。凭证评分器复用的是本轮新生成扫描报告，`reused_completed_scan:true`不表示使用旧R1–R3扫描结果；新扫回执为false，记录实际48.86秒。所有输入、337份来源标注、评分标注及执行配置摘要均核对，R1–R3的41份旧公共产物与原清单相同。

## 运行成本、长尾与工程回归

大基准结束后，在最终运行时单独测量实际NLP/扫描器子进程：3次冷调用中位9.172秒，7次复用调用中位3.117秒、经验p95/p99为3.132秒；子进程常驻约489MiB、峰值约518MiB。4次创建包含取消后的恢复，别名逐包重置，语义控制保留；原始包不落盘。这是小样本合成串行测量，共享服务器条件下不能当生产SLA或因果加速比。[完整测量](artifacts/privacy-benchmark-20261108-r4/worker-profile.json)保留CPU和RSS各样本。

从本轮超时中按预定seed/hash选择1个372495字节文件，在实际模型已预热后重试仍超时。15秒间隔的私有采样栈出现spaCy/分词/识别调用，未能把长尾归因于某个单一算子；不能以1例外推全语料。保留原133个未知，不用诊断覆盖全量结果。[单例摘要](artifacts/privacy-benchmark-20261108-r4/warm-unknown-diagnostic.json)不含输入或栈中的私有路径。

首轮 `dcd1a990` 的原始 `CI=true npm test` 退出0，Python3390唯一用例：3176通过/214跳过/0失败；Node官方TAP1741项：1732通过/9跳过/0失败/0取消，JUnit叶视图为1739项/1730通过/9跳过。smoke退出0；随后Motif退出1，错误为临时目录清理时 `OSError/Errno39`，本轮不能因此写成首次全过。[首次聚合](artifacts/privacy-benchmark-20261108-r4/regression-initial.json)与原私有日志均保留。

原因是示例拥有的临时目录先清理，SDK异步准入仍在写派生副本。`b39eac69`仅在示例释放目录前调用现有 `wait_for_privacy()`；成功与原任务异常都等待，子进程120秒预算不延长，正常SDK任务关闭继续异步返回。新增检查用受控后台写者验证清理前收尾及原异常保留；服务器相关9项全部通过，随后真实SDK配本地fixture Provider的Motif四模式、46次公共MCP回放和4份历史证书核验通过。[修复复验](artifacts/privacy-benchmark-20261108-r4/motif-repair.json)保留数据范围，不作为真实模型RSI收益。

最新 `b39eac69` 从独立检出重新执行原始 `CI=true npm test`，退出0：Python3392项按完整nodeid与独立收集逐项相同，3178通过/214跳过/0失败；Node官方TAP1741项，1732通过/9跳过/0失败/0取消，JUnit叶视图1739项/1730通过/9跳过。smoke和Motif均退出0。完整npm墙钟3995.94秒；本轮没有用分组结果虚构单次npm退出码。[完整回归及环境](artifacts/privacy-benchmark-20261108-r4/regression.json)保留命令时刻、实际包版本与私有原始回执摘要。

跳过不计通过：Python214项中194项需要外部Poppler，其他包括OCR语言、CairoSVG/Pandas/SciPy、PPT renderer及平台/显式原生诊断；Node9项为Docker opt-in、bwrap条件或当前平台不适用的检查。[跳过清单](artifacts/privacy-benchmark-20261108-r4/regression-skips.json)提供计数和Node逐项来源。受影响的公共隐私Python79项全部通过、0跳过；不能据全量退出0声称真实PDF/渲染和原生沙盒环境已经全覆盖。

最终通用接线从完整JUnit核对：6个登记场景加chat/coding/future-custom-mcp，共9组；两个Web宿主各9组、Web/离线/共享9组、Python投影9组均通过。实际SDK使用本地fixture Provider；SDK关闭3项为受控替身。研究读边界9/9、construction导出1/1，以及Paper/PPT中英混写样例Web结算函数与离线CLI14/14一致（12准入/2拒绝），原件摘要不变。[覆盖回执](artifacts/privacy-benchmark-20261108-r4/entry-coverage.json)和[14组逐项聚合](artifacts/privacy-benchmark-20261108-r4/web-offline-entry-summary.json)将宿主接线与检测benchmark分开，不是只验证两个场景，也没有把全部benchmark机械乘遍UI。

最终回归后再读取11030个凭证输入、337份原始/评分元数据和三个PII文件核对摘要；八份检测/策略文件在a492、dcd、b39相同，b39相对dcd只改示例和其测试，原始比较结果不重算或覆盖。[最终完整性核验](artifacts/privacy-benchmark-20261108-r4/final-verification.json)与[27份聚合清单](artifacts/privacy-benchmark-20261108-r4/manifest.json)绑定这些证据。前期专项不叠加为本次完整测试数。

配置执行字节、仓库LF字节及JSON语义摘要见[配置核对](artifacts/privacy-benchmark-20261108-r4/configuration-bytes.json)；原始日志、逐条预测、金标值、命令中的私有路径仅留隔离目录。

## 实施后审计与下一步设计

按[R3审计编号](../research/rsi/privacy-adjustment-plan-r4.md#已确认缺陷与未验证风险)复核，区分已修行为与仍未证明的质量：

| 原审计项 | R4处理与证据 | 剩余边界 |
| --- | --- | --- |
| A01/A02 解析 | text不再转数字；JSONL、arguments、catalog首次严格解码；源准入和共享投影使用一次事件快照 | 宿主在本模块之前已经丢弃的数据无法恢复；第三方MCP必须交原始事件/字符串 |
| A03 工具信任 | 每次扫描核验实际二进制SHA；NLP初始化核对版本；安装与运行复用同一资产表，篡改控制拒绝 | Linux/Windows x64；不构成对恶意宿主或私下替换同版本模型文件的防御证明 |
| A04 类别漏遮 | 成熟金融/证件上下文增加1150处完整遮盖，无旧覆盖丢失 | PERSON59.55%、LOCATION18.04%仍弱；GLiNER本配置因误删/语义门槛退出 |
| A05 凭证残留 | 完整JSON及解码原文扫描继续保留，固定原因码；64个已知失败文件诊断未支持盲加规则 | 同准入仅减少7行字面残留；缺少规则覆盖的凭证仍会泄漏，不能称已解决 |
| A06 期限/资源 | TS排队和回复按单调时钟校验；SDK/CLI使用可终止的自有子进程，原子写派生副本；实测冷/热及取消恢复 | 每个模型进程约0.5GiB；大文件预热后仍可能超时，同步直调由宿主提供总预算 |
| A07/A08 语义关联 | 包内别名、原件宿主句柄和科学数值保护保持；条件类别明确标记未实现 | 跨包身份合并、多轮RSI、身份上下文日期/组织/年龄未验收；数值/十六进制address例外还需可信字段角色细化 |
| A09/A10 口径/验收 | 公共策略/schema固定生效实体；保留全标签、10类视图、未知及准入迁移；重新核对所有输入/标注摘要 | 已见语料复测；独立来源留出、真实任务、Mac及接收端仍是独立验收项 |

后续按以下三个可验收步骤推进，使用新实验ID，不修改本轮规则和金标：

1. **身份识别质量**：先拆分姓名/地址失败的语言、可信字段及上下文；优先评估Presidio支持的成熟中英识别器或独立实体模型。新候选先冻结配置、容量及全文覆盖检查，在新的来源/模板留出上同时比较漏遮与额外遮盖，保留120/120任务要求及现有负例门槛。GLiNER当前失败配置不得直接设默认，也不从本轮成绩挑阈值。
2. **凭证与长尾**：将已知诊断用于开发，不当独立评价；按真实标注类别核对Gitleaks可复用规则及可信字段角色，每次只增加有独立反例支持的配置。对未知文件另做阶段计时/受控预热，评估成熟分块接口；必须证明不丢跨块秘密和全文跨度、误删不增后再采用。不能截输入、放大期限或把超时当安全结果。
3. **产品验收与共享**：桌面打包补齐新增模块/策略/资产表，Mac单独验证；同一公共规则经过所有宿主后，用真实RSI多轮任务核对句柄、身份别名和质量。正式接收端另验认证、同意绑定字节、取消及持久回执。上述门槛完成前继续Draft、默认私有，Issue141–144按子项跟踪。

凭证后续可研究成熟的[Samsung CredSweeper](https://github.com/Samsung/CredSweeper)：规则加可选ML过滤能够作为独立候选，尚未安装、对照或加入默认模块。其[官方训练流程](https://github.com/Samsung/CredSweeper/blob/main/experiment/README.md)使用CredData，[架构文档](https://github.com/Samsung/CredSweeper/blob/main/docs/source/overall_architecture.rst)的阈值也参考CredData测试分数；因此先锁定实际版本/权重/配置并审计训练重叠，CredData上的改善只能作已见基准回归，仍需新的独立秘密样本。不能仅凭工具成熟就宣称它解决本项目的残留。

独立新来源留出、真实RSI后继质量、Mac真实Coding和正式共享接收端的认证/持久回执未由这些检查证明；Issue141–144继续开放。模型API请求0，未改正式服务、用户原件或累计账本。
