# 科研 PPT 当前交接

## 2026-11-04：PR131成员学习与独立认证修复

- 用户已授权修复并在最新CI通过后合并PR131，不部署。基线`7ced3b0`，修复分支`codex/pr131-member-fixes-20261104`，推送目标仍是PR131的`feature/research-ppt-agent`；提交/合并SHA由该PR与Git历史定位。
- 页面学习改用既有账户预算绑定，原代理增加受限的独立Capability验证入口。普通在线run权限、原认证、账户隔离及未知费用保留；失败/撤回仍拒绝。
- 本地全量2300 Python/1607 Node通过（261/23跳过），smoke/Motif/RSI/效率检查通过。Linux真实命令代理→独立验证→Store发布→reload→后继执行通过，相关2项0跳过。均为明确诊断，无真实模型请求或新效果结论。
- PPT75/Paper77兼容导出保持原Graph IR、来源及MCP schema，旧目录保留。默认库改动未部署；旧私有原生库仍依源码锁回退和重新认证。
- 问题、修复与证据见[追加记录](../experiments/ppt-public-rsi-20261104.md)。接手核对PR131修复head及合并状态；正式发布另走统一service流程，不能根据本轮合并自动重启服务。

## 2026-11-04 公共RSI接入，PR131草稿完善

- 目标与范围。按用户要求将PR131转为草稿，整合main `931d1bc`和远端`2358245`的Windows修复，新增公共RSI与PPT原生学习/交付桥接。代码在独立`codex/ppt-managed-learning-20261104`副本整理，交付分支仍为`feature/research-ppt-agent`。
- 已完成。`ppt_capability_learning.py`将合格单路轨迹和原生认证程序登记到公共材料池；`capability_adapter.py`实现公共发现、冻结独立验收和发布；`artifact_capability_runtime.ts`复用原Artifact执行与权限守卫；`ppt_capability_online.ts`通过原`create_ppt_page`消费公共发布根。制作/学习/认证/评审继续单列。
- 构造控制。宿主`GENELOOP_PPT_CAPABILITY_PLAN`显式启用公共构造，按原生库代际和冻结计划去重，后续普通聊天不会逐次重提案。成员预算使用既有账户前缀和Session绑定，沿原累计账本；默认自动采集和材料登记继续执行。公共层未配置时保留原生页面复用。
- 已验证。Windows定向23通过/6跳过；首轮独立Linux全量Python2352通过/208跳过、Node1603通过/9跳过、0失败。纯参数证据接线随后通过真实页面工具调用及PPTX/PDF/PNG交付。整合最新main的最终全量及GitHub CI继续核对，结果以PR最新检查为准。
- 真实验收。真实模型1请求生成单步骤公共根，估费USD0.00091104。复用该候选完成Store发布、不同输入后继执行，两次源页检查均可见文字一致、像素MAE0。另一个新任务通过`create_ppt_page`调用已发布根并由`finalize_ppt`导出，机械通过；新增模型请求0，成品已取回本机`.local/deliverables/ppt-public-rsi-20261104/`。
- 失败与边界。首次验收凭证未加载导致零请求失败；首次付费候选验证因验收脚本选用缺少CairoSVG的解释器失败。沿正式入口指定解释器复用原候选后通过，属于显式工程恢复。实际工具试用又捕获纯参数调用缺少依赖证据，已增加当前批准参数的独立证据及回归，文件版本检查继续执行。原稿科研措辞仍需审阅，未声称公共封装额外降本。
- 配置与数据。最终PPT74/Paper76兼容库保留原Graph IR和来源，绑定目录schema去重及Windows交付路径修复；先前发布目录保留。当前公共页面根与私有素材、认证输入和原始日志均留私有目录。实验ID `ppt-public-rsi-20261104`，公开记录见同名报告。旧24题继续使用原冻结代码。
- 跨平台收尾。最新Windows CI捕获交付依赖的反斜杠路径使官方报告误入输入集，已在逻辑路径边界统一为`/`。本机借用既有同版本依赖执行公共Runtime/交付定向，15通过/1跳过。此前最终Linux整合全量Python2352通过/208跳过、Node1616通过/9跳过；目录去重后交叉Python20通过及完整Node1617通过/9跳过，smoke/motif通过。当前CI以修复后最新提交为准。
- 接手下一步。核对PR131最新双平台CI；审核公共计划中的独立来源和质量范围后启用；公开共享另走隐私准入。正式服务保持既有版本，回退可使用先前发布库与配置，原材料和累计账本保留。

## 2026-11-04 PR131已提交，24项正常材料任务继续执行

- 目标与范围。限制无依据审查、固定活动脚本化、正常页面学习与后继成品使用已做出真实验证。原实验分支为`codex/ppt-rsi-transfer-20261102`；本次提交在独立`codex/ppt-managed-learning-20261104`副本整合最新main `5d73a4b`，代码提交`1c8a6af`已推送到用户交付分支`feature/research-ppt-agent`，已创建[PR131](https://github.com/jingyio/GeneLoop/pull/131)，等待审核。正式服务保持既有版本。
- 已完成。共同运行规则、真实角色字体校准、Generate统一交付和预览守卫、静态边界注释修复、实际成品快照及源页证据。正常worker自动提炼页面程序，沿Artifact认证后在未来任务冻结加载。新增局部schema引用兼容、认证后实际在线加载检查、`expected_page_sha256`参数修订、执行协议变化重新认证、跨失败导出注释链的成品来源统计。
- 已验证。服务器`npm test` Python1807通过/202跳过、Node1491通过/4跳过；最后仅追加TS来源修复，全部Node1492通过/4跳过，smoke/motif通过。Windows定向Python16/1，本机Node依赖不足，完整结论依据Linux。实际Office注释修复前后PNG相同、MAE0。225项代码锁本机/服务器一致，457份私有证据已下载并逐SHA验证。
- 实验与配置。ID为`ppt-managed-learning-20261104`，结果在同名`-results.md`。服务器候选仍为开发父目录下`.local/ppt-managed-learning-20261104-c5`，PPT70/Paper72保留原Graph载荷。Flash/off、393216容量、沿旧账本不限设置。两项正常训练完成，G03/G04四次后继执行完成，24项普通材料任务已启动。学习与Judge单列。
- 效果与边界。G03 B66/O61请求、费用低1.67%，标题/事实质量仍有问题，完整程序成品复用0。G04 B53/O47、费用低18.92%，组件调用并进入最终成品1次，非盲辅助查看可读，科学/视觉盲评待完成。G04两组有接口阶段差异，不能把全部差额归于RSI。初次提案由worker自动完成，源码保持原样；后续开发维护重认证复用该提案，额外模型调用0。
- 证据修订。C3/C4入口失败、schema回退后的130请求取消任务、每次认证拒绝与旧源码均保留。G04来源漏记由失败导出已完成的注释修复引起，已在`evaluation/lineage-reconciliation/`单独副本重算，原任务事件不改。学习使用gate通过，候选仍为probation，未伪造active配对。批量前6个独立任务的最终源页版本进入材料池，29个来源版本包含草稿，统计须区分。
- 配置与数据。私有运行、论文、脚本和证据留`.local/`。页面学习默认沿真实Web的`SSS_WEB_POLICY`及委托凭证，可用`GENELOOP_PPT_COMPONENT_LEARNING_POLICY`指定测试策略。账户预算前缀与`turn-<task-id>`单独记编译费用，不修改累计账本。
- 私有入口。运行配置与队列在候选目录`.local/evaluations/ppt-managed-learning-20261104/`，`normal-batch/batch-state.json`为进度，客户端依已有runner状态恢复，不能盲目重提付费任务。`bash <开发父目录>/.local/run-managed-c5.sh python3 .local/batch-status.py`只读查询；24题使用同一隔离Web与旧账本。Web由官方`--resume`恢复，同一Home/output保留。正式服务保持既有版本。
- 权限与支出。真实测试授权持续有效，批量前含全部诊断738请求/$1.257498594代理估费，学习1请求/$0.008429100已单列。批量继续另计，实付与人工分钟未知。本轮代码已提交、推送并创建PR，正式服务保持既有版本，前序实验工作区及未提交工作保留。成品在本机`.local/deliverables/ppt-managed-learning-20261104/`。
- 下一步。观察24题交付与真实在线来源计数，确认合格终态进入池；结束后做辅助质量评审与失败归类，再以冻结最终代码做独立合格费用验证。程序当前以自包含结论页为主，长标题、公式与复杂图件仍需验收，干净安装待补。回退使用对应源码/库及已保留快照，保持任务和账本。
- PR整理。提交仅新增PPT71/Paper73两个兼容库，直接沿main的PPT44/Paper47保留原IR和来源，223项代码锁一致。私有轨迹、论文、产物、实验客户端、中间库和分轮兼容脚本保留在实验目录。必要回归保留。独立Linux整合回归Python2345通过/207跳过、Node1599通过/8跳过，smoke和motif:check通过，新增模型请求0。PPT70/Paper72实验副本与正在进行的队列不改。
- 团队接线。整理时main为`5d73a4b`，开放PR129为`a597083`、PR130为`23c1b50`，两项与当时提交的`git merge-tree`均自动合并通过。`codex/rsi-privacy`的`83c1185`与当时提交有3处代码/测试冲突，后续合并须同时保留`privacy_projection=True`、新增代码锁及单路准入测试。后续已整合main `931d1bc`并补公共PPT适配，见本文件顶部和接口文档。
- 远端检查。GitHub已确认PR可合并。首个Linux检查在`npm run setup`下载Python依赖时发生`BrokenPipeError`，尚未执行测试；其他检查仍运行中。GitHub CI结果须在审核前继续核对，独立Linux全量回归结果单列。代码通过GitHub官方Git Database API快进推送，远端tree与commit SHA均与本地一致。
- 最新队列观察。N01已完成，N02执行中且有4次接口参数/封装拒绝，完整恢复与质量后续核对。批量材料与成本不混入前述两题对照。

## 2026-11-04：交付修复与小规模验收收尾

- 目标与范围。本机分支`codex/ppt-rsi-transfer-20261102`、基线`0bd1e3b`加此前未提交改动。实现字体/对比预检、默认设计指导、自动输出目录与结构常量绑定、共同finalize_ppt、版本缓存、客观缺陷停滞提示、成品来源统计及账户内字体经验接线。主要文件为`ppt_design_preflight.py`、`ppt_delivery_pipeline.ts`、`ppt_delivery_runner.py`、`ppt_delivery_learning.py`及现有component/program学习模块。当前PPT60/Paper62保留原Graph载荷。
- 真实诊断已验证缺字失败→修复后Office导出→生成1条字体规则→后继调用实际加载应用，禁止回退仍拒绝，0模型请求。此处是构造生命周期和实际渲染诊断。真实程序生成2次，经历对比度拒绝和开发者断行参数校准，尚不称全自主成功。
- 已验证。最终C12服务器Python1783/Node1484通过、202/4跳过、0失败，定向9项及smoke/motif通过；1392份本机/服务器文件SHA一致，10份Graph载荷保留。C10重导出误将官方输出报告作输入的负例已复现修复，同版本调用真实复用。C11脚本目录变量漏路由也已补回归。独立测试Web均核验终态、pending0及PID/start ticks后关闭。
- 实验结论。两题四次生成及一次重复配对，共六份PPTX/PDF/全部页PNG。C11 B210/$0.379821324，O330/$0.477319380，高25.67%；C12 B162/$0.287856384，O128/$0.210844848，低26.75%，但两侧Graph旁路均2、O没有调用页面程序，不能归因RSI。三页稿有图示/字形与概括问题，非盲Codex评审后仍未通过严格等质净降本。真实新字体规则/晋级0。详见[完整记录](../experiments/ppt-component-delivery-repair-20261104-results.md)。
- 配置与数据。真实Flash/off、容量393216、费用和次数不限，沿用旧账本。最终C12为同开发父目录下独立私有候选。成品在本机`.local/deliverables/ppt-component-delivery-repair-20261104/`的`c11/`与`final/`；原始事件、回执、配置、生成响应及日志在同ID的`.local/evaluations/.../final-evidence-c12/`。密钥仍由服务器私有环境提供。
- 权限与预算。未提交、推送或部署，用户原未提交工作与旧12题保留。当前1386请求/$2.350242990代理估费，其中页面程序生成2请求/$0.009462300单列。账单、开发维护和人工修订成本未知。没有人工盲评或人工修稿计时。
- 未完与接手。停止扩大模型测试。优先解决已选择组件到最终交付的宿主管理路径和无明确缺陷的微调循环，再核验正常真实任务产生的新规则及后继消费；字体经验之外的模型程序生成仍为显式离线入口。结果缓存只在相同依赖时复用，复杂科学/视觉错误需要评审。未经过下一阶段验收前不将本候选宣传为稳定降本或生产部署。
- 回退与风险。正式服务未切换；独立候选可通过原登记版本及配套源码恢复，原库不改。候选选取与参数校准含开发者介入，普通组也使用Graph与共同底座。任意Python导入和自由Bash仍无法仅靠命令识别全面约束。实际Pillow13.0.0与清单12.3.0存在差异，Python包级缓存失效及干净安装复现待补齐。

## 2026-11-04：可靠交付修复设计（仅审计与方案）

- 根据用户对诊断循环、组件认证和默认设计的追问，复核本地候选代码及既有逐步审计，形成[本轮修复方案](../experiments/ppt-component-delivery-repair-20261104-plan.md)。本次仅新增方案及交接链接，无运行代码修改、无新模型请求、无提交或部署。
- 新发现：生成候选的提示仍要求SVG字节完全相同，与已改为文字/画布/像素等价的认证器不一致；现有prompt已提醒字体和字框误报，仍缺少受管理交付路径的收敛机制。现有Office入口服务上传原件，不能称为已接通自产组件的完整交付链。
- 下一步顺序：默认profile及实际字体/配色约束→两组共用官方导出与结构化检查→版本缓存和停滞处理→最终交付来源链→两个独立任务配对。学习与Judge费用单列，尝试/弃用/重做计原组。旧测试和正式服务保持原状，实施与效果尚未验证。

## 2026-11-04：历史页面参数化、原生调用与真实负例（未提交/部署）

- 目标与范围。保留主线与旧实验，从合格历史 SVG 提炼参数化 Python 页面程序，复用 Artifact 认证和沙箱，验证新任务是否实际使用。分支 `codex/ppt-rsi-transfer-20261102`，基线 `0bd1e3b` 加此前未提交改动，当前未提交、推送或部署。
- 已完成。新增 `ppt_component_learning.py`、schema、源渲染、缓存、等价检查及 `ppt_component_tool.ts`，原生 `create_ppt_page` 与旧 Bash 共用 `artifact_motif_transport.ts` 和现有 broker。普通组实际 25 工具，无组件入口/目录，优化组 26 工具。当前公共兼容候选 PPT55/Paper57，Graph 仍为原读取边，没有新增图类型。
- 已验证。服务器最终 `npm test` 为 Python1774/Node1476通过，202/4跳过，0失败，smoke/motif通过。定向12项通过，真实冷/暖/变更输入缓存及 JSON 键顺序复验通过。本机160项源码锁与服务器一致，原冻结12题189项源码SHA不变。最终113份证据已同步逐SHA核验。
- 实验结论。历史10组合格轨迹中6组有当前原盲评PPTX，形成79个执行来源及已评审页文字绑定的SVG候选，未批量生成或认证。单一历史结论页的模型程序通过源页面等价与不同材料执行认证，后继真实任务调用1次，Graph旁路2次。第二次B130请求/$0.223978314，O185/$0.293335926，费用高30.97%，O还把两条边界写成三条，严格题面验收失败，不能称同质降本。第一次目录提示O完全未调用程序，失败及94请求编译绕路均保留。学习96请求/$0.095601636单列。详见[页面组件实验](../experiments/ppt-component-learning-20261103.md)。
- 配置与资料。私有实验 `ppt-component-learning-20261103`，真实Flash/off，容量393216，额度不限且账本沿用。服务器最终副本 `ppt-component-entry-20261103`，本机证据 `.local/evaluations/ppt-component-learning-20261103/server-evidence/`，成品 `.local/deliverables/ppt-component-learning-20261103/final/`。密钥仍由原私有环境提供，不进入Git。
- 未完成。组件源PNG不认证实际Office效果，缓存仅减少相同页面的源渲染，真实任务没有暖命中收益。当前仍由完整Skill执行导出与看图，反复字体/位置检查抵消了局部复用。没有部署或晋级为默认降本能力，File完整分页循环尚未迁入。
- 逐步补审修订。`program_reuses=1` 表示成功试执行。模型看过组件PNG后，因白字浅底和缺字而明确改为自行设计，最终交付来自手写路径。普通组也修复字体和重叠，首次Office看图后工具操作B34/O101，优化组在坐标与字体诊断中多次修正先前解释。已补记真实颜色参数、原始预览与事件SHA，成品复用范围须按此修订，不把试调用统计当作最终交付复用。补审0新增模型请求。
- 接手下一步。先完成双方共享、实际渲染的可靠Office导出入口，再独立认证组件在该入口下的布局约束，最后用少量新任务验证增量收益。先修交付链，不继续无目标地批量生成程序。原读取回执修复继续有效，早期记录仅代表各自当时版本。
- 权限与回退。仅在授权隔离测试环境运行，原始论文、轨迹、全部失败和费用留私有目录，正式服务未切换。正式发布继续统一service入口，回退须使用成套源码、库与注册表，不能清账本或覆盖旧库。

## 2026-11-03：长文本MCP回执修复（已验证，未提交/部署）

- 目标与范围：在原候选上修复读取Motif因DSH长输出附注而回退的问题；保留完整原文和旧实验，不扩展新程序学习或重跑12题。分支`codex/ppt-rsi-transfer-20261102`，基线`0bd1e3b`，工作区仍含此前接线改动。
- 已完成：`converted_source.py:source_read_response`将完整展示与紧凑MCP`structuredContent`版本回执分开；`server.py`显式返回`CallToolResult`，不改上游Harness或共享观察器。新增协议/守卫回归及`reexport-ppt-receipt-compat.py`；默认候选PPT48/Paper50，旧五份学习载荷逐字节保持，不称新Motif。
- 已验证：服务器20Python/11Node定向通过；最终`npm test`1765Python/1468Node通过（202/4跳过、0失败），smoke/motif通过。首轮3项环境失败与17通过/1跳过复验日志均保留。真实Flash/off读取任务`3f27986342ae4fd99c59f3e079fa000a`completed，2次verified skip，read边核验成功，0工具错误/0未验证回退；未生成新PPT，不推断整体降费。
- 费用与证据：独立诊断34真实请求/代理估费$0.05755053（含附件预处理，未知0），不计旧B/O，也不伪称学习费。RSI学习/生成/认证及Judge继续单列，用户任务内重试恢复仍计各自B/O。原冻结实验189项SHA保持，本机/服务器15项候选文件一致；23份证据已下载逐SHA核验，位于本机`.local/evaluations/ppt-receipt-fix-20261103/server-evidence/`。详见[修复报告](../debug/ppt-read-receipt-fix-20261103.md)。
- 未完成与下一步：当前Code入口仍未从本批heredoc/组合Bash学到通用程序；同伴File循环、视频主动参数化、Paper新function构造入口未接PPT。先从合格稿源码生成参数化候选，再独立认证/后继任务验证；不能把已有目录注入或兼容导出说成该能力已生效。
- 权限与回退：未提交、推送或正式部署；独立诊断服务已关闭，未动正式网站/原实验。正式服务仅可走统一service入口。保留v47及配套源码，回退必须成套恢复注册表与源码锁，不删私有库、失败证据或账本。

## 2026-11-03：质量证据、旧稿继承与程序学习（未提交/部署）

- 费用/结构审计新增：已实际fetch最新main`2b3d005`（含PR127），只读比较File/视频/递归机制，未合并或部署。本批总verified skip为12，其中round-0003为4，种子为8；新类型0/Code0。28原生任务收到学习通知，Code可检查13条；同采集器审计24个completed运行候选0，主要接口不接纳heredoc/组合Bash。30份全文读取投影28份因附加spill说明不能严格解析JSON，真实read边发生unverified并回退，不能放松守卫冒充旁路。原生成O少约13万输出、但多约7180万命中输入，对已知估费分别-0.156/+0.431美元；学习请求0，RSI/评审仍单列。优先修有界回执，再从合格源码提炼参数化页面程序/可靠局部交付。详见[审计与候选](../experiments/ppt-rsi-cost-trace-audit-20261103.md)；0新模型调用，无新候选认证或启用，未提交/推送/部署。
- 双评已完成：实验`ppt-single-24judge-20261103-v2`，Codex24组逐页/失败复核 + 真实Flash/off24组补评，22份可评分现有稿、2组无最终稿失败审计；T11/O只有首轮，计划轮次完成仍21/24。Codex通过10组（B/O各5），模型候选17通过/4未过/3待核验，科学图表漏错不能被模型高分洗掉。含恢复B2458请求/已知$5.07919849，O2413/$5.38726376，未知费3/15笔；O已知费高6.07%，不支持整体同质降本。新Judge25请求/$0.43165699+1笔未知（含一次空值传输恢复），旧Judge13/$0.22840854，全部单列；Codex平台费/人工修订未知。20项服务器评测诊断通过，181份补评证据及442份输入已取回逐SHA核验；评审不写回学习库，冻结成品/原失败/账本保留。详见[双评报告](../experiments/ppt-single-24judge-20261103-v2.md)，私有`double-review-summary.json`与`DOUBLE-REVIEW-COMPLETE.json`绑定记录。未提交、推送或部署。
- 最新终态快照：新版生成/Judge队列均finished，21/24组运行完全部计划轮次、8份完整评分；T02/O原中断及T11/B SSE失败保留，T11双方修订未运行。B2453请求/已知$5.07375584，O2384/$5.37468582，另B1笔未知费用；已知费用高5.93%，不能称整体同质降本。T07双侧Judge8.8/8.7且单次估费低42%，为有限正例。round-0003已自动认证/后续消费/机械费用晋级，T08费用退化后自动disabled（T04/T06/T07/T08各1次skip）；科研质量晋级false、Code0。当前无生成活跃任务，服务仍在线，源码189SHA一致，历史库隔离；接手先核对既有质量/未知费用和归因，不自动重跑。见[终态记录](../experiments/ppt-single-12tasks-20261103.md)。未提交/推送/部署。
- 最新进度复核：10/24任务组运行结束，4份完整评分；T06普通组结束，优化组因中文Regular字体确认等待约3小时。已按原自主设计授权由AI操作员答复“字号/颜色区分，不使用粗体”，保留干预/等待记录，原Task请求14→37、pending问题0，确认继续执行；不称完全无人干预。round-0003在T04/T06各1次verified skip，仍probation，Code0。四项已运行结束配对B729/$1.55897431、O825/$1.78218601，整体估费高14.32%；T04单题低20.43%但质量/交付证据未齐，不能称同质降本。源码/库189项SHA未变，历史库未混入，未提交/推送/部署。详见[本轮最新段落](../experiments/ppt-single-12tasks-20261103.md)。
- 用户新增授权已完成：旧单路另作隔离历史学习，实验`ppt-historical-learning-20261103`。盘点20条、6条Baseline历史机械证据可用，T01/T03训练、T04留出，经原编译器认证2个既有读取Motif（新类型0）；Code因20条都缺原pre/post边界，0准入，不伪造receipt。新增模型0/费用$0，复用采集947请求/$2.2681949单列，CPU/人工未知。私有历史库不启用、不注册，不混入当前12题；189项当前源码SHA及候选证据隔离核验通过，277份原证据/副本已取回本机逐SHA核验。记录见[历史学习](../experiments/ppt-historical-learning-20261103.md)。当前新版已到T04，自身round-0003已加载并出现1次verified skip，尚未形成完整质量/费用或晋级结果，不能归因于历史库。未提交/推送/部署。
- 当前指示与状态：新版12题已按用户要求恢复，原暂停指示不再生效。F10a最终全量1744Python/1467Node通过（202/4跳过、0失败），smoke/motif通过；Paper50/PPT47仅兼容导出，189项源码/库SHA核验。原5组不重跑，T02/O由官方冷恢复标失败，82请求/$0.125106546及旧失败保留，不再付费重试。原run-id/账号/Home/账本沿用；T03普通/优化组均已产生真实Flash/off请求，生成/评分/交互/汇总四角色持久续跑。旧两代候选退役；后续round-0003已有读取旁路，Code消费与净收益仍待验证。24份证据已取回本机`.local/evaluations/ppt-single-12tasks-20261103/recovery/server-F10-resume/`逐SHA核验；首次preset启动失败及旧代码锁拒绝均保留。详见[本轮记录](../experiments/ppt-single-12tasks-20261103.md)。当前未提交、推送或正式部署。
- 基线/范围：main `0bd1e3b`；独立 `codex/ppt-rsi-transfer-20261102`。原 12 题实验仍固定 `09b81b2` / v37，未修改代码/库、重启或覆盖旧结果。
- 已实现：共享质量记录接入原学习和晋级；PPTX/PDF 优先继承；真实 Bash 产物证据→既有 Artifact 编译/不同输入沙箱认证→未来任务目录/执行→两项独立配对费用晋级/负反馈回退。同一主对话的续改/子会话不算独立学习决定。模型仍决定内容及适用性，程序复用不算 verified skip。
- 已验证：服务器最终完整 `npm test` 1705 Python / 1465 Node 通过，分别202/4跳过、0失败；smoke、motif:check 通过。成员别名下的真实沙箱认证/执行已验证。独立审阅因额度未完成。R01 两组均继承自己的旧 PPTX，首轮完整交付，优化组加图改页反复重做后通过原 API 取消；功能回归不等于修订可靠性或收益通过。详见[记录](../experiments/ppt-rsi-reuse-integration-20261102.md)。
- 私有数据：源码检出内 `.local/test-logs/ppt-rsi-transfer-20261102/`；账号库沿原 output/learning/ppt-<owner-scope>，模型凭证不传学习 worker，不清账本。不把库共享给其他账号。
- 接手：先完成原冻结12题的任务级费用/质量审计，不能用共享总账冒充生成费用；根据明确修订循环负例限制局部恢复范围；用户审阅后再决定提交与发布。先不提交、推送或部署。
- 回退：基线及对应旧 registry/证书；原五项读取学习产物保留，不删除用户库或原实验。
- 实验结论：R01 两轮普通组412请求/$0.73794473，优化组582请求/$1.06781775，代理估费增44.70%且优化组修订未完成，不支持新机制降费。候选0、没有新程序真实复用/晋级；已有Graph首轮skip1不能归因新增程序。科学/视觉/人审和人工分钟未知。普通组非目标文字/slide XML保留，PNG有小量差异，不能声称像素严格保持。
- 配置/交付：最终 registry Paper45/PPT42；真实 R01 冻结 F4/PPT40，未重跑最终代码；原五项学习产物逐字节保持。86份原生不可变成品与审计证据已取回本机 `.local/evaluations/ppt-rsi-reuse-integration-20261102/` 并逐SHA核验；原12题仍运行，无代码变更。费用/请求不限，原账本沿用，实际账单未知。
- 证据收尾：本机/服务器最终候选87项公开文件SHA一致；35份F0–F6诊断日志及一致性证据已取回 `.local/test-logs/ppt-rsi-transfer-20261102/server-final-evidence-f6/`，归档SHA核验通过。源码回归结束后只修改文档和私有只读审计，不重复付费试验。
- 用户随后授权本轮也并行跑同一12题：新实验 `ppt-rsi-12tasks-20261103` 已在独立源码/输出/账号目录启动，T01 B/O已实际发送；12题、24份最终稿、28个生成运行，Flash/off、PPT42，原账本不清零但按任务ID隔离新旧生成/Judge费用。原 `09b81b2/v37` 测试不重启、不换库；计划与启动负例见[新记录](../experiments/ppt-rsi-12tasks-20261103.md)。未提交/推送/部署；新结果仍待完成与审计。
- 最新范围：用户要求只暂停新版，先补齐单路准入再重启。新版暂停前486已结算生成/Judge请求/$1.02033267，旧测试未暂停。真实PPT完成边界自动冻结单路receipt，成员认证已接线；Baseline供Graph/Code，Execute原生模型程序供Code，单路不伪装配对；认证/试用不依赖先证明省费。最终Paper48/PPT45，59Python定向通过，最终全量1725Python/1467Node通过（202/4跳过、0失败），smoke/motif通过。新实验 `ppt-single-12tasks-20261103` 已重新启动，T01/B执行中；先3项独立单路训练，再观察后续9项独立任务，见[新方案](../experiments/ppt-single-12tasks-20261103.md)。真实新候选/收益仍待观察；未提交/推送/部署。
- 最新实时复核：旧生成24/24组结束，Judge14份/11份完整分数；新版5/24组结束，T02/O的running是Web进程退出后的残留，HTTP/PID核验离线，首次判断已更正。单路自动eligible1→2→probation真实触发，产生两代原有读取结构候选，但支持任务task-state.json被后续刷新改变，整文件锁导致ppt_learning_evidence_changed，私有候选未启用，新程序0复用/认证。新版两项完整对照均更贵。先修复稳定证据锁与可变状态的边界、查明/恢复隔离Web退出及计量，不得放松守卫或重签旧证书覆盖负例；详见同一实验记录的实时复核段。当前未修改冻结执行代码、未提交/推送/部署。

- 最新用户指示：先暂停新版恢复，先交付旧12题报告。F10稳定事实绑定与独立Web恢复补丁已在候选副本通过74Python/5Node定向诊断；全量回归按用户要求停止，未记为通过。原执行副本源码未应用F10，Web未重启、剩余任务未重发；F9原147源码/私有状态/账本快照已保留，公开源码归档已下载校验。旧12题只读审计：生成6046请求/$13.39555586（B3275/$7.29896891、O2771/$6.09658695），Judge另17请求/$0.32384615，14份评审结果/11份完整评分；批次费用下降16.47%，不支持同质稳定净收益，新结构认证/晋级0。见[旧测试汇报分析](../experiments/ppt-real-12tasks-20261102-analysis.md)。当前未提交/推送/部署；新版恢复须等用户后续指示。
- 导出复核新增负例：旧T12/O第二轮答复明确因未继承旧PPTX而拒绝修订，工作区与第二轮交付均无PPTX；Runtime completed不是该任务成功。桌面已取回T04/T08/T12六份原稿并逐SHA/ZIP/页数核验，T12/O为首轮6页，显式标记REVISION_FAILED；B为第二轮7页，不能当等价成功对照。T08/O有真实presented PPTX但缺完整登记PNG套件。原报告PDF/Markdown已追加事实、费用不改，新版仍暂停；仅导出，无新模型调用、修稿或提交。

## 2026-10-21：固定风格程序复用成本实验

- 本轮：`codex/motif-cost-learning-20261021`，实现`76ca3e2`；`artifact_motif_*`与离线学习／认证脚本，默认关闭。全PPT由GeneLoop制作、修改；测试者只提交题目、读取和复制原始成品。
- 最新用户范围：不以PPT内容正确性作为验收项，比较同一固定风格和真实交付成本；双方保持完整ppt-master Default、三页、可编辑形状与PPTX/PDF/PNG。不要把免除双方内容审阅的共同改动归因于Motif。
- 最新匹配：90→106请求、10,538,864→9,876,883总Token、USD0.14433796→0.11510303，认证程序实际执行1次；时间292.4→335.5秒。请求仍增加，不能宣称所有环节都复用或总会省费。此前v12费用上升2.7%、未触发整程序认证，保留反例。
- 库范围：从历史正常GeneLoop三页渲染程序及独立新文章认证，当前只覆盖固定三页JSON／风格；不是完整ppt-master导出流程的连续执行库。来源、版本守卫、原件只读和语义回退保留；候选IR不直接替换正式旧库。
- 验证：Linux完整Python1718／Node1359通过、各4skip，smoke/motif通过；当前例实际生成3页、126个可编辑形状、备注每页超过40汉字，真实PNG返回模型。未作内容质量结论。
- 复现／交付：见[实验记录](../experiments/three-scene-motif-cost-learning-20261021.md)、[接口](../interfaces.md#artifact-motif-独立实验接口2026-10-21)和忽略的`.local/deliverables/geneloop-motif-cost-learning-20261021/`；原任务、所有失败与费用留在私有部署目录的同名实验根。
- 正式服务仍7e167ed，未替换库／未重启。后续先扩大不同页数和模板的覆盖，再决定正式接线；回退实验只需不设置私有Artifact配置，不能删除历史文件。

## 2026-10-20：与 File 及 PR92 共同集成（PR93，待审）

- `codex/integrate-file-ppt-rsi` / 源码 `6603d7d` 已推送 [PR93](https://github.com/jingyio/GeneLoop/pull/93)，保留 PR88 原提交祖先关系，未合并/部署。
- 保留 PR92 附件阅读索引、主线私有上下文/进度/取消，叠加 PPT 后台学习与否决机制；当前集成库为 `ppt-master-v12` / `paper-web-v17`，从 main 已发布 v11/v16 重新核验相同序列化 IR 与证据，新学习边界进入源码锁。旧发布目录不改。
- PR92 之后 71 Python/112 Node 定向通过，包含独立认证、未来任务选库、晋级、重启、负反馈与完整性守卫；最终 Linux 全量1415 Python/1073 Node通过，各3跳过；CI 以[实验记录](../debug/file-ppt-integration-20261019.md)为准。未重新购买完整 PPT 制作评测，不扩展原质量/收益主张。
- 上线仍需原账户对照配置、可用 Python 和持久学习目录；原失败/费用/私有候选保留，失配不重签，回普通 Harness 后按新正常轨迹学习。合入后只通过统一 service 入口另行发布与真实账号验收。


## 2026-10-19：用户轨迹自动学习接线（已推送，未部署）

- 目标与范围：以 main `a1c0fa2` 开发，提交前同步至 `d422d77`（执行代码与已测 `b939cd5` 相同，仅新文档）；开发分支 `codex/ppt-user-learning-20261019`，交付分支 `feature/research-ppt-agent`。接通 PPT 原任务→后台离线编译→独立认证→后续试用→机械/费用晋级及停用。当前仍使用 main 官方 ppt-master 6.6.0 风格，不恢复旧 V17 renderer。
- 已完成：`harless_ppt_learning.ts`、`learn-web-ppt-tasks.py` 接原 Web 生命周期与 compiler；私有账户/scope隔离、按兼容配置取2训练/1留出、2后续对照、完整含失败重试费用、普通踩立即停用、反馈代际防旧worker误恢复、证据/代码守卫及重启继承。无默认验收表，用户不需额外操作；可选内部 review API 不影响普通使用。
- 认证范围：仅 pin→convert、convert→read 两条现有受限边，编译不调用模型、不重新跑任务。默认只晋级结构/机械/代理费用，科学质量和人工分钟未知；尚无真实用户新候选晋级或同质降本结论，不称任意新工具生成或无限代际学习。
- 兼容：独立 `ppt-master-v9` / `paper-web-v14` 保持旧库、schema与原证据，校验原序列化 IR 后更新新接线代码锁；旧目录不改。
- 验证与限制：服务器原隔离副本 `DeepSeekHarness-ppt-learning-20261019` 与提交审计副本 `DeepSeekHarness-ppt-learning-20261019-submission-audit` 均在用户原指定 `/mnt/sevenT/junjiex/` 下，复用旧 Python/Node 环境；新诊断 26 Python / 2 Node、release 14 项及工具结果兼容7项通过。最新main最终 `npm test` Python924通过/199跳过、Node855通过/3跳过；原开发轮900/855通过，smoke/motif检查通过，详见[接线记录](../experiments/ppt-user-learning-20261019.md)。合成轨迹只证接线，不是新真实使用收益。
- 私有数据：日志在 `.local/test-logs/ppt-user-learning-20261019/`；密钥仍留旧项目 `.local/credentials/deepseek.env`，环境激活脚本不自动加载。当前目录没有复制密钥，不修改旧运行目录或旧账本。真实调用使用Flash/Off、不压缩；额度沿用当前不限设置，全部失败尝试记账。
- 真实进展：技能锁差异已解决，上游精确commit `440557b8dc7c7257b69c04a0b014d5c50a78e6cb` 的13,016文件全部符合原锁。首对三页PPT均已交付，Baseline188请求/$0.313435596、Execute203/$0.312394368，实际旁路均0，不支持RSI降本；后台已自动收录一条合格Baseline。账号沙箱准入通过，浏览器完整生成未验收。
- 兼容修复：适配器兼容原生MCP envelope的解码payload与直接Native JsonValue；structuredContent沿用原权威性，执行值/文本矛盾或版本变化仍回退。中间错误比较曾使literature原生旁路回归失败，修复后该SDK/MCP诊断通过；不改单个核心或上游。未发布v9/v14已重建并备份。最终真实读取普通17请求/$0.019312314、优化15/$0.018176058，审计确认2次skip；仅证局部读取结构，不能称完整生成或新用户候选收益。
- 提交与下一步：实现 `d9f520a` 已随历史整合提交 `571a55c` 推送至 `feature/research-ppt-agent`；未创建PR、未部署正式服务，PR由用户准备。旧分支两项提交历史及独有实验报告保留，工作树以main为准。当前隔离真实验证库只有1/3合格Baseline，真实新候选尚未晋级；上线后让正常独立使用继续积累，证据达标自动认证/后续对照晋级，不额外购买验证任务、不人工凑状态。本轮不扩功能或实验矩阵。
- 上线必核对：真实模式、可用Python、当前账号policy的 `comparison_scenes` 包含 `ppt`，注册表指向当前v9/v14；成员输出为独占 `/app/.local/web`。来源任务结算与成品快照保存均自动调度，下一优化任务冻结候选，失败/负评回原库；无需用户填表或开发者手动跑学习脚本。单路无Baseline证据只等待，正式切换使用main的 `npm run service`。
- 权限与回退：开发与真实API测试授权内，累计461请求、逐回执峰值估费$0.711649760；无外部应用写操作。按原注册表退回 v8/v13 时须配套恢复代码；私有候选失败回当前兼容库，证据不删。账单/CPU/人工维护费用未知。成品及最新日志已同步本机私有目录。

## 2026-10-18：新会话首次转换修复

PR #73 已合并/部署 `0c20986`。上线读取探针揭示首次 MCP 转换先于 Bash 时缺少 code 目录；转换器现在初始化本会话子目录并拒绝符号链接。新增两项回归通过；同一证据重编 `ppt-master-v3`，没有新采集、没有改变两条结构和原 PPT 对照。失败探针的 11 请求/$0.03263586 保留，完整结果见同模板实验记录。

## 2026-10-18：PPT 转换结构扩大复用与同模板网页对照

- 新 `ppt-master-v2` 从真实完整制作任务训练并通过独立留出，新增 pin→官方转换、转换回执→核验读取两条闭合边；实际网页验证 2 次跳过（上一版 1 次），未认证三节点链，不接管 Bash/页面制作/科研判断。Paper v8 仅兼容重编，旧库保留。
- 同一 AdaLoRA、官方 presentation_core/academic-research 模板、Pro Off：Baseline 87 请求/$1.17369790/1036.504s；Motif 80/$0.98129175/844.355s。单次估费低 16.39%，不能把 7 次请求差都归因于 2 次跳过。含失败采集共 694 请求/$7.70190830，账单未知、人工/CPU 未计价。
- 全部幻灯片均 GeneLoop 自制，未人工修订；两路六页、备注、PDF/PNG、网页预览和下载 SHA 完整。两版质量均未通过，Motif 排版更差，实际主题字体也未严格遵守指定字体；只称同模板输入，不称同样式成品或同质稳定降本。
- 运行代码冻结 `737c41f`；最终实现/守卫测试 `57e0ce4` CI 两平台 Python/Node、smoke/motif 检查通过（含明确跳过项）。共享 provider-length 原生续做仅诊断覆盖，本次未触发。详见[完整结果及测试](../experiments/ppt-master-structure-style-20261018.md)。
- 发布跟踪 [PR #73](https://github.com/jingyio/GeneLoop/pull/73)；原 PR #72 已合并并部署 `9a25a7d8`，原负向结果不改写。新部署保留数据、累计账本和回滚快照。私有原稿/报告在 `.local/deliverables/ppt-master-structure-style-20261018/`，正式回执与读取探针另存，不混入 PPT 评测费用。
- 后续优先提高共同流程的事实、公式与排版验收，再做重复盲评；本轮 `quality_cost_promoted=false`。扩大复用仅允许有真实轨迹和守卫证据的结构，不能把固定手写流水线算作学习。



## 2026-10-18：ppt-master 默认接入、真实结构训练及网页对照

- 分支 `codex/ppt-master-motif`，基线 `7d74e9e`。`/ppt` 改用完整官方 ppt-master 6.6.0：固定 13,016 文件摘要、只读挂载、新 MCP 入口和模型选定来源的 pin/read；旧制作工具与 host_delivery 不再用于默认 PPT。全部幻灯片由 GeneLoop 制作，测试者未修稿。
- 新 `motif-libraries/ppt-master-v1` 来自 Attention/DoRA 两训练与 LoftQ 独立留出，经原 witnessed-edge 编译器生成一个首页读取衔接；真实 AdaLoRA 网页对照命中 1 次 verified skip。普通批量读取/会话私有临时目录/渲染环境优化不算 Motif 学习。Paper v7 仅用原证据重新编译共享代码兼容锁，0 新模型请求，旧库保留。
- 两路完成六页 PPTX/PDF/PNG、备注及可编辑对象；网页上传/双路发送/预览/下载 SHA/刷新保留通过。Baseline 74 请求/$0.68057381/546.154s；Motif 86/$0.73033102/617.852s。Motif 费用高 7.31%，整体成本收益未成立，且两版都有公式/表格/来源缺陷，`quality_cost_promoted=false`。
- Linux全量 Python 1046通过2跳过、Node817通过3跳过，smoke/motif:check通过；Windows定向28通过1跳过，全量受符号链接/环境限制不能称通过。完整失败、费用、配置和质量证据见[实验记录](../experiments/ppt-master-motif-20261018.md)。含被拒绝候选，共713请求，代理估费$5.74779583，账单/人工/CPU未计价，原累计账本未清零。
- 私有原稿、下载核验、评测报告位于 `.local/deliverables/ppt-master-motif-20261018/`；服务器隔离实验的 `evaluation/private-evidence/` 保存原事件和有效配置。公开只存匿名摘要与认证。权限沿用真实API不限请求/费用/额外输出的测试授权。
- 未完成：独立人类盲评、重复同质成本验证。接手优先处理普通流程的事实与渲染恢复，不将新库描述成全流程或科学判断学习。回退必须把旧代码、旧场景注册表、旧证书配套恢复；旧技能/库未删除。
- 合并与正式切换状态将在完成发布后追加；当前这段不声称已上线。


## 2026-10-16 网页组合交付、局部恢复与新读取库

- 当前分支 `codex/ppt-workflow-learning` 已保留 main 的统计来源检查/输入标签修复。原 CLI 完整 `research-design` Skill 自动追加；网页两侧默认 `host_delivery`，渲染→检查→验证→交付由普通脚本组合，失败保存私有草稿并让原模型只修指定页。最新句柄反馈、同任务预算、取消/来源/权限/schema/实现锁保持，CLI 旧次数诊断保留。
- 新库 `motif-libraries/ppt-web-v2-r4/` 来自真实独立 RAG/QLoRA 训练与 DoRA 留出，现有编译器产出两条只读 pin/read 边，30 页数×21 完整实际 schema；不是手写 DAG、不是全稿设计或修复写入的学习。原库图和证书未改。科研稿有错误，显式未通过质量费用晋级。
- [实验及 workflow](../experiments/ppt-web-workflow-learning-20261016-v1.md) 和同目录 results.json 保留全部负例、缓存命中/未命中、输出、费用、耗时与文件质量。学习共 177 请求/$0.232263144（含失败），离线编译 0 模型；完整本轮 397 请求/$0.477209820，均代理估费，实付未知。
- 短说明三组实际交付，B0/B1/B2 请求 15/8/6；普通脚本和 Motif 收益分开。长论文六条件只有两份交付且有科研错误，不能据此宣称同质省费。原生网页 10 下载逐个 SHA 校验/刷新完成通过，Motif 两次实际 skip；其费用比 Baseline 略高，反例保留。
- 根 Python 795、Node 734、PPT 121 项通过；新增真实库锁 9 项及 smoke/motif:check 通过，最终 CI/发布见 PR 回执。私有 `.local/ppt-workflow-20261016/` 保存题面/原 PDF/真实轨迹/检查图，受保护数据不清理，预算沿用每侧 $0.115/每对 $0.23，累计与额外输出限制 null。
- 未完成：独立人类盲评、公式/图注/引用与叙事修订、人工分钟/账单核对、重复同质成本验证。本次没有新增运行期前端流式画面验收。下一步优先处理这些质量错误，不增加学得语义/全流程降本的主张。

## 2026-10-15 辅助附件准入的运行兼容复核

本次独立审阅以 `2a03e22` 为基线，检查共享 `harless_task_scope.ts` 与 `dsh_web_tasks.ts` 的 PPT 输入路径。附件入口接收并保存 Word、需求文本等辅助文件，但 `job.json.inputs` 与 `bindUploadedPptTask` 使用相同的 PDF/PPTX 子集；混合上传保留原上传顺序对应的 `document_id`，不重新编号。只有辅助文件时保持 `source_pending`、空 PPT job 和 `allow_output: false`，不创建已认证读取绑定。PPT 工具不会因此把辅助附件当作可 pin/read 的来源。

原上传 receipt 归属、字节数、文件 SHA、任务 job 身份、符号链接/硬链接/真实路径检查不变；所有附件仍进入批准快照和 `scopeDigest`。新增正文提取只读已批准副本，校验来源 SHA，发送前再核验完整 scope。现有 `pin_source`/`read_source` 参数契约、完整工具 schema、执行器和原训练产物未改。提取文本可影响模型的内容判断，不构成原 Motif 新能力或质量/费用认证。

已完成零模型诊断：从基线源码与当前源码分别绑定空来源、单 PDF、单 PPTX 和大小写混合 PDF/PPTX 四组，返回行、保存字节、job、批准快照及 scope 摘要逐项一致；混合辅助附件只将 PDF/PPTX 版本交给旧绑定，来源篡改、job 不匹配、无归属 receipt 和字节数变化仍拒绝，辅助文件改动使 scope 失效。`node --test tests/test_harless_report_inputs.mjs` 四项、`python -m pytest -q tests/test_harless_rsi_bundle.py` 六项通过；后者允许本机尚未构建的可选 `dist/` 文件缺失，不代表完整部署锁已验证。此处未运行真实模型或实际 MCP 初始化，不能把这些诊断称为实际工具/模型验收。

仅更新运行兼容记录中的 scope 源码锁（`a7b2c4dafba7d9babb7effc17f32961df4dac62aba0a29f28842483cab49ab3d`）及 `entry.json` 对该记录的摘要；原 certificate、library、manifest 与 schema 文件不改。部署前仍须核验最终源码/构建产物的全部 65 锁，实际 MCP 在 1/6/8/10/12 页的完整允许 schema，与混合附件/仅辅助附件的上传、当前来源绑定和既有读取守卫；由根任务统一执行并追加实际结果。更改 scope 后须重新审阅摘要，不沿用本次锁。

## 2026-10-15 输入限制取消后的运行兼容复核

共享 `harless_task_scope.ts` 仅取消 literature 分支的 4000 字符限制，导致 PPT 部署兼容锁失效；PPT 任务绑定、来源权限、SHA 与已学习 pin/read 读取路径均未改。此次只更新 `runtime-bindings.json` 的该文件锁与明确复核说明，并同步 `entry.json` 摘要；原训练证书、库、manifest 和 schema 文件逐字节保留，不构成重新训练或质量/成本晋级。

服务器私有诊断树已验证完整 65 个代码锁、20 项库/场景/编译守卫测试；实际 MCP initialize/list 在 1/6/8/10/12 页均返回 21 个工具，按既有 Web 允许列表选取的完整 19 工具 schema 与五个登记变体相等，job 字节未改变。模型调用与工具调用均为 0；生产切换由根任务统一执行。新增源码锁回归可在未构建 PPT 的根测试中发现共享源码漂移，存在构建产物时再核对完整运行包。

## 2026-10-14 后续分支集成

`feature/research-ppt-agent@7375185` 的 V16/V17 场景代码、反馈、局部恢复与持久库实验已纳入独立集成分支；历史真实实验仍按原记录解释。双路主聊天代码位于场景内，但未接入默认 `/harless`：其现有契约只支持本地操作人，且不继承 Mode/RSI，不能覆盖 PR #13 的统一 Runtime 与成员路径。匿名实验 Markdown 已复制；历轮 PDF 与私有产物不入 Git。

本机 PPT Node 构建/118测试通过；Python 279通过、2跳过，10个真实渲染断言因本机 LibreOffice PDF CJK 字形缺失失败。相同集成树在 V100 固定 Noto/LibreOffice 环境通过291项 Python、118项 Node；原字形守卫未放松。场景代码和 Prompt 改动使先前私有 PPT Runtime 包的代码锁过期；未重新认证前 Execute 应拒绝，不能靠重写旧摘要放行。本轮模型请求0。

## 2026-10-14 Web/成员部署（当前补记）

- Codex在 `codex/harless-launch-readiness-20261014` 完成Web库绑定与成员依赖挂载；最终功能验证 `396e2cf`，[PR #13](https://github.com/jingyio/DeepSeek-Harless/pull/13) 已推送/未合并，未切换公网、未修改原PPT研究数据/论文协作者工作区。
- 已取回的独立正常轨迹2训练/1留出经原编译器与实际完整19Schema认证，`deployment-v3/runtime`仅五个在线文件，只读闭合pin/read；逐任务用批准上传SHA绑定，不继承历史source_id。认证不是质量/费用晋级。旧证据保留，部署代码锁更新生成新包。
- 真实合成只读任务成功2HTTP/1Verified Skip；先前预算失败1HTTP/1局部skip单列。两成员实际bwrap/MCP、各一页中文PPTX/PDF/PNG机械交付通过，0模型，科学质量未评审。CPU转换及task内validation与checkpoint路径兼容修复；跨任务/软链接仍拒绝。
- 最短部署：安装/构建场景依赖，配置私有三个 `HARLESS_PPT_*` 变量及网关 `memberSceneDeployment`，运行 `node scripts/project.mjs python scripts/check-harless-members.py --render-ppt`；库准入与输出依赖失败明确拒绝。用户菜单可选页数/模板/新副本权限，默认只读。
- 结果、失败、环境、累计预算与版本边界见 [上线准备记录](../debug/harless-launch-readiness-20261014-v1.md)。下一步与Session负责人联合公网验收，再以真实论文生成任务独立人评。原V15研究结论不改，以下为历史交接。

## 2026-10-14 私有库迁移补记

Codex 按用户授权从旧部署取回 12 份 PPT Manifest 及 322 个库/认证依赖文件，同步到 V100 `.local/imports/ppt-library-transfer-20261014/`；本机同名私有目录也保留备份。两端逐项 SHA256 核验通过。4 份完整证据锁匹配旧部署，当前 Runtime 格式检查接受 10/12、拒绝 2/12；当前代码相较旧证据仍有版本变化，尚未认证迁移或绑定 Web Execute。此次模型调用 0，未改变预算、权限或历史证据。详情与接手步骤见 [迁移记录](../debug/ppt-library-transfer-20261014-v1.md)。以下保留原场景发布交接；原本机 `H:/DeepSeekHarness` 路径属于原负责人环境，不能当作本次 macOS 已存在的文件。

- 更新时间与交接人：2026-10-13，Codex。
- 目标与本次范围：停止扩展研究机制，收敛课题组试用。保留接口，朴素组会稿、双路生成/记账、版本安全修订、显式反馈与受控学习；结果见 `docs/experiments/research-ppt-v15-deployment-20261013.md`，历轮索引见 `docs/experiments/research-ppt-reports/README.md`；20 份 PDF 留在团队私有归档，不进入 main。
- 分支 / commit / 工作区：原场景开发位于 `feature/research-ppt-agent`；不含 PDF 的集成改动从 main `b330bb4` 另建 `codex/research-ppt-clean-pr`，已提交并推送，见 PR #5。原场景工作区与私有数据未覆盖；PR 审查及 CI 完成前不合并。
- 已完成：`trial.py` 两独立job、同模型/来源/schema/19工具、预览/显式付费、全账本/实际交付/待评审；`feedback_learning.py` 私有不可变反馈、去重、2训练/1留出、现有编译器、候选隔离、收益晋级/回滚；`accounting.py/runtime_snapshot.py` 替代旧轮次依赖。`ts/render.ts` lab v15.1及prompt/Skill采用朴素科研表达。TypeScript在线/Python后端，不改上游Harness。
- 最短入口：先按根README及 `scenarios/research_ppt/deploy-ubuntu18.md` 安装/构建并激活实际环境；`npm run ppt -- --input .local/inputs/paper.pdf --slides 6 --template lab --allow-output --collect-feedback` 仅预览；确认后 `npm run ppt -- --trial <实际trial.json> --call-model`。MCP与Python/JSON接口保留，无新UI。`--operation restyle` 受限样式转换；`direct_edit` 限同job、完整plan及明确page/changes，执行携原SHA生成新副本。
- 已验证：均在服务器 `/mnt/sevenT/junjiex/DeepSeekHarness-v9` 激活环境执行，日志 `test-logs/research-ppt-v15-deployment-20261013/`。最终根npm test 146Python/47Node；smoke18诊断/0付费；场景build及初批83Node/176Python；最终新增产品53回归；真实两路stdio schema/无active fallback、真实ledger/交付取证、局部修改真实LibreOffice与非目标XML/notes/media/样式保持。批次不相加；协议夹具不是云效果。单独Node测试缺统一Python环境曾失败，根统一入口复验通过，旧失败保留。
- 实验结论：V15 DoRA六页普通/组合请求18/12、token536799/307233、代理估费0.02201855/0.01778932美元、耗时92.503/75.822秒，双路总0.03980787美元。观察请求−33.33%、token−42.77%、费−19.21%；原稿有来源/均值/流程/局限问题，普通组使用组合修订、未独立人评，不支持同质量稳定降本。verified Motif=0，不称RSI效果。明确辅助修订新副本均0新增模型，不计原自主成功；人工/计算/维护/实付未知。
- 历史结论：V3 E4输出保持时减少请求、V10明确标题修改10/7→0有局部证据，不能推广完整生成。V6新工具/Motif真实使用但总成本仍高；V13/14候选或继承码verified各1，质量/恢复抵消局部收益。V14三组机械成功但科学有错，不支持同合格质量净收益。公开V1–V14总报告18页不构成跨任务持续降本曲线。
- 学习边界：默认learn=false、科学/视觉pending；本轮两路原账本入库至显式v2库，原记录不改，训练0/新候选0。稳定前缀/共同题面从真实prompt字节导出，完整prompt绑定manifest；旧缺字段拒绝认证。`--candidate-version` 隔离评测，`--use-active-learning` 仅继承当前有效晋级版。晋级需两独立新任务人评/全费/人工分钟、真实execute/manifest/冻结审计/verified旁路；active和回滚重查最新批准证据。本轮没有真实新候选晋级或完全自主长期学习结果。
- 配置与数据：公共Schema/锁/工具在 `scenarios/research_ppt/`；来源、credentials、runs、反馈、交付留 `.local/`。变量 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL` 用途公开，值不记录。服务器旧HEAD `6ced8277d7743bcb260975290665af26d105274a` 加部署，真实运行不是最终发布HEAD；原快照保持。思考/压缩off，proxy账本不当实付。
- 交付：原稿本机 `.local/research-ppt/research-ppt-v15-deployment-20261013/deliverables-01/`；辅助稿同根 `assisted-02/assisted-{baseline,optimized}-02/delivery/revised.pptx`，含PDF/PNG/overview。原稿22/辅助38文件SHA/size核验一致。V1–V14 PDF/清单/39PPT路径索引在本机 `.local/research-ppt/reports/`；公开汇总PDF身份见 `summary-manifest.json`。
- 发布清理：保留最新main团队Web/请求上限/预算/API。PPT公共差异仅场景、文档、入口、Windows file-URI及窄闭合pin/read，增加版本/schema/barrier回归。八个历史矩阵/报告脚本逐文件备份核验至本机 `.local/research-ppt/release-archive-20261013/`；开发树/历史数据和关键安全测试保留。见 `docs/operations/research-ppt-release-cleanup.md`。V12–14隔离原生服务/五套素材未作为本次默认后端发布，私人原型不称已接入。
- 未完成与限制：同学独立科学/视觉评审及人工分钟、账单；任意外部PPT无损编辑、完整主张/公式自动正确性、任意中断恢复、完全自主进化；基础插件无Python依赖。Ubuntu18需兼容工具链/字体，SDK runtime-bin缺项仍不能泛称标准pip部署完成；Windows完整真实渲染未验证。
- 接手下一步：1）同学提交1真实任务、双路运行并填review，科学/视觉不合格不发布节省结论；2）按具体页反馈明确patch，记人工分钟且原稿保留；3）独立授权合格轨迹2训练/1留出后离线认证，以两新任务完整质量/费用决定晋级，无active走普通流程，不扩候选矩阵。
- 权限与预算：既有不限DeepSeek实验授权持续，本轮proxy0.03980787美元、实付未知；默认预览，每路1.50美元/40步。新副本、备份及整理中文commit/push已授权，提交前告知，无PR；后续用户数据学习需明确授权，私有日志/凭证不公开。
- 回退与风险：发布前产品基点 `4008d2d`；新风格可选academic或旧renderer。来源/代码/证书改变需新job/认证，不重签旧结果。权限/schema/version拒绝保持；异常写锁先确认无写入者再处理，不称任意SIGKILL自动恢复。科学理解/选材仍需模型/人审，机械通过不是事实/审美合格。
