# GeneLoop 公共脱敏模块

本分支已整合 main `cdc3a6a9`（包括已合并的 PR159、PR160），首轮集成基线为 `d1863342`。公共脱敏能力不按 Paper/PPT 分支选择，现有场景和新增 MCP 场景共用 `src/adapters/geneloop_privacy.py`。在线TypeScript复用有界本地worker，SDK和离线导入CLI用同一worker的单次模式；直接Python调用也使用共同内核，但由调用方提供总预算。正式服务没有切换。

R5新增默认关闭的[官方Privacy Filter/CredSweeper候选](research/rsi/privacy-official-tools-r5.md)，由私有宿主配置和字节摘要显式选择，继承公共学习/导出准入。原类别及默认Presidio/Gitleaks规则保留，正常任务仍读原件；NLP依赖因官方异常清理修复更新为固定兼容组合。600条PII及24组语义控制的文本重放改善姓名/地址完整遮盖，但金标外遮盖/正文保留门槛失败；旧R5因依赖故障停止保留部分结果，新版本[完整评测](experiments/privacy-benchmark-20261108-r5.md)及最终回归仍待完成，不能称新后端已验收。默认路径也须携带新增的纯标准库适配模块，附加模型仅选中后端时加载。

2026-11-07 的 [R1 冻结基线](experiments/privacy-benchmark-20261107-r1.md) 保留不变。[R2 实测](experiments/privacy-benchmark-20261107-r2.md) 使用 `d832be12` 修复 JSON 包装、重复键、Unicode 拒绝与协议词问题，并重新执行完整回归和三基准；仍不能据此保证完全匿名化，学习材料继续视为受限数据，独立留出和产品验收未完成。

2026-11-08 的 [R3 诊断](experiments/privacy-diagnosis-20261108-r3.md) 固定已有 10 类文本口径，同时保留全类别压力结果与结构化标识缺口；逐条归因确认规范化导致部分姓名漏检。产品最小修正 `ea819fc6` 保留原命中并补原文姓名，未更换成熟工具或阈值。GLiNER/OpenMed 在独立解释器的对照属于已见样本研究：直接合并有正文遮盖代价，尚未设为默认或加入产品依赖。

[R3完整复测](experiments/privacy-benchmark-20261108-r3.md)另保留293次凭证未知、同准入残留未改善及首次并发回归失败；运行时配置修复后，按相同限时顺序复验通过。它证明局部姓名修复与相应接线，不证明完全匿名化或生产可用性已认证。正常任务继续读取原件，正式服务未切换。

## 数据流与入口盘点

R3之后的[源码/证据审计与调整方案](research/rsi/privacy-adjustment-plan-r4.md)确认的数字text类型丢失、重复键首次预解析和扫描器运行时信任缺陷，已在R4修复。公共类别/字段规则收敛到版本化策略及schema；运行时核验固定依赖版本，每次扫描核验实际二进制字节。金融/证件补充复用Presidio官方模式和局部上下文，未全局遮盖长数字。模型worker有界复用、取消及SDK原子派生写入已实现；完整质量验收与工程验证须分别看本轮结果，学习副本仍是受限数据，PR保持Draft。

| 边界 | 接线与用途 |
| --- | --- |
| Web / 桌面任务 | `dsh_web_tasks.ts`、`dsh_geneloop_tasks.ts` 在任务结算后异步生成 `privacy-learning.json`；真实任务默认尝试准入，mock 须显式诊断开关。桌面列表接收所有完成场景 |
| SDK / CLI / 研究运行 | `harness_runtime.create_harness` 组合 SDK 公开 run/close，先完成原关闭，再由后台线程对本次原生事件生成账号私有视图。需要立即读取副本时调用 `wait_for_privacy(timeout=...)` 并核验返回值；线程在解释器结束前完成内存中的有界批次，不写原始队列。保留原 observer、结果、取消、费用与 journal；派生视图不是执行见证 |
| 离线导入 | `geneloop_learning_trace` 接收选定文件、当前任务起点、终态和有效工具目录，与两个 Web 宿主共用投影器 |
| Paper/PPT 结构学习 | 原 `rsi_learning_trace` v2 只保留登记工具、参数形状与已见证绑定，无正文和身份值。继续交原编译器及留出认证，保留成熟库兼容 |
| 轨迹 / 修订学习 | `dsh_trace_rsi_learning.ts`、`dsh_revision_rsi_learning.ts` 的模型可见结果和错误交公共内核。run/call/packet 使用单宿主随机句柄；已有私有审计保存句柄和原标识摘要，不导出映射 |
| Builder / Evolution | `capability_construction_history.py`、`capability_proposal.py`、`capability_goal_proposal.py`、`capability_evolution_investigation.py` 在历史进入模型前处理，包含初始上下文和工具返回。私有原件与模型实际可见值分别审计 |
| 编译 / 认证 | `continuous_motif_learning.py`、`capability_script_learning.py` 等在账号内核验原字节、执行样例及来源；模型提案走上述边界。脱敏视图不替代原证据，不授予认证或执行权限 |
| 导出 | 公共 operation library 强制 `admit_publication`；online manifest、efficiency registry、construction library 的 `--public` 同样准入。默认私有导出供原认证、账本和宿主桥接，保留原字节，不作为可共享对象 |
| 可选共享 | 两个任务宿主挂载 `harless_rsi_sharing.ts`，只从当前账号完成任务生成类型化 `tool_flow`；不接收客户端正文或任意路径 |
| 正常执行 / 交付 | 原始任务、附件、成品、费用及权限证据按原账号范围保存。公共派生视图用于学习；用户下载自己的文件和正常任务模型/MCP 访问沿用原授权 |

新增场景通过公共宿主或 SDK 工厂运行便继承接线，不需新增场景脱敏器。直接实例化上游 SDK、自定义学习请求或发布器必须使用此模块。外部 MCP 自身留存需其部署方管理；历史私有数据不会自动回填或改写。

## 契约与成熟工具

`learning_view(JSON)` 递归处理字段名和值，也处理工具 stdout 中的 JSON。复用本地 [Microsoft Presidio](https://github.com/microsoft/presidio) 的识别和 Anonymizer，别名使用官方 [custom operator](https://presidio.dataprivacystack.org/tutorial/11_custom_anonymization/) 扩展点；项目补结构字段提示和入口适配。身份映射仅在单次调用内有效，不落盘。固定 Presidio 2.2.365、spaCy 3.8.7 / 中英文模型 3.8.0、[Gitleaks 8.30.0](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.0)，依赖、模型 hash 与来源见 `requirements-rsi-privacy.txt`。

- 姓名、邮箱、电话、证件号、银行账号、住址、私有路径、附件名和账号/会话标识等替换为类型化别名；同一材料中相同实体尽量保持关联，文件类型保留。
- 任务正文、模型回答、工具参数/结果中的语义可进入账号内学习。公式、技术标识、代码、数值和统计要求不整体删除；字段名含身份信息同样处理。
- 凭证字段或 Gitleaks 命中直接拒绝整份材料。处理前后均将完整 JSON 包、递归解码的字符串及必要的 NFKC 视图合并交给原生 Gitleaks stdin；不只扫描转义后的 JSON。原文仅在内存中组装，限制递归/节点与解码展开量，不截断后放行。工具缺失、超限或无法可靠处理同样拒绝，不回退原文或原异常。依赖按清单安装，验证时记录实际版本。
- Presidio 在统一的 NFKC 识别视图上检测，使用固定 `regex` 的 Unicode 字素簇将跨度映射回原文；规范化改变文本时，再用同一识别器补原文 `PERSON`，沿用脚本/协议保护并保留规范化的全部命中。未遮盖的字符保持原样，不因两次独立识别结果不同而拒绝整包。无法对齐时仍拒绝。协议词在正文中的完整词边界也受保护，只约束统计 NER，凭证和显式身份字段继续检查。
- JSON 使用标准解析器的重复键检查，CLI 和嵌套文本一致拒绝重复键及解析深度失败，防止丢弃前值后又原样保留含凭证的原文。普通非 JSON 正文仍走文本脱敏。
- 已标记或可识别的二进制字段、图像/音视频本体及媒体 base64 数据 URI 不进入视图。当前不宣称识别人脸、声音或图片中的个人信息；任意编码、未发表研究、商业机密和上下文间接身份没有自动识别保证。
- `admit_publication(JSON)` 要求处理前后相同，否则拒绝。它不改写或重签已认证源码/库字节，也不代替共享授权和对象白名单。

在隔离解释器安装 `requirements-rsi-privacy.txt`，将 `SSS_PYTHON` 指向该解释器，`SSS_RSI_GITLEAKS` 指向核对官方校验表的二进制。版本与实际二进制摘要须匹配 `config/rsi-privacy-tools.json`；当前仅登记已核验的Linux/Windows x64，其他平台不能仅靠手填路径通过信任检查。运行时不下载模型、不调用外部脱敏 API。所有学习材料仍视为受限数据，不能因通过识别就任意公开。

Linux/Windows x64 可用 `python scripts/install-rsi-privacy-tools.py --root .local/privacy-tools` 安装固定官方发布包；先核对固定 SHA256，再写入单个二进制并核验版本，拒绝覆盖已有安装。`--archive` 可传离线官方包。脚本只输出可用于 `SSS_RSI_GITLEAKS` 的绝对路径，来源和实际摘要写入私有安装清单。CI 的两个平台都显式安装同一份固定 NLP 依赖与 Gitleaks。其他架构需另外核验官方资产、登记信任表并执行平台验收；Mac包的这项集成尚未完成。

## 通用离线导入

提供当前任务的零基事件行起点及其冻结的 `effective-config.json`（`allowed_tools` 或 `tools[].name`）。

```sh
"$SSS_PYTHON" -m src.adapters.geneloop_learning_trace --authorized \
  --input .local/example/events.jsonl --catalog .local/example/effective-config.json \
  --scene future-custom-mcp --status completed --start 0
```

私有 v4 视图包含工具结构和脱敏 `content`，不保留原 call ID、时间戳、provider header 或二进制。SDK 输出附私有来源摘要，固定 `execution_witness:false`。无任务起点的旧任务不会猜测起点后共享。旧 v2/v3 仅保留给已有结构编译器和早期诊断，不限定模块覆盖范围。

## 默认私有与可选共享

对应 Issue [141](https://github.com/jingyio/GeneLoop/issues/141)、[142](https://github.com/jingyio/GeneLoop/issues/142)、[143](https://github.com/jingyio/GeneLoop/issues/143)、[144](https://github.com/jingyio/GeneLoop/issues/144)。轨迹共享、源码共享和可选遥测默认关闭；账号内学习不自动触发跨用户上传。

源内容先通过公共隐私准入，再生成 `geneloop.rsi-shared-object/v1` 的 `tool_flow`。v4 严格字段见 `schemas/rsi-shared-tool-flow.schema.json`。场景固定 `generic`，工具用样本内 `tool-0` 等代号，保留顺序、重复关系和结果状态；自定义 MCP 内部名称不上传。正文、语义内容、源码、附件、身份和自由扩展字段不在共享白名单内。流程对象不是可执行 Motif 或质量证书。

`/api/harless/rsi-sharing` 两个宿主共用处理器，先核验账号所有权。未知字段、嵌套敏感字段、失败任务、来源异常及脱敏失败均拒绝。

- `GET` 返回默认策略、共享是否可用及接收地址。
- `POST {action:"preview",task_id}` 返回完整冻结 JSON、字节数、SHA256、接收地址和十分钟预览 ID。
- `POST {action:"send",preview_id,sha256,consent:true}` 仅发送已预览且逐次同意的原字节。
- `POST {action:"cancel",preview_id}` 使未发送预览失效，发送中尽力中止并保留未知接收状态。

预览和同意仅当前进程有效，重启失效；每次只尝试一次，不自动重传、不跟随重定向或转发 Cookie。审计写入失败便拒绝预览或上传，审计只含固定事件与时间。桌面可查看、保存本地副本或取消，重新打开不恢复勾选。HTTP/WebSocket 自动出口继续使用 `apps/desktop/src/privacy.ts` 目的白名单。

私有 `GENELOOP_RSI_SHARING_ENDPOINT` 经两个服务启动入口进入策略；真实模式仅允许无用户信息、查询和 fragment 的 HTTPS，默认不设置。隔离诊断使用仅监听 `127.0.0.1`、随测试退出的接收端。正式接收服务的认证、持久回执和团队共享发布仍需独立验收。

## 验证与版本守卫

外部识别基准与工程回归分开记录。[验证方案](research/rsi/privacy-benchmark-v1.md) 和[首轮实测](experiments/privacy-benchmark-20261107-r1.md) 覆盖中文/英文 13000 条与 CredData 11030 文件；凭证超时单列为未知结果，不计作安全拒绝。现有实现复用 Presidio/spaCy 与 Gitleaks，没有独立训练的 GeneLoop PII 模型；项目规则和接线不能据工程测试通过宣称高准确率。

```sh
"$SSS_PYTHON" -m pytest -q tests/test_geneloop_privacy.py tests/test_harness_privacy.py tests/test_rsi_learning_trace.py
node --test tests/test_geneloop_privacy.mjs
node --test --test-name-pattern='platform privacy|RSI privacy' tests/test_dsh_web_tasks.mjs
```

服务器独立检出加载 `.local/remote-env.sh`，专项禁外网使用实际 Presidio/Gitleaks；全量按正确解释器、Node 兼容配置、字体及 `TESSDATA_PREFIX` 执行 `npm test`、`npm run smoke`、`npm run motif:check`。当前状态见[工程记录](debug/privacy-platform-20261106.md)，未跑完的检查不记为通过。

注册 Paper/PPT 库继续使用 `config/rsi-privacy-code-compat.json` 精确证书/当前摘要对并逐文件核验。私有旧候选按原守卫回退、重新认证。Windows Electron 真实进程用合成协议验交互；实际 NLP 在服务器验证。Issue 143 的 Mac 真实 Coding 仍依赖 DESK-01/04，不能以合成诊断替代。没有新增模型效果、科研质量或节费结论。
