# 论文校对 当前交接

## 2026-11-05 当前审议入口（修订3，待用户核查）

当前研究HEAD为`7fd8c1fd`。向solver交付[通用上下文与产物协议](../evolution-context-protocol.md)及[完整推进方案](../changes/paper-semantic-evolution-20261105.md)。本轮核对恢复清单中30次任务、原事件和输入摘要一致；下一步为通用skeleton、分层调查和产物采用验收。本轮文档未提交/推送，模型调用0，尚未启动新的Evolution或judge实验。

## 2026-11-05 用户校正主批次

当前需复用的是10月21日五篇论文各两次的修复后实验`paper-multipaper-retest-20261021-v1`及其原对照。完整材料已在原`paper-script-motif`工作区的私有`.local/`恢复。已核对原20次对照及复测10次的事件与输入绑定，5份独立论文输入。定位清单为当前私有`.local/overnight-20261105/multipaper-20261021-recovered/manifest.json`，包含旧评价来源，仅供宿主审计，尚未送入本轮Evolution或judge校准。S4误报的两次后续检查使用同一份中间解析数据，未提供独立复核。

后续优先使用该批原确定性oracle，定位S4误报、旧QLoRA冲突证据聚合、选择与接管后剩余工作。原请求195→110、核心9/10为既有成果；两次重复按同论文输入保留，旧回放与新留出分开。详细判断见[计划校正](../changes/paper-semantic-evolution-20261105.md#当前主批次校正)。10月10日逐论断原件搜索退出当前优先级，作为历史记录保留。本次恢复与审计新增模型调用0。

## 2026-11-05 历史语义失败审计与质量反馈接线

- 本次范围为用户要求的旧轨迹定位，基于`codex/evolution-overnight-20261105`、HEAD `6499d32c`。只追加本节及[原实验复核](../experiments/evidence-evolution-20261104.md#2026-11-05-历史轨迹复核与瓶颈定位)，保留工作区已有R13未提交改动；本次未提交或推送。
- 已核对11月4日两轮原模型输入与输出，以及11月3日构造方法原认证。两轮Evolution仅有两份Runtime关系记录，无失败或反例，费用未知；补充已有容器信息后返回空候选。旧方法程序未认证，实际后继采用为0。
- 语义失败前史包括逐论断支持错误，但本次仅取得原公开报告，尚未重新取得完整原事件。论文参考评分92.5/93.5为同一评估者核验，不能写作独立LLM judge性能演化成果。
- 当前瓶颈为语义质量问题及其实际求解决策尚未与上述Evolution输入接通。下一步先恢复旧语义失败证据，确认任务独立性、具体未解决判断与既有能力边界，再定最小候选及留出验收；不自动恢复旧18格运行。
- 本轮模型请求0、模型费0，旧账本与原件未改。仅文档变更，检查Git diff和引用；无生产切换、合并、部署或外部写入。

后续按用户授权开始实现，先保存[关键判断与实施计划](../changes/paper-semantic-evolution-20261105.md)，再补原RSI质量协议到语义经历、分层调查与旧策略CLI的接线。`rsi_quality.review_quality`保留宿主固定的任务/工件/标准绑定与原判断；调用模型的回调及账本由原宿主提供。执行完成但质量失败可独立检索，具体检查及原件按需读取。PPT81/Paper83仅为来源兼容导出，生产未部署。

当前机制提交为`c4d86145`，上阶段证据封装修复为`34fb0b44`。最终本地全量Python2947通过/261跳过、Node1662通过/23跳过/0失败，smoke、Motif、RSI、效率和RAE检查通过。Linux冻结源码23文件597通过、418.57秒；3608文件SHA一致。模型调用0。原件定位已核对本地和V100的项目目录及7个相关结果/工作归档，未找到完整逐论断原运行。真实judge校准、Evolution语义候选与后继质量仍pending。接手先恢复可追溯语义评价材料，再校准裁判并运行最小真实后继对照。工作区另有其他会话的产物分配审计文档，本轮保留，不混入本次源码提交。

上述源码及结果记录已推送至[草稿PR156](https://github.com/jingyio/GeneLoop/pull/156)，结果记录提交为`3a14109e`。PR保持draft，未合并或部署。该head最后读取的Ubuntu/Windows检查为queued，本地和Linux结果分别保留，不能写成GitHub CI已通过。

## 2026-11-03：停止场景细节优化，回到公共机制

用户明确纠偏：不再针对Paper反复优化detail。预定18格`generative-primitives-002`未启动，新模型请求0；仅保留冻结资料，后续不得自动续跑。单源接口/诊断/缓存源码已保存至本地`9473647e`，新增源码提交未推送、未部署。全部既有自主C→D、失败和成本边界保持不变。

本轮无模型验证：本地2077 Python/1530 Node，Linux232 Python/43 Node通过；1项Windows专用检查跳过。相同D四输入各三次工程重放全部合格、结果一致，root中位22.958→6.150秒；[工程报告](../experiments/recursive-runtime-cache-20261103.md)不充当创造价值证据。当前重点改为公共构造入口接线及反馈驱动下一轮决策，详见[主线当前顺序](main.md)；下节“接手下一步”的Paper细节优先级已被本节取代。

公共接线现已完成于`984c1ca7`，夹具修正`57da12bc`：不再只由Paper研究adapter消费新算法；本地2142 Python/1530 Node、Linux公共整链相关37项通过。原生执行和认证真实，模型输入仍为诊断；完整费用反馈/自动再投资未完成。新结果、失败和当前接手任务统一以主线交接为准，不恢复18格Paper研究。

## 2026-11-03 上午：自主递归构造与组会交付

- 更新时间与交接人：2026-11-03上午，Codex；用户要求一小时内推进并准备组会，长期目标继续是完整效率反馈，未标完成。
- 起点/代码：PR123已合并到远程main `2f29d34a`。当前工作区分支`codex/recursive-construction-20261103`，新接口源码`4af5c56f`；私人`reference/`未动。本轮已推送[草稿PR #124](https://github.com/jingyio/GeneLoop/pull/124)，尚未合并或部署；后续提交仅文档与平台测试兼容小修，当前CI见PR。
- 已实现：同答`{program,composition}`、受限`composition_source`静态前端；认证前锁定模型选择/绑定，认证后只解析`$program`；编译失败repair按当前alias显示精确意图。多项目最终清单与显式有限研究预算；公共运行/权限/原库不改。
- 已观察：`continuation-study-001`四对真实检查点消融，on四格全合格、两格模型完整C→D，off两格合格、无完整C。on/off模型估费0.005062164/0.068178516，局部低92.6%，不是无C对照或新盲测。
- 从初始池结果：`generative-primitives-001`三组各两格；WithC1模型自主新写3273字符比较程序和C调用，DoRA/BitFit四项最终检查全过、每项2次C回执。D为`cap_c962563a382f4c1d2e1f598c`。实际用JSON意图，不是Python拼写。WithC0完整重写2/4；Flat1完整重写4/4且费用更低；另三格最终未评审。完整理论反馈未闭合。
- 验证/费用：本地1979Python通过/239skip、1516Node通过/20skip，Linux原生/公共129通过，smoke/motif通过，诊断无模型。真实38请求、USD0.139684764用量估费，原账本3315→3353，全部结算unknown0；实付、Codex开发、人机成本未知。
- 证据入口：公开[组会报告](../experiments/recursive-construction-20261103.md)含一分钟讲稿、完整矩阵和失败；[新协议](../recursive-construction-protocol-20261103.md)。私有`.local/recursive-construction-20261103/server-evidence/`保留两个study及配置/原始回答/质量/回执。服务器同名私有根`code-20`=main、`code-21`=`4af5c56f`，加载既有`.local/remote-env.sh`后用研究README入口；不重发已关闭格。
- 接手下一步：①减轻新程序调用与原生value包装等作者接口负担，仍由模型明确参数关系；②补array.items类型与确定数据形状错误的修复诊断，保留已提交后继失败的撤回/新机会；③再做可执行C/仅描述/无C的创造价值和同一任务流净节余→再投资→D→E对照，不追加重复任务凑回本。
- 权限/风险：真实DeepSeek持续授权、平台null与原累计账本不变；生产/默认聊天/外部应用/私人原件未改。独立研究入口可停用，回退源码到main `2f29d34a`；保留所有失败与不可变研究快照。

## 2026-11-03：Capability Frontier 七小时主线

- 起点：已核对远程 main `f594e19`，PR #122 已合并。当前分支 `codex/capability-frontier-20261103`，沿用当前工作区，私人 `reference/` 未跟踪。
- 更新时间与交接人：2026-11-03，Codex；研究已封账，独立草稿[PR #123](https://github.com/jingyio/GeneLoop/pull/123)审阅中，不自动合并。
- 当前目标与结果：引用一致性 C → 跨版本一致性 D，以及隐藏 C 的反事实；完整冻结见[七小时协议](../capability-frontier-protocol-v1.md)。C 已真实发布；三种冻结条件全部结束，最后条件 WithC 2/2、Direct 1/2 通过 Mamba 两对检查，Flat 一格失败、一格无候选。已发布 D 全部完整重写、未调用 C/J；自主 C→D 与递归效率收益 pending。
- 执行窗口：约 00:48–07:48（Asia/Shanghai）；先固定真实/公开输入、独立判据、组间可见能力和有限实验预算，再运行。沿用原累计账本；生产服务、旧库与默认聊天不改。
- 已实现：JSON 值桥接与65KB认证报告、双文件角色绑定、函数入口胶合与完整程序机械包装、按能力池版本恢复机会准入；复用原公共控制器/原生认证/TS执行与发布，没有另造Agent循环。
- 已验证：`e6d46f6`源码本地全量1879 Python通过/239跳过、1516 Node通过/20跳过；服务器原生/公共95 Python、前轮20 Node通过/1平台跳过。含最终源码的`a92f278` Ubuntu/Windows push/PR四项CI全部通过（含全量、smoke、motif:check）；后续仅文档收尾，当前head见PR检查。444个实验内部文件引用校验无缺失/变化，未读凭证或越出实验根的链接。
- 最终反馈接线：`e1f25ad`在最终研究封账后将独立质量回写现有Feedback。三份真实错误D退出后续Builder目录，四份合格D保留，原发布/证据不删。无候选、环境错误和未知结果不当算法反例，已撤回根不凭成功事实自动恢复；代码与实际结果见`frontier/feedback.py`和`code-16/.local/post-study-feedback-001/`。
- 构造续接：实际H0第一次请求已经学到正确JSON比较程序，入池后旧控制器清空上一步意图，别名c4→c5却无完成提示。`951aeea`新增按当前snapshot绑定的材料获取记录与当前别名，保留用途/证据、避免重发完整源码；普通repair仍不跨snapshot。第一份原程序+C的零模型强制组合也通过原发布/后继及Mamba两对，证据`code-17/.local/first-H0-material-diagnostic-001/`。这不是自主选择；修正后的模型行为/成本尚未重跑，保持pending。
- 复现与预登记：`10a0dc6`消除写死的日期/owner，默认新D采用已澄清语义；新实验显式冻结ID/带时区截止，旧配置不修改。`e6d46f6`在开跑前核对预算/截止/任务/初始池；原16格保存记录全部匹配。新日期/owner的CLI准备通过12原生检查，未启动模型；原账本未变。证据`code-18/.local/preparation-diagnostic-001/`、`code-19/.local/preflight-audit-001/`，新参数见研究README。
- 零模型诊断：C 本身在 Mamba 三版本全部正确；宿主强制接成 C(before)+C(after)+原模型比较程序，经原认证/发布/后继与 Mamba 两对检查通过，每对真实调用C两次。它是执行机制证据，不计自主选择。Flat 1原提案解除误拒绝后仍因影响传播过度被独立检查拒绝，未晋级。
- 费用与数据：C20请求/USD0.075317172，D三条件12+30+17请求/USD0.264833400；总79/USD0.340150572仅DeepSeek用量估费，新增unknown0；Codex工程调试、人工/机器未计价，账单未知。原账本3236→3315，前缀不变。code-08/13/14对应三个正式条件，后续快照仅零模型诊断/回归。结果同步本地`.local/capability-frontier-20261103/server-evidence/`，不含`.env`、dsh凭证目录与node_modules；逐请求用量、文件索引与引用审计均保留。
- 入口：服务器加载`.local/remote-env.sh`后用`node scripts/project.mjs python -m scenarios.paper_proofreading.frontier.run --request <新冻结request.json>`；最终验收用`frontier.finalize_D --directory <新study> --base <私有实验根>`。新freeze要求`--experiment-id`、`--deadline-utc`，准备器支持`--protocol`，旧study已封账不能重发/覆盖。公共说明见[研究README](../../scenarios/paper_proofreading/frontier/README.md)，精确SHA/反例见[实验](../experiments/capability-frontier-20261103.md)。独立研究分支已推送到草稿PR123，最后复现补丁随本次收尾推送，未合并/部署。
- 接手下一步：审阅独立研究PR和CI；先用新协议检验材料获取后的真实续接，再决定是否修改普通程序调用已有能力的接口或选择更需要既有抽象的任务。原H0第一次材料足以构造D但模型没走该路径，不可把“信息丢失已修”写成“自主递归已修好”。当前不追加模型调提示；不得把小样本配置差异、强制调用或旧视频收益称作本轮递归因果收益。
- 权限与回退：真实模型测试授权保留，平台null与原账本不变；无后台付费请求。外部应用写入/投稿/生产接管未授权。本分支独立研究入口可停用；回退共享变更时连同精确兼容配置一起回退到`f594e19`，旧库/证书与所有原始失败均保留。

## 2026-11-03：B 真实书目 Capability 验收

- 范围与版本：B 当时分支 `codex/rsi-real-acceptance-20261102`，A为`eba71e6`，B为`5efa221`；已通过[PR #122](https://github.com/jingyio/GeneLoop/pull/122)合并至 `f594e19`，尚未生产部署。A 的计量实现保留，私人 `reference/` 与原始书目不提交。
- 已完成：修复原生 Script 的只读校验和前缀、当前命令临时脚本及 `re.compile` 误拒绝；恢复新材料对 Builder 的描述；公共生命周期以宿主输入版本识别同名新内容并核对真实回执。没有增加 Agent 循环或改默认聊天。
- 真实结果：三项正常书目任务完成；模型缺口触发原学习器、认证入池和重试。模型提案在工程修复后保持字节不变，显式恢复发布；27 条验证与 29 条后继各 4 项检查通过。`cap_9ec2e88e6dc4540d4359e186` 已对下一 Builder 可见。**含人工工程恢复，不称全程自动恢复、C→D 或完整论文审查验收。**
- 费用：19 次真实 Flash/off 请求（含失败），用量估费 USD0.018788928；实付、人工/维护总成本未知。原账本 3217→3236、前缀不变，没有效率对照。
- 验证：macOS 全量 1840 Python/1511 Node 通过；Linux 原生定向 42 Python/6 Node、smoke/motif 通过。Linux 较早全量 2058 通过/10 失败，负面项详见[完整记录](../experiments/paper-capability-real-20261102.md)，不能称 Linux 全量全绿。
- 配置与复现：两端 `.local/rsi-real-acceptance-20261102/b-final-summary.json` 索引固定输入、原账本和所有结果；服务器执行先加载项目 `.local/remote-env.sh`。新运行使用新的输出/Store，保持证据引用的代码目录不变，不重放已发布任务。
- 下一步：先在未参与本轮的真实稿件/任务上检验覆盖；C→D 另立研究实验。任务结束自动采集、完整论文质量与成本对照、生产接管及任意中断恢复仍未完成。模型测试持续授权，外部写入/实际投稿未授权；未操作生产服务。

## 2026-11-02：离线 Script Capability 接线

- PR更新：[PR #121](https://github.com/jingyio/GeneLoop/pull/121)已推送并创建，未合并/部署。合并PR #119后保留main旧版本，按原工具从Paper v42兼容重导出v43，五项IR/程序/来源文件不变，58项兼容回归通过。合并后1809 Python通过，Node1506通过/19跳过/1旧上传ECONNRESET失败，失败保留。以下本轮原生实验数字是合并前验证，不能代替最新CI。

- 当前分支 `codex/efficiency-rsi-20261102`，基于 `8a414dd`；本轮本地提交见Git，未推送/部署。旧程序、证书、原件及账本保留。
- 已完成：`capability_adapter.py`、`publish_capability.mjs`、`verify_capability_outputs.py`接公共Builder/反馈/Store；原生只读Script后端及精确版本白名单。独立验收先覆盖字面BibTeX条目数、唯一键和重复键，不认证文献真实性。
- 已验证：Linux原生认证、组合、发布、不同输入后继和下一Builder可见，4项论文测试通过；21项Script/沙箱检查通过。全量Python1793通过/237跳过，Node1495通过/18跳过；Linux smoke通过。确定性组合和合成输入只属诊断，模型请求0。
- 未完成：真实历史任务的acquire路由、新真实Builder提案、任务结束自动采集、读取Motif接入及收益对照。默认聊天和原学习工作器未接管。修复`observation`缺失前的发布失败保留。
- 配置/复现/边界见[场景协议](../capability-scenes-v1.md#论文-script-接入2026-11-02续)和[记录](../experiments/efficiency-rsi-script-20261102.md)。测试使用项目Linux私有环境，原始产物仅存`.local/efficiency-rsi-script-20261102/`。真实API持续授权不变；本轮新增费用0、机器成本未计价。
- 接手下一步：固定真实任务训练/认证分区，运行原学习器路由；让真实Builder构造并逐阶段定位失败。回退可停用新scene_adapter；兼容策略与白名单应和本轮代码一起回退，不单独删除配置文件。

## 2026-10-23：回执传输独立 main 修复

- 目标与范围：用户同意依次推进传输小PR、明确反例下的候选失效、成本决定。第一步从最新 main `62cb9787` 新建 `codex/script-receipt-transport-20261023`，只整理有界无损回执，不带入尚未发布的集合/关系/反馈实验。原实验分支 `codex/paper-evidence-split-20261023` 在 `fd7f98c9` 完整保留，Desktop脏工作区、生产、原件及旧库未动。
- 已完成：Runtime校验并解码 `bounded_zlib_v1`，仅显式compactContext和新认证标记共同启用；模型始终看到可读stdout，包括解码结果更大的情况。认证器对来源/独立输入核对完整明文/压缩回执等价。原stdout、权限、版本和一次性授权守卫不变，旧明文路径保留；代码锁仍须实际重认证，不能直接补hash。接口见docs/interfaces，范围见[独立记录](../debug/script-receipt-transport-20261023-v1.md)。
- 已验证：40项定向通过；完整Python1519通过/235跳过，Node1372通过/15跳过/1失败。未修改网关的大上传ECONNRESET在原样main私有独立检出也8/9失败，已定位为main同现问题，未借本PR改网关。smoke/motif:check通过、0模型。12个原历史程序重新沙箱认证，ID/模板/描述不变，私有transport-main-library摘要 `beb12ae8…`；未更新生产库。
- 费用与配置：本步骤API0/USD0，累计6697/USD12.048783156，unknown13/pending2保留，非账单；本地/人工成本未货币量化。原始日志、原样main诊断检出、认证、state及PR材料放 `.local/paper-candidate-guard-20261023-v1/`。真实论文回执失败的付费回归属于先前实验分支，不把本次合成传输诊断称新论文效果。
- 接手下一步：仅推送/提传输PR供审阅，不合并/部署；远端CI需独立查看。其后另开分支做当前程序/输入/任务目标绑定的明确质量反例，不将相似结果、未选、重写或单次任务失败直接编译为错误原因；关系扩展继续暂停。无后台付费，heartbeat保持暂停。

## 2026-10-21：PR106 已提交，主线同步核验

- 范围与代码：`codex/paper-evidence-handoff-20261021`已推送，[PR106](https://github.com/jingyio/GeneLoop/pull/106)以main为base，供审阅，未合并或部署。远端main核对为`5373b0e5`，已是本分支祖先；`git merge origin/main`返回Already up to date，无冲突，无新增机制代码。
- 依赖：PR104尚未合并，本PR目前包含其Positive描述/Negative提示型RSI和DSH基础兼容改动；PR正文明确列出，建议先审104再收敛增量，不自动合并或关闭旧PR。不要将父PR的绿灯当作本PR CI。
- 验证：复用当前源码的五篇十次真实结果和源快照一致性核验，不重复付费测试。最近本地Python1519通过/235跳过、相关Node94通过/2跳过、smoke/motif通过；完整Node1368通过/15跳过/1项未修改gateway的ECONNRESET失败保留。远端Ubuntu/Windows检查以PR106当前head为准。
- 数据与费用：PR仅含代码、题面及匿名指标/结论，私人原件、凭证、原始轨迹未提交。PR准备新增真实模型调用0，累计仍6559请求/USD11.741008680保守估费，旧与新增共10 unknown/2 pending继续待核，不能称最终净降本。私有准备/提交记录在`.local/paper-main-pr-20261021-v1/`，十次证据见下一节。
- 接手下一步：审阅PR106当前检查及#104依赖；确认合并方式后再同步main。生产与公共默认关闭状态不变，不自动扩大自动学习、执行或外部写入范围。

## 2026-10-21：修复后五篇论文十次真实复测

- 目标与范围：按用户要求重启原五篇完整BibTeX文件任务，每篇两次，仅Motif；沿用旧10次Baseline与旧10次Motif，不新增普通缓存或Baseline。固定代码/库、不在中途改规则或回灌测试轨迹。
- 分支 / 代码：`codex/paper-evidence-handoff-20261021`，运行提交`ca1bbdcc`、接入修复`fe41cd39`。只新增实验记录，本地提交未推送/PR/合并/部署；原Desktop/SSS和生产未动。
- 已完成与验证：10/10正常结束、核心9/10正确；44工具Schema/顺序与旧Baseline一致、十次源码快照一致、题面/来源hash一致、原件未变。真实DeepSeek Flash/off，输出8192、300秒，cap/request=null、reset_history=false；原生压力检查点策略不变。无机制/接口改动，复用前轮相关94通过/2跳过、smoke/motif通过记录，未重复全量测试；旧gateway超大上传ECONNRESET失败仍保留。
- 实验结论：见[本轮复测](../experiments/paper-multipaper-retest-20261021-v1.md)及[十次指标](../experiments/paper-multipaper-retest-20261021-v1.csv)。Baseline195请求/94785输出Token，本轮110/52100（-43.59%/-45.03%）；未缓存输入288898→284698（-1.45%），上轮冷输入大增未重现。核心9/10与Baseline同通过率，但失败类型不同，不能称无损。
- 机制与反例：4/10任务实际接管21程序，8种程序、4种跨论文复用；Prefix两轮均正确，54→10请求、USD0.069582→0.024544。QLoRA首轮实际修正管道后接管4程序。其余6次未提交选择/缓存命令，不能将全部请求下降归因于自动接管或Embedding。S4第二轮模型原生解析器将8条有year记录误报缺失，明确保留；不是漏报一条缺失年份。最终执行后仍14次已知用量模型请求，包含必要总结，不能全算可省。
- 配置与数据：私有`.local/paper-multipaper-retest-20261021-v1/`保留protocol/授权、run.py、固定sidecar、结果/回答/Breakdown、comparison、mechanism-audit、verification；原生事件/账本在各web run。复用`execute-transport.json`的冻结原12程序/1复用契约/1Negative，库digest `02a887057fc0…`，compactContext=true、阈值不变。自动学习关闭、模型学习0、Embedding0、Negative提示0；这是消费已有学习成果的执行回归，不是新的RSI学习验收。
- 权限与费用：新增110请求，已知用量估费USD0.170113848；DDPM两笔502无用量，完整保留USD0.107458800预约，保守合计USD0.277572648，比Baseline USD0.243661320高13.92%，最终净费下降尚未确认。累计6559请求/USD11.741008680，旧8 unknown/2 pending保留，新增2 unknown/0 pending；账单未核。上轮137请求/USD0.336523500开发验证另列，不能隐藏或宣称本十次已摊销。
- 接手下一步：核对两笔未知账单；优先检查为何六次没有选用候选以及原生解析结果的覆盖/失效机制，采用局部回归，不重跑相同Baseline。少量同输入观察不能证明稳定一般收益，不直接发布或自动提PR。
- 回退与风险：本轮未改机制或生产配置，移除实验sidecar即可走原生路径；保留全部失败与累计历史。十次真实任务及runner全部结束，无后台继续付费；未联网核验文献真实性、未做PDF或全部文字人工盲评，仅本地macOS验收。

## 2026-10-21：上下文、输出字段与选择传输修复

- 目标与范围：接续五篇评测的冷输入/重复解析归因，在独立分支`codex/paper-evidence-handoff-20261021`开发；实现提交`a62a037f`、`73e3e224`、`fe41cd39`，仅本地，未推送/PR/合并/部署，Desktop/SSS脏工作区未改。
- 已完成：compactContext默认关闭，短候选ID/共享输入绑定/延迟无用协议；DSH公开post-execute保留全部stdout并私存完整证明；可选JSON形状认证及结果向原数据复用器传递；依赖切片标记常量输出并修正生成标签误判。选择入口支持固定`cd /work &&`，带管道的显式选择整体不执行，只提供一次保留原选择的重试命令；模型重交后才走原守卫。不改上游核心、生产、工具集合、阈值、原件或权限。
- 已验证：新增传输分支定向Node94通过/2平台跳过。最终npm test为Python1519通过/235跳过、Node1368通过/15跳过/1失败；未改动的gateway在途超大上传413测试发生ECONNRESET，隔离复跑同项仍失败，未宣称全量绿。smoke/motif:check通过。日志位于私有`final-test.log`等。所有库按当前源码实际重新认证，阶段3固定原12个模板/描述/输入契约及原复用/Negative规则；无改锁绕过。检查是免费诊断，不能冒充模型效果。
- 真实结果：本轮14次启动，4次冻结对象错误在调用API前失败，10次真实完成、核心8/10正确；阶段1四次均正确，阶段2及阶段3各有一次QLoRA漏第三组标题重复。阶段3 DDPM确实经历错误管道→诊断→模型修正→3程序连续接管，10请求/USD0.015021336；QLoRA直接写原生程序，10请求/USD0.023140296且漏检，不计合格降本。不是完整论文联网核验/PDF，也不是独立盲评。见[完整记录](../experiments/paper-context-handoff-20261021-v1.md)及[逐次指标](../experiments/paper-context-handoff-20261021-v1.csv)。
- 归因更新：原10次Motif+本轮前8次共18次中，3次已selected但带旧入口不识别的包装、均未接管，不能统一解释为模型未选择；任意中间shell前缀仍不支持。字段齐全/程序未崩不等于正确解析；QLoRA原生路径发现引号问题后只修语法检查，未重算已受影响的标题分组。字段覆盖/依赖失效仍未完整实现，不能把提示当验收机制。
- 配置与复现：`.local/paper-context-handoff-20261021-v1/`保留授权、各阶段protocol、全部失败/学习、认证/库、results/all-attempts/analysis/metrics/final-verification和原runner输出。入口沿用`run-script-motif-experiment.py --real-model --mode execute --script-config "$PRIVATE_CONFIG"`；当前`execute-transport.json`的库摘要`02a887057fc0…`。真实DeepSeek Flash/off，输出8192，300秒；原完整DDPM/QLoRA输入及公共bibliography-integrity题面，只做Motif局部回归、不新跑Baseline。阶段2新增JSON候选漏检，不推广该私有库。
- 权限与费用：沿用本地持续授权cap_usd:null / uncapped_user_authorized / reset_history:false。Agent136请求/USD0.335993232，另描述学习1请求/USD0.000530268（超原描述预算，未接受）；新增137/USD0.336523500，累计6449/USD11.463436032，均为保守代理估费而非账单。新2笔502保留USD0.113826300预约，旧6 unknown/2 pending保留；没有新增Baseline、后台继续付费或模型学习成果虚报。
- 接手下一步：先审阅字段读取覆盖与结果依赖；自动学到的程序需要能够区分“字段存在”“值是常量”“实际完成检查”。旧解析修正后，相关旧结果应局部失效/重算，不能只用更强提示告诉模型完成。传输修复已有真实路径证据，整体同质量稳定净降本仍未证明，不急于新增PR或更多全量运行。
- 回退与风险：移除实验sidecar走原生路径；旧库和所有历史失败留存，生产/认证库/原材料不受影响。仅本地macOS沙箱验收，未声明Windows或Linux真实效果。人工、本地计算及供应商账单尚未量化/核对。

## 2026-10-21：五篇论文 BibTeX 文件任务真实评测

- 目标与范围：用户要求给导师提供最新版论文场景效果，选择5篇论文的完整BibTeX文件完整性/重复检查，随后明确取消普通缓存组。仅Baseline与Script Motif，各篇各2次，共20次；不是联网真实性、正文对应或PDF交付评测。
- 分支 / 代码：`codex/paper-multipaper-eval-20261021`，运行提交`8c2e2d61`，包含启动时最新main `5373b0e5`及PR104的`b19bda66`；题面/结果记录在当前分支。未新增PR、未合并、未部署，当前评测记录仅本地提交；原Desktop/SSS脏工作区未改。
- 已完成：复用原`run-script-motif-experiment.py`；冻结并实际再认证12 Script算子/1契约/1提示型Negative，模型学习新增0。5份公开arXiv v1原始文件共598条，训练库无相同完整输入hash，未注入错误或截取。两轮顺序反转，测试轨迹不回灌当前库。公共题面为`scenarios/paper-submission/bibliography-integrity.prompt.md`。
- 已验证：20次真实DeepSeek Flash/off，输出8192，300秒期限内均原生结束；实际source hash/原件未改/模型配置均核对；所有src/scripts快照及44工具schema一致。独立bibtexparser1.4.3与条目头计数一致，按固定JSON字段离线验收；没有全部文字的独立人工盲评。仅新增文档/题面和指标，未改机制代码，不重复完整npm test或付费全场景。
- 实验结论：见[完整评测](../experiments/paper-multipaper-eval-20261021-v1.md)及[20次指标](../experiments/paper-multipaper-eval-20261021-v1.csv)。Baseline195请求/USD0.243661320，Motif165/USD0.240745620；请求-15.38%、输出Token-18.89%、Agent时间-29.22%，费用仅-1.20%，核心完全正确9/10→8/10。双方核心正确的7配对中Motif反高7.85%，只作事后诊断。未证明同质量稳定净降本。
- 机制证据：6/10 Motif任务发生42次认证结构执行，10种程序、8种跨至少两篇复用，覆盖4篇；不是净少42次API。Embedding/Negative提示实际0次，不能归因于它们。片段完成后仍98次模型请求、USD0.10982431；Prefix两轮都接管8程序但实际8→38请求，后续路径差异显著。
- 失败与归因：QLoRA两次均漏同一组标题重复；同轨迹已有一个解析器返回3组，另一个只认花括号字段返回2组，最终取211计数却保留2组，冲突证据未统一验收。S4首轮Baseline拒绝已存在且hash一致的当前输入、返回null，不能称正确对照。Mac原生文件IO的Linux descriptor限制为B8/M5次，M另1次其他错误；全部保留，不能代表Linux生产。
- 费用核算：命中输入-515200省USD0.0030912，输出-17907省0.0214884，冷输入+72213增0.0216639；首请求已有23268冷输入增量，余48945来自后续路径，不能全归为目录或纯算法开销。历史描述/Negative学习15请求/USD0.013573896另列，若全部摊到当前十次使用不再净省。历史14来源/认证任务127请求/USD0.164169312另列，不混分母。
- 冷输入追查：仅离线重算20次既有日志，无新付费。首请求+23268，后续扣除上一模型输出的净上下文增长代理量+53980，既有上下文未命中剩余量反而-5035，合计+72213。每任务初始system固定多8036字节，其中2353为本轮零调用的数据复用协议；没有观察到反复system更新。42次自动结果61691字节，普通结果另232263字节，相比Baseline全部192676字节显著膨胀；DDPM接管后误解析产生16750/7157字节结果。完整源码已用句柄隐藏，不能将问题归为重复注入代码。具体计量/边界见同一实验记录；私有analyze-cold-input.py/cold-input-analysis.json可复核。字节不是Token，未把分析当成实测节省。
- 配置与数据：`.local/paper-multipaper-eval-20261021-v1/`保存protocol/授权、下载可用性、原始文件/预生成oracle、固定库/编译状态、逐次log/回答/Breakdown、results/analysis/enriched/final-verification及复现脚本；原始事件/账本仍在各web run。库digest `70bfa012…`，阈值.88/.04/.6不变；压缩为native-pressure-checkpoint-v1。凭证/原始资料/日志不提交。V100拒绝SSH，按既有授权本地运行。
- 权限与预算：cap_usd:null / uncapped_user_authorized / reset_history:false；新增360请求/USD0.484406940，累计6312/USD11.126912532保守估费，非账单；新pending/unknown0，旧6 unknown/2 pending及V100旧账继续待核。所有任务及本轮Embedding进程已结束，无后台继续付费，未改原件/生产/公共库。
- 接手下一步：先让完整范围和字段级结果可验收，对2组/3组冲突局部核验并确保最终不丢失已有证据；再减少不接管时目录冷输入及片段完成后的重复脚本。不要以库数量、42次结构执行或单次便宜结果代替净降本结论。若改变机制/模型/平台，另开实验ID；不要覆盖这轮失败。
- 回退与风险：本轮仅独立实验和记录，停止/移除私有sidecar不影响生产；保留全部原始来源、历史库和累计账本。私有库不构成公开自包含benchmark包，未声明Windows/Linux真实模型效果。

## 2026-10-21：数据驱动证据程序复用实验

- 分支`codex/motif-cost-learning-20261021`，实现`76ca3e2`；新增从真实原生代码及前后快照学习的配对证据程序，独立新输入认证，TypeScript按模型选择、当前输入和版本守卫执行。不是模型权重训练。
- 最新匹配25→16次请求，864,346→501,764总Token，USD0.03208103→0.02229210，实际认证执行1次。全部数字／p95／配对t区间及判定用独立实现复算一致；没有人工科研盲评，不宣称稳定同质降本。
- 此例仅覆盖固定配对协议的证据复算，研究问题与审阅判断仍由模型完成，不替换原校对／Script RSI库。普通路径、File SDK和上游DSH保留；实验默认关闭，线上仍7e167ed。
- Linux完整Python1718／Node1359通过（各4skip），smoke/motif通过。所有旧失败、训练／认证／机械重放和费用见[成本学习记录](../experiments/three-scene-motif-cost-learning-20261021.md)；本地可审阅包位于`.local/deliverables/geneloop-motif-cost-learning-20261021/`，私有原轨迹不提交。
- 后续扩大稿件与协议覆盖；先用[接口](../interfaces.md#artifact-motif-独立实验接口2026-10-21)独立复测，正式发布仍走统一服务入口。以下段落按其历史日期保留。

## 2026-10-21：提示型 Script RSI 闭环

- 更新时间与交接人：2026-10-21，Codex。
- 目标与本次范围：只接通提示型Negative Motif自动生成/独立审核/发布/后继使用的小闭环。沿用已有编译器与同一私有store；未扩大自动早停、生产或外部写入权限。前轮Positive描述闭环及费用保留在Git历史与对应实验中。
- 分支 / 代码：`codex/paper-negative-learning-loop-20261021`，基于本地`40d015ca`，已通过`3a295837`同步main `73591f62`并保留两侧文档，兼容实现为`99e1b031`。已推送并创建[PR104](https://github.com/jingyio/GeneLoop/pull/104)，未合并/部署；远端CI以该PR当前检查为准。父PR100状态不等于本分支CI。Desktop/SSS的其他脏工作区未动。
- 已完成：`script_negative_learning.py`复用当前原生失败编译，两个不同任务且工具源码一致才有候选；有界模型生成+独立审核，强制prompt_only，审核缓存与失败不自动付费重试。`advance-script-motifs.py`区分完成任务Positive历史和已结束任务Negative历史，发布同一不可变round。`script_learning_store.ts`接入negative_file/digest与冻结加载；Runtime实际失败后投递建议。默认无negative-learning.json不启用。
- 接线修复：自动生成12个Positive算子而实验未配置Embedding，曾因Invalid URL连带停用整个Runtime；`optionalScriptRuntime`现对空库直接跳过，对非空匹配器初始化失败仅局部回退，Negative/Reuse和原生Agent继续。完整配置下原cache catalog保持可用。库摘要/来源/代码锁失败仍保守拒绝。初判为空库已纠正，不以新增算子数量称收益。
- 已验证：最终完整Python1359通过/213跳过，最终完整Node1206通过/5跳过；相关Python35、Node34定向通过，smoke与motif:check通过。确定性测试仅作诊断。完整Node曾有1项既有MCP子进程5秒期限失败，单独7项复跑及停付费任务后的完整Node均通过，未放宽超时、未删除失败日志；并行负载原因尚属推测。
- main兼容更新：使用DSH的`isAgentLoopRequest`标记绕过compaction等辅助请求；自动提示规则逐失败见证绑定目标参数schema，无关工具新增允许提示复用，目标变化仍失效，早停规则不放宽。合并后Python1517通过/235跳过、Node1357通过/15跳过；相关Python38/Node38、smoke/motif通过。见[main兼容记录](../debug/paper-rsi-main-compat-20261021-v1.md)。
- Windows CI修复：首轮2项失败定位为worker发布指针使用系统反斜杠，违背共享POSIX路径协议，继承时被拒绝。已统一三种资产指针为`as_posix()`并保留安全校验，原发布/继承回归补充格式检查；首轮失败不删除，远端结果以PR104最新提交为准。该序列化修复不另跑付费实验。
- 真实结论：见[Negative闭环验收](../experiments/paper-negative-rsi-20261021-v1.md)。同论文两种历史失败候选，非七篇独立论文。A/B任务传输失败但原生结构错误仍自动采集；学习400后做了一次局部worker恢复。C自动发布5da69dc7…，D精确消费并提示；D结束自动重新生成/审核提示，另编译12个正面算子。E局部发现组件接线问题。第二次局部重编译/当前loader认证后，最终F/G均在当前代码下真实命中并投递，F自动发布a21a7de1…由G精确加载，源码与冻结快照一致。两次人工worker恢复单列，不冒充自动触发。
- 质量与限制：C/D均有实际7页PDF及工具交付回执，但在最后组件隔离修复前；最终F/G为45秒投递检查，主动取消，未重复完整恢复。没有重检文献真实性或逐页视觉验收，不能称完整论文质量合格。D仍尝试不合法单章重组且保留旧说明；提示不保证修复成功。A通用summary把原论文图片PDF算成报告，本轮已按真实documents产物纠正统计，未改旧原始summary。
- 费用：本轮Agent157请求/USD0.514436304保守估费；学习5请求（1次400失败+两组生成/审核）/USD0.004753800，合计162/USD0.519190104。已知观测费用USD0.271771704，其余预约保留。新增未知用量3笔、E汇总时1笔pending，旧3笔继续待核；供应商账单与V100历史未核。本轮无完整请求skip、无自动早停、无净降本证明；局部取消与完整恢复不共用分母。累计5918请求/USD10.425416136，历史不清零，人工与本地计算未货币量化。
- main兼容真实检查：两次60/180秒局部任务均取消，无报告PDF；第一次未到失败匹配，第二次精确加载前次自动发布库，在44工具环境送达5次Negative提示，无skip/早停/fallback，无人工worker恢复。未证明恢复成功或净降本。新增学习2请求、Agent32请求，合计34/USD0.217089456；累计5952/USD10.642505592保守估费，新增pending1/unknown0，旧6笔unknown及1笔pending保留。当前压缩为`native-pressure-checkpoint-v1`，不可沿用前轮关闭压缩配置；所有新快照与账本在`.local/paper-rsi-main-compat-20261021-v1/`。
- 配置与数据：`.local/paper-negative-rsi-20261021-v1/`包含授权、计划、A–G日志、两次manual-recovery、learning-store、请求/响应、审核、所有失败、aggregate、final-verification；逐run配置/源码快照在`.local/script-motif-experiments/<run_id>/`，原始事件与报告在对应web runs中。真实DeepSeek Flash/off；Agent输出32768，学习1536/max_rules1；正面mode shadow、Negative prompt（有干预）；未调用Embedding，压缩关闭。原恢复prompt SHA443bd3f6…、来源SHA4bd41694…，均沿用历史真实输入。私人材料/日志/凭证未提交。
- 最短入口：按README项目环境启动现有`run-script-motif-experiment.py`，同一`--learning-store`与私有sidecar，store放严格配置`negative-learning.json`：schema_version1、implementation_files为受信工具实现相对路径列表、model deepseek-flash、max_output_tokens1536、max_rules1、cap_usd null。完整有效JSON、变量化复现命令见接口及实验。必须保留既有无限额实验授权和账本；不是公共产品付费默认。
- 权限与预算：沿用已授权本地真实API实验，cap_usd:null / uncapped_user_authorized / reset_history:false；请求不限、输出有界、全部失败/重试/预约累计。本轮没有新自动execute，原生工具只写授权隔离报告产物；未改原件、投稿、生产或外部应用。已停止本轮所有真实任务，不安排后台继续付费。
- 未完成：自动学习仍只生成有依据的历史检查建议，未生成执行失败谓词/早停权限或通用因果机制；仅一个结构错误家族与同论文恢复变体。正面匹配器因无Embedding配置在最终局部任务中停用，不能据12算子评估正面执行收益。
- 接手下一步：兼容回归、局部实测及PR104提交已完成；检查其CI并由用户决定是否合并，不自动合并/部署。若继续降本，先分析提示后重写完整参数/报告的调用，设计一次有类型局部修订交接；不重跑完整Baseline，不扩大到其他场景或用库数量代替收益。
- 回退与风险：移除新store中的negative-learning.json可停用负面学习；已有自动负面指针仍会加载，若需完全停用同时从实验sidecar移除learningStore与negativeLibrary并停用worker环境。保留历史store与账本，不清空.local。旧库迁移必须实际重编译/认证，不能改hash绕过。仅本地macOS验收，未宣称跨平台生产支持。

## 2026-10-20：批量控制与PR100历史记录

- 更新时间与交接人：2026-10-20，Codex。
- 目标与本次范围：本轮优化批量选择、连续执行与完成交接，保持同库做真实BibTeX局部任务。用户最新明确以RSI闭环跑通作为本轮验收目标，报告质量不作为当前阻塞项；现有真实局部验证足够，本轮不再追加完整论文、全场景或Baseline测试。未部署。
- 分支 / 代码：实现提交30ee31d，基于a590080（已跑通自动Script RSI），验收说明50f1b5c。[PR100](https://github.com/jingyio/GeneLoop/pull/100)已按用户授权合并至main，merge commit为1055a4f；合并前Ubuntu/Windows的push及PR四项CI全部通过。未部署生产，原Desktop/SSS工作区未改。
- 已完成：script_execution_frontier.ts支持一次选择1–8片段/最多16节点，旧candidate_id兼容，严格候选/版本/回执校验，失败停止后续队列。完成不再伪装邀请；初始候选可提前提供，稳定目录置前、当前绑定/随机ID置后。script_motif_runtime.ts允许scratch未创建时绑定批准上传，减少重复目录并保留不适合自动绑定算子的显式缓存入口。无新工具/算子、无阈值放宽、无上游Harness修改。
- 已验证：最终npm test为Python1329通过/213跳过、Node1201通过/5跳过；相关定向36通过，smoke和motif:check通过。当前M发布库的owner/摘要/执行代码锁加载通过；这些检查属于免费诊断，真实模型证据另见实验。
- 实验结论：[批量控制实验](../experiments/paper-frontier-batch-20261020-v1.md)。9次真实局部运行E–M连续接管3–8个程序，原生工具/过期选择错误均0。G/H/I/J/K/L/M与旧C/D实际加载的programs和contracts逐项相同、题面/工具Schema相同，改代码后真实免费再认证，未只重算SHA。E/F使用稍后库，仅作开发观察，不作同库归因。
- 费用与反例：旧100条18请求/$0.025559700、26条6/$0.007911264；最终L为7/$0.018895596（-26.1%）、M为4/$0.007330920（-7.3%）。同配置H/I分别-6.7%/+16.9%，不能只选便宜一次。J仅2请求，但K便宜52.4%且质量失败，不计合格降本。接管数不是净少请求数；当前只支持局部费用观察，不证明完整论文或稳定同质量收益。
- 质量与成因：K把实际100条/99唯一键写成98唯一键，采用了后来覆盖不全的原生解析，还混淆行号/序号。补充冲突交接提示后L仍将无BOM写成有BOM，并有头部格式前后矛盾。J/M核心26条盘点可核对，但文字未全面合格。提示没有解决事实校验，不把新提示称为编译Negative Motif；未独立人工盲评。全部回答/不合格结果保留。
- 自动学习：M当前使用固定旧D对应算子，结束后在新的私有learning-store自动发布12算子/1契约，12.31秒、模型请求0，供下一任务使用。旧store/库未改。前轮A2→B、C→D精确自动交接证据见[RSI闭环](../experiments/paper-rsi-live-loop-20261020-v1.md)，本轮未破坏该接线。
- 配置与数据：.local/paper-frontier-batch-20261020-v1/含prior-runs、授权、E–M回答/breakdown、aggregate、各次免费再认证、source/effective-config摘要与learning-store。输入SHA前缀1142caced119（26条）、4005000c6d65（100条真实子集）；题面沿用d055aeefc57f…。真实DeepSeek Flash、off、输出8192、费用/请求不限、reset_history:false、压缩关闭、无embedding调用。最短复现见实验文档。
- 权限与累计：只读任务副本，不联网、不导出、不改私人原件、不写外部应用。新增57请求/$0.095528316代理估费；累计5698/$9.828635508。新增pending/unknown0，旧3笔、服务器历史和账单仍待核。编译模型调用0，开发/计算/人工未量化；所有真实任务已结束。
- 验收与后续：论文独立实验入口的RSI机制闭环已跑通，本轮收口，不新增模型实验。用户随后明确授权合并PR99和PR100；PR100已合并，PR99的组合检查见主线交接和该PR最终状态。没有额外完整论文、全场景或Baseline付费测试。计数/原文位置的机器验证、必要原文片段复用及完整论文交付质量作为后续非阻塞工作保留；不改写失败记录或宣称稳定净降本。代码合并不等于生产部署。
- 回退与风险：去掉script-config/learning-store走原生路径，或切回a590080并用其旧认证库。当前代码使用本轮实际再认证库；不要把旧代码锁改SHA当兼容。生产/公共认证库/认证数据/全局配置未动；真实沙箱仅本地macOS验收。其他历史检索/报告/Negative结果由前轮实验文档保留，不因本轮局限否定已观察的局部收益。
