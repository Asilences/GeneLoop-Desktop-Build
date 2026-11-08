# RSI 数据隐私交接

## 当前R5依赖修复与复测准备

- 依赖修复进展：旧R5在5000正式/3000聊天/1634英文后停止，所有部分记录/哈希保留，凭证阶段未启动。137条原worker前缀复现spaCy3.8.7异常后的`Vocab.get`故障；首个修复版3.8.12与旧依赖的真实失败保留，当前选官方3.8.18及严格固定兼容组合，不自写词表补丁。新V5环境的76项定向、实际中英模型/异常恢复/CPU/凭证ML和独立文档复核通过。对应规格为`env-r5-repair-v5.json`；新默认和候选完整基准及最终回归还未完成，勿用旧R5部分结果或R4回归冒充新版本验收。
- 原分支/草稿PR162继续，默认检测规则仍为Presidio/Gitleaks，固定NLP依赖已更新。`0ddc7f2d`接入默认关闭的官方Privacy Filter原始权重及CredSweeper1.19.6，`5d7698e2`为旧R5冻结版本；公开来源、字节守卫与私有宿主开关见[实施说明](../research/rsi/privacy-official-tools-r5.md)。正常任务、认证与正式服务不改。
- 600条历史PII及24组语义控制全部完成，文本并集多596处完整遮盖、旧覆盖丢失0、120/120任务要求保留；但新增金标外遮盖和正文保留门槛失败，不默认采用。该结果是先行文本重放，不是最终公共准入或独立留出。当前状态见[R5记录](../experiments/privacy-benchmark-20261108-r5.md)。
- 私有隔离根标识`.rsi-privacy-r5-20261108-VFBiTXZ6`：`frozen/`与`contract-env-v3/`保存已停止的旧R5；`repair-probe-code-v5/`、`contract-env-v5/`和`regression-env-v5/`为新修复诊断，日志在`results/`。新版本完整基准及npm/smoke/Motif、Web/离线检查尚待重新冻结执行，不覆盖R1–R4。默认路径须携带纯标准库模块`rsi_privacy_candidates.py`；额外模型仅显式配置时加载，固定NLP依赖按requirements安装。Mac与正式接收端仍待验收，Issues141–144保持开放。

## 当前R4实施

- 原分支 `codex/rsi-privacy-platform`，PR162保持Draft。检测冻结 `a4923292`，导入/SDK编排 `dcd1a990`，最终验收快照 `b39eac69`，三者检测文件/策略字节相同；实际变更和复现配置见[R4记录](../experiments/privacy-benchmark-20261108-r4.md)。本轮通过草稿PR交付，未合并或部署，正式服务、原件、认证与累计账本未改。
- 已修数字text类型丢失、事件/参数/catalog首次JSON重复键、运行时扫描器信任，并落地版本化策略/原因码、成熟上下文识别、有界在线worker与SDK/离线导入单次120秒边界。当前信任表只验Linux/Windows x64；桌面集成须携带新增Python模块、配置及schema，Mac工具资产/真实任务另验，不能直接宣称可分发Mac运行时已完成。
- PII13000条全部新调用：比R3增加1150处完整遮盖，原完整命中/额外遮盖/正文保留/拒绝数无退步；姓名/地址质量未解决。官方GLiNER PERSON-only的624条候选不达冻结语义/额外遮盖门槛，未设默认。64个已知凭证残留文件只作归因，不作总体成绩。
- 私有隔离根标识 `.rsi-privacy-r4-20261108-oDzoHF6O`：`frozen/`跑基准，`final-runtime/`保留首轮npm通过/Motif竞态失败，`settled-b39/`为修复后的最终检出；先加载各自 `.local/remote-env.sh`。最终 `results/regression-r4-settled/` 完整npm/smoke/Motif退出0：Python3392唯一、3178通过/214跳过；Node官方TAP1732通过/9跳过，均0失败。隐私79项0跳过，外部PDF/渲染和原生沙盒跳过详见新记录。
- 通用接线9组覆盖、实际SDK配本地fixture Provider、研究9/导出1及Web/离线14组通过（12准入/2拒绝），原件摘要不变。凭证8796准入/2101拒绝/133未知/0评测错误，同准入8629文件残留行2603→2596；全量后再次核验输入/标注与八份检测文件摘要。`results/`保留所有失败、定向与最终回执；API请求0，独立留出、真实RSI质量、Mac和正式接收端未验收。

最短检查顺序为：在 `settled-b39/` 加载私有环境后，以独立Home/短临时目录运行 `CI=true npm test`、`npm run smoke`、`npm run motif:check`；补充脚本为本目录 `scripts/privacy-benchmark/` 下的 `check_entry_boundaries.py`、`check_construction_export.mjs` 和严格 `check_entries.mjs`。本轮带私有路径的实际编排和参数在隔离根 `run-regression-r4-settled.sh` / `run-supplemental-r4-settled.sh`，不能对已存在结果目录直接重跑覆盖；重放三基准见[评测README](../../scripts/privacy-benchmark/README.md)。

桌面对接须一并携带 `geneloop_privacy_worker.py`、`rsi_privacy_tools.py`、`rsi_privacy_policy.py`、`rsi_privacy_recognizers.py`（均在 `src/adapters/`）、TypeScript的 `privacy_worker_pool.ts` 及现有入口改动；配置为 `config/geneloop-privacy-policy-v1.json`、`config/rsi-privacy-tools.json` 和 `schemas/geneloop-privacy-policy.schema.json`。依赖沿用 `requirements-rsi-privacy.txt`，解释器与扫描器通过 `SSS_PYTHON` / `SSS_RSI_GITLEAKS` 指定，不能用未核验二进制代替。入口与取消/错误约定见[接口](../interfaces.md#rsi-学习数据投影)，Mac资产与实际设备另验。

## 历史R3及更早记录

- R3后审计（2026-11-08，冻结`a3579aa2`）：新增7项合成入口复核，确认纯数字text预解析导致电话漏遮、重复JSON键预解析绕过源准入；安装器验证与运行时扫描器核验有缺口。详见[工程审计](../debug/privacy-platform-20261106.md)及[调整设计/实施顺序](../research/rsi/privacy-adjustment-plan-r4.md)。先修严格首次解析、保留文本类型和依赖核验，再按类别补上下文与官方GLiNER姓名候选；R4尚未实施。新main`1d1e16f4`与PR163的PPT学习/兼容表改动需独立整合检查，不外推本分支旧基线回归。
- 当前交付（2026-11-08）：原分支 `codex/rsi-privacy-platform`、[草稿PR162](https://github.com/jingyio/GeneLoop/pull/162)。已测规则 `ea819fc6` / 运行时 `4f6adedb`；正常任务和私有证据仍读原件，仅学习副本脱敏。R1/R2不改写，未合并/部署，正式服务与账本未动。
- [R3正式记录](../experiments/privacy-benchmark-20261108-r3.md)重新执行PII13000条/凭证11030文件；姓名完整遮盖增加270处，金标外遮盖增加5字符，无原先完整遮盖丢失。声明范围未完整遮盖30.95%/40.22%/35.27%；凭证同准入8630文件残留2590→2590，未改善，293次未知不能当安全拒绝。隐私质量尚未验收。
- 最新源码串行完整复测：3357个唯一Python用例，3143通过/214跳过；Node1723通过/9跳过，均0失败；续接/smoke/Motif通过。最终严格入口14/14一致、12准入2拒绝，原件摘要不变。首次并发Node3失败/2取消、旧入口13/14却退出0的反例均保留，未延长120秒限时；子进程现保留明确的Home/CPU配置，其他环境和凭证变量不透传。
- [规则/工具诊断](../experiments/privacy-diagnosis-20261108-r3.md)冻结原10类，不把范围外自动视为允许披露；七变体定位规范化姓名损失，GLiNER/OpenMed仅为独立CPU研究候选，不进入产品依赖。银行卡上游校验/正文边界诊断不删金标；尚需上下文识别、独立负例、身份关联与RSI质量验收。
- 本轮私有隔离根标识 `.rsi-privacy-diagnosis-20261108-76bl6wwu`；代码 `candidate/`（冻结规则）、`transport/`（环境修复），结果 `results/`；最终完整日志 `regression-transport-quiet/`。先加载各检出的 `.local/remote-env.sh`；重放命令见评测README，未知/失败保留独立目录。Mac真实Coding、正式接收端认证/持久回执未在本轮验收，四项Issue不关闭。

- 历史R2交付（2026-11-07）：[草稿 PR162](https://github.com/jingyio/GeneLoop/pull/162)，分支 `codex/rsi-privacy-platform`，最新已测规则 `d832be12`。正常任务和宿主校验读取原件；仅 RSI 学习副本脱敏。服务器完整工程回归已通过，Mac 真实 Coding 与正式共享接收端仍未验收，不提前关闭 Issue。已在 [141](https://github.com/jingyio/GeneLoop/issues/141#issuecomment-6683861349)、[142](https://github.com/jingyio/GeneLoop/issues/142#issuecomment-6683862014)、[143](https://github.com/jingyio/GeneLoop/issues/143#issuecomment-6683862447)、[144](https://github.com/jingyio/GeneLoop/issues/144#issuecomment-6683862771) 跟踪初步解决范围；PR159 是此前已合并阶段。

- 更新时间与交接人：2026-11-08，Codex。
- c8阶段先交付[原声明类别视图](../experiments/privacy-benchmark-20261108-declared-scope.md)，没有新检测调用；当时暂停后续诊断，当前已继续R3，见首段。
- R2历史结果：[冻结复测](../experiments/privacy-benchmark-20261107-r2.md) 使用 `d832be12`，PII 13000 条/凭证 11030 文件全部重新执行。已知包装差异 5/5 修复，重复 JSON 键绕过拒绝；语义集 24/24 准入、120/120 不变量保留，Paper/PPT Web/离线 14/14 一致。凭证准入 8840、明确拒绝 2101、评测超时 89、执行错误 0；未知结果不算安全拒绝。基于 R1 错误开发，仍需独立留出和产品验收。
- R1 历史基线：冻结产品规则 `68a4e4d7`（与 `bdef7b54` 应用代码相同），覆盖 PII 中文/英文 13000 条和 CredData 11030 文件。完整漏遮、额外遮盖、拒绝、凭证超时未知结果和分母见[首轮实测](../experiments/privacy-benchmark-20261107-r1.md)。该版未通过隐私质量验收：5 个事后差异样例均出现原文扫描命中而 JSON 包装未命中；项目语义补充集仅 14/24 准入、准入保留 64/68 项不变量，另有 4 项协议词损失。规则未随评分修改，原始语料与逐条报告保留服务器隔离目录，不进 Git。
- R2 未通过质量验收：中文正式姓名完整遮盖 58.44% → 55.14%，中文聊天总体未改善，聊天/英文正文片段保留退步，凭证超时 39 → 89。原生已触发且模块准入有 T 值字面残留的文件由 232 → 0，但原生也漏掉的凭证仍可能放行；不要以局部修复宣布完全匿名化。
- 目标与范围：GeneLoop 全场景公共脱敏模块，覆盖两个 Web 宿主、公共 SDK、离线导入、研究学习模型边界及公开导出；新 MCP 场景继承公共接线。继续推进 Issue 141、142、143、144，保留默认私有、预览和逐次同意。
- 通用验证范围：三 benchmark 的 13000 条 PII/11030 凭证文件测公共内核；Paper/PPT 的 14 组只是一项样本接线对照。最终 JUnit 另核实 9 个场景：两个 Web 宿主各 9/9、Web/离线/共享对照 9/9、公共语义投影 9/9，真实 SDK+本地测试 Provider 1/1、关闭生命周期 3/3；另补研究学习与四个公开出口边界 10/10。真实脱敏工具与模型/上游装配替身、合成 seed/registry 的边界见 R2 入口回执，不冒充所有真实产品路径验收。
- 当前实现：`geneloop_privacy.py/.ts` 提供本地 Presidio/Gitleaks JSON 内核；`geneloop_learning_trace.py` 提供通用 v4 视图和严格匿名工具流程。旧 v2 仅保留成熟 Paper/PPT 结构编译兼容，不限制覆盖范围。公开导出拒绝需要修改的认证字节；私有原件供原证据和版本守卫核验。详见[接口与盘点](../rsi-data-privacy.md)。
- R2验证：`d832be12` 完整 Python 3140 通过/214 跳过/0 失败（3354 个唯一用例，四组 JUnit 与收集清单核验）；Node 1722 通过/9 跳过/0 失败。续接策略、smoke、Motif 均退出 0。原件、认证与版本守卫保留；前候选 `f2af62cf` 的通过结果和随后发现的 JSON 绕过另存，未冒充最终验证。
- 以下为此前 Paper/PPT 阶段验证历史，当前通用模块以以上条目和本轮记录为准。
- 本轮基线：在原 `codex/rsi-privacy` 上整合 main d1863342 的桌面和演化实现。PPT v82 与 Paper v84 使用其 main 证书的精确旧/当前摘要对，实际运行仍逐文件核验；账户私有旧证书继续按原规则回退及重新认证。
- 本轮实现：`rsi_sharing.ts` 提供账号内原始证据到严格工具流程对象、冻结预览、同意、取消及异常回执。桌面 `privacy.ts` 限制自动网络出口，设置页显示完整共享 JSON 并允许保存本地副本。接收端默认不配置，仅在隔离回环接收端验收。
- 本轮桌面验证：真实 Windows Electron 45.2.1 的原协议与隐私场景 15 组检查通过，正常退出后独立进程重启检查通过。本地副本、完整预览与接收端收到的字节一致，合成敏感标记未进入接收端，网络中断无自动重传。最终记录位于私有 `apps/desktop/.local/validation/renderer-0195c19f-ffa3-4932-afac-7c5e20e45c99/`。早期诊断因隐藏旧对话框的选择器发生等待超时，改为只操作当前打开的对话框并等待移除；失败记录保留。
- 本轮服务器验证：最终源码 1fa48a94 的 Python 定向 97 项、Web/离线对照 4 项、共享/桌面 Node 定向 19 项通过；`npm test` 为 Python 3081 通过/214 跳过、Node 1687 通过/9 跳过，退出码 0。续接策略、无模型 MCP smoke 18 例及 Motif 重放 4 例通过，测试后检出仍干净。最终本机证据在私有 `.local/privacy-issues-141-144/server-final/logs-final/`；此前 b1c7906e 的完整通过记录和更早失败记录也保留。
- 本轮配置与失败：独立 Linux 检出保留真实 Git 元数据，Node 22.23.2、Python 3.12.15、SDK 0.1.5rc1、DSH 0.1.5-rc.3、Presidio 2.2.365、spaCy 3.8.7、Gitleaks 8.30.0。首次隔离 Python 缺少完整 PyMuPDF 路径，已在本轮独立虚拟环境复用完整 PyMuPDF 1.26.7 修正，初次失败记录保留。沿用已验证的字体、Tesseract 语言数据与 Node 兼容配置；包和正式环境未改。有效环境、源码版本与日志归入私有实验 ID `privacy-issues-141-144-20261106`。模型请求和付费均为 0。
- Issue 143 边界：Mac 真实 Coding 产品链路仍依赖未关闭的 DESK-01/04（155、136），当前结果为真实桌面进程与合成协议工程验收。四项 Issue 按实际证据跟踪，不把依赖项视为完成。
- 分支：继续使用 codex/rsi-privacy，本轮开始的已推送版本为 0c6f339；已验证源码 1fa48a94 已推送，[PR 159](https://github.com/jingyio/GeneLoop/pull/159) 已于 2026-11-06 合并到 main（`5e21c754`），其后仅补本轮文档记录。历史 v2 阶段起点为 36ccf00，当时注册证书基线为 main 5d73a4b，本轮兼容基线以首段为准。
- v2 已完成：投影校验参数形状、绑定和原始事件边界。现有学习器只把结构样本交给原编译、独立留出认证和发布流程。原任务、权限、费用与交付审阅继续由宿主私有证据核验。兼容表只接受指定路径的旧/新字节摘要组合，在线使用当前字节摘要复核。
- v2 历史验证：Windows 短路径隔离副本。45 项证书与投影定向测试、v2 投影和 Paper/PPT worker 合计 39 项、4 项带锁定 PyMuPDF 的跨语言生命周期测试。无模型 smoke 覆盖 18 例，motif:check 重放 4 个认证 Motif。Web 与离线投影对照通过。付费请求 0。
- v2 Windows 历史全量失败：固定快照的 Python 为 2127 通过、249 跳过、34 失败、30 项 setup 等错误。Node 独立全量为 1501 通过、55 跳过、17 失败，均为测试创建符号链接时的 EPERM。私有日志位于隔离验证副本的 .local/rsi-privacy-npm-v2.log 和 .local/rsi-privacy-node-final.log。早期混用 v1/v2 的全量结果已由固定快照取代。
- Linux 服务器复跑：提交 83c1185，恢复真实 Git 元数据，使用 Node 22.23.2 二进制、旧 glibc 兼容预加载、Python 3.12.15、PyMuPDF 1.26.7 和固定中文字体。Python 全量 2233 通过、207 跳过、1 失败。上轮 7 项全部通过，唯一失败为 File 集成测试创建会话时本地 HTTP 读取超时。同配置单独复测两次均通过，保留全量退出码 1。独立 Node 全量 1567 通过、8 跳过，续接策略检查、MCP smoke 18 例和 Motif 检查 4 例均通过。真实模型请求 0，正式服务未改动。
- v3 语义投影：按显式授权处理当前任务第一条原生用户指令。Presidio 2.2.365 和 spaCy 3.8.7 使用固定中英文模型，Gitleaks 8.30.0 扫描原文及处理后文本。现有 Paper/PPT 认证与发布仍使用 v2 结构输入。任何工具失败均拒绝语义样本。
- v3 Linux 专项：Python 16 项和 Web/离线一致性 4 项通过，均在无外网网络命名空间执行。首轮发现 1 处文件名漏检和 2 处语义误删，修正文件扩展名边界、实体识别语言范围和统计符号后，10 条中英混写合成样例的 22 处敏感标注均被遮盖，35 处任务要求标注均保留。合成凭证命中和扫描器缺失均拒绝输出，真实模型请求 0。
- v3 Linux 回归：常规 `npm test` 的 Python 全量 2233 通过、218 跳过、2 项 OCR 因缺少语言数据路径失败，保留该次退出码 1。补隔离 `TESSDATA_PREFIX` 后，两项 OCR 与 Paper/PPT 学习及证书相关复测合计 42 项通过。使用正确解释器重跑的 Node 全量 1567 通过、10 跳过。续接策略、无模型 MCP smoke 18 例和 Motif 重放 4 例通过。
- 限制：证书兼容覆盖仓库注册库，账号私有旧候选遇到代码变化继续回退并重新认证。v1 诊断输入须重新投影。无法核验关系的失败调用保留为编译屏障。全量 Windows 回归遇到可在干净 main 复现的环境和夹具失败。
- 接手下一步：1. 按 R2 的逐类型覆盖、准入残留及同分母结果继续处理剩余漏遮/误删/误拒绝；使用新版本和新实验 ID，补独立留出。2. 补 Mac 真实 Coding、可选依赖对应检查及真实 RSI 后继质量，不把补充集当产品验收。3. 正式接收端认证与持久回执另验收，默认关闭，生产发布另行授权。
- 权限与回退：只操作代码分支和隔离验证副本。没有访问正式任务、生产配置、历史轨迹或累计账本。本轮未发布，未生成正式服务切换点；候选代码可与本轮开始的 0c6f339 比对回退，正式服务配置保持原样。

| Issue | 当前交付与验收边界 |
| --- | --- |
| 141 / PRIV-01 | 默认私有、区分正常任务与可选共享、桌面出口白名单及固定事件审计已实现；产品链路仍随 DESK-01 验收 |
| 142 / PRIV-03 | 当前通用 v4 工具流程使用严格 JSON Schema、源内容隐私准入和样本内代号；旧 v2 为兼容诊断保留。凭证、私有路径、未知嵌套字段及异常拒绝继续回归 |
| 143 / PRIV-05 | 真实 Windows Electron 与隔离服务器的工程诊断通过；Mac 真实 Coding 任务仍待 DESK-01/04，未关闭 Issue |
| 144 / PRIV-04 | 完整预览、逐次同意、本地副本、取消和隔离接收端已实现；依赖 143 的产品验收，默认不开启正式共享 |
