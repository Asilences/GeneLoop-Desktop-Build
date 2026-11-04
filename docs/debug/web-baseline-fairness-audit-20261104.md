# 网页 Baseline 与 Motif 公平性审计

## 用户要求后的实现候选

用户要求清理重复产品提示、普通 Chat 的默认 PPT Skill，并集中存放调试日志；随后要求网页匿名双栏、随机左右顺序和后台完整记录，以 PR 交付。本轮实现位于 `codex/fair-comparison-ui-20261104`，基于最新 main `b8e04296`。

- 完整 system 组装时剔除重复的 preset persona 段，产品身份和隐私规则各一份。注册器同作用域不允许同名覆盖，首次实现触发该检查后改用公开 `system-prompt/assemble` 钩子，10项提示/原生工具诊断通过。
- 原全局 `ppt-master` Skill 注册移入 PPT 场景绑定，按 Agent scope 保存，解绑时释放。正常双栏入口诊断确认双方 PPT 子会话可加载，普通 Chat 与宿主目录为空。macOS 临时路径规范后专项通过，原失败保留。
- `display_order` 在准入前随机并持久化，结果正文前的方法名称已去除。匿名位置仅影响展示，内部真实 lane 与全部原始证据保留。评分和反馈增加显示位置记录，104项对照服务/浏览器组件诊断通过。
- 结果卡片同时隐藏复用计数和回退标识，预览标题及轨迹选择改用中性文字。模型自行生成的正文与产物原样保留，开发 API 也保留真实字段，匿名展示不作为隐藏开发接口数据的安全边界。
- 按用户确认的分类迁移88份历史调试与工程联调 Markdown，更新 Markdown 链接及导出器验证记录路径；科研实验留在 `docs/experiments/`。`docs/debug/README.md` 保存历史路径索引。AGENTS.md 已约束新记录和私有原始材料的集中目录。
- 精确兼容导出采用 PPT76→77、Paper78→79，原程序、schema、任务和来源证据逐字节不变。导出检查覆盖本次源代码变更和文档路径调整，本次训练与模型调用均0。

以下调查保留当时部署版本和历史观察，其“只读”范围属于前面的调查阶段。实现后的完整回归及 PR 状态见文末“实现验收与交付”。

## 结论与优先处理

- 用户最新明确本轮重点为首次模型请求的 prompt，后续过程交给各方法自然执行。此前将后续澄清、选路及历史分叉列为公平性问题，范围过宽。本轮以起点是否存在额外偏置为判断边界，过程观察单独保留。
- 初始输入核对覆盖完整 system、用户消息、首次附件上下文、预载 Skill/程序目录和工具 schema。共同模型参数同时核对。方法本身需要的初始信息单列为处理条件，公共层额外出现的身份、流程和能力差异才作为待排查偏置。
- 已从原生会话事件重建八对无继承交流前缀的首请求。PPT、Paper、Data 各两对共六对的完整输入在仅归一化正文 task_id 后相同，包括通过原生 provider serializer 重建的请求 JSON。Video 两对的文字消息与 system 也相同，但右侧额外四个工具。普通 Chat 另核对两条单路任务。过程与证据见下一节。
- 对本次抽取的最近 100 对历史任务，99 对有两侧有效配置。这 99 对的模型、推理档位、场景提示摘要、工具可见来源版本及预算配置逐对相同。PPT、Paper、Data 共 93 对的完整工具 schema 摘要也相同，Video 六对均不同。未观察到这些配置项系统性削弱某一侧。
- Video 的四个额外工具属于首次请求中已存在的方法差异，本地新 PPT 程序目录同样属于初始提示条件。它们应在报告中明确归属，是否构成不合理偏置取决于实验要测的是完整方法还是单独接管机制。六对输入等价结果支持已核对样本的公共起点对齐，其他任务和含图片的最终 wire 仍按覆盖范围分别判断。
- 已找到双 baseline 的 169/70 次请求分叉，以及后续收到不同补充答案的 4/159 次请求分叉。这些是运行结果与过程解释，不直接证明初始 prompt 不公平。
- 普通 Chat 当前为单路 baseline。无场景任务若显示在双栏中，需要核对该轮实际 scene。今天的静态画像请求实际进入了 Video，优化侧经过视频制作链后再交付图片，观察到场景与任务错配。
- 以本轮首请求差异清单为基础讨论修改，后续提问、选路、修复和工具调用保持自然展开，作为方法表现评价。当前证据尚不能确认“我们的方法在无 Motif 时稳定降低生成质量”，成品质量也未盲评。

## 完整首请求核对结果

### 重建方法与校验

之前仅检查应用自己的 `model-request-config.json`，遗漏了原生 DSH 事件里的完整输入记录。现确认 `dsh-agent-loop` 在首次调用前写入 `system/message`、`user/message`、`request/header` 和 `request/context`，随后从相同 Session surface 调用 `deriveMessages()` 构建请求。因此可以在读取首次 assistant 事件之前截断日志，离线重建当时的完整请求边界。

先抽取各场景最近两条新子会话，再排除带继承交流前缀的条件，得到四场景各两对共八对。另取两条普通 Chat。这里“无继承交流前缀”以持久化的 `prior_context` 全为 `[]` 核验，任务可以有本轮真实附件。第一轮抽样中存在旧产物和历史交流差异的三对单列保留，其差异落在继承上下文，未混入这八对。

本地使用线上同版本的 `Session.create(...).deriveMessages()` 和 `requestHeader()`。已从正式服务计划定位依赖安装目录，逐一核对 `dsh-session`、`dsh-agent-loop`、`dsh-llm-deepseek` 的版本 `0.1.5-rc.3` 及 `lib/index.js` SHA256，三者与本地逐字节相同。

随后经同一原生 DeepSeek serializer 重建 body，在 `prepareExtensions` 收到已序列化 body 时保存并主动结束。全局网络调用另设拒绝守卫，实际 fetch 次数为 0，真实模型请求为 0。这是已有真实输入的离线重建，没有生成替代模型答案。网页 provider 子类已核查，只调整输送 session header、输出容量和取消 signal，所核对的正文不受额外变换。原应用的 extensions 配置为空。

### 逐场景结果

| 场景 | 无继承前缀样本 | 完整 system | 用户正文/附件上下文/Skill | 工具定义与顺序 | 参数 | 首请求差异 |
|---|---|---|---|---|---|---|
| PPT | 2 对 | 相同，约 1.19 万字符 | 仅 task_id 不同 | 25/25，逐项相同 | 逐项相同 | 正文里的 task_id |
| Paper | 2 对 | 相同，15944 字符 | 仅 task_id 不同 | 44/44，逐项相同 | 逐项相同 | 正文里的 task_id |
| Data | 2 对 | 相同，约 1.04 万字符 | 仅 task_id 不同 | 37/37，逐项相同 | 逐项相同 | 正文里的 task_id |
| Video | 2 对 | 相同，约 1.07 万字符 | 仅 task_id 不同 | 31/35，右侧多四个程序工具 | 逐项相同 | task_id 与四个复用工具 |
| 普通 Chat | 2 条单路 | 8200 字符 | 检查了实际初始消息 | 22 个工具 | 一条 High、一条 Max | 当前只有 baseline，无双侧可比 |

六对 PPT/Paper/Data 的 provider body 在仅归一化实际正文中的 `task_id` 后完全相同。所有八对的 system 都逐字节相同，不存在样本中右侧独有的弱化能力、强制省 token 或额外工作流指令。首次用户消息中的附件身份、内容及顺序也核对一致。

任务 ID 的原始值确实进入模型可见的附件上下文，不只是传输 header，因此原始请求不是逐字节相同。它属于任务身份差异，目前没有证据表明它系统性偏向一侧。会话内 message ID、rpcId 和左右标题等元数据经 provider serializer 后不进入正文，此次相等判断没有将它们误计为模型输入差异。

Video 的额外四工具是已发布的学习程序接口，属于现有方法的能力扩展。双方完整 system 都还包含“适用时优先使用可用学习程序”的指导，其中 baseline 没有对应四工具。该指导带有可用性条件，不能直接认定它导致 baseline 退化；需要记录的是初始可选动作集合确实不同，即使最终程序调用为零，也不是同一工具条件。

### 初始公共提示中的共同问题

- 十条检查任务的 system 中，产品身份段都重复出现两遍。对应配置 persona prefix 与 `bindProductPrompt` 的 identity section 同时生效。它增加共同提示长度，本轮未观察到左右不对等。
- 普通 Chat 也收到约 1200 字符的 ppt-master Skill 摘要和命中时加载的指令。完整 Skill 尚未在首请求加载。该目录来自共享安装，对所核对的四场景两侧相同，不能用来解释同一对里的单侧退化。对普通任务是否造成 PPT 选路倾向尚未验证。
- 专用场景的制作/报告流程文字仍随该 scene 注入，两侧相同。用户任务超出场景适用范围时可能受共同约束，其影响需和任务实际 scene 对照，不能仅按最终是否调用 Motif 分类。

### 首末请求口径纠正及覆盖边界

先前称今天检查的异常任务均为 Off，依据是会覆盖的末次 `model-request-config.json`。原生首请求 header 显示，画像 Video 任务 `comparison-1768a52b-f7da-481a-a19c-10dd07e69f87` 两侧起点实际都是 High。两个 PPT 样本分别为 Off、High，Paper/Data 样本为 Off。任务中档位的后续变化不在本轮初始公平性判断内，起点参数以原生 header 为准。

八对无继承前缀样本均可经文字/文件序列化路径重建 provider body。另三个带继承历史的首请求中，有两对包含原生图片，其 durable attachment 标识已比较，因未导出图像请求版本字节，未重建图片上传后最终 wire body。此次相等结论只覆盖上述八对，不能外推所有历史任务或未采样版本。

私有完整输入及差异保存在 `.local/debug/web-baseline-fairness-audit-20261104/first-input-fresh-native-events.json`、`first-input-fresh-reconstructed.json`、`first-input-fresh-wire-and-diff.json`，匿名结构结论在 `first-input-fresh-comparison.json`。重建命令为 `node .local/debug/web-baseline-fairness-audit-20261104/reconstruct-first-input-fresh.mjs` 和 `node .local/debug/web-baseline-fairness-audit-20261104/compare-first-input-fresh.mjs`。初轮含继承历史的输入和差异另保留 `first-input-*` 文件。

## 范围、版本与方法

- 实验 ID 为 `web-baseline-fairness-audit-20261104`。类型为现有真实任务的只读调查和确定性诊断，新增模型请求 0、模型费用 0。
- 用户明确 baseline 指网页双栏 Baseline。实际生效的 `comparison_scenes` 为 `ppt`、`paper-proofreading`、`research-data-analysis`、`video-editing`。文件管理走独立 SDK 单路，另行说明。
- 本地审计开始于 `2da62957`，结束核对时共享工作区已被其他工作推进至 `04d6d7b5`。相关在线宿主、comparison、视频与产品提示实现未在这两个版本间变化。私人 `reference/` 以及其他工作的修改不属于本次交付。
- 服务器从已有项目私有 `.local/remote-env.sh` 发现 `GENELOOP_SERVICE_HOME` 和 `GENELOOP_SERVICE_CONFIG`，沿统一入口执行 `service status/check`。owner/gateway 均运行、owner 认证通过、登录检查 200。
- 当前计划的 `gateway.sourceDir` 对应源码为 `70f86583e740f7e8f264802c1749513429c40850`，源码检出干净。服务入口所在检出与实际应用源码检出不同，定位以运行计划为准。
- 运行 policy 为真实 provider，任务/累计费用、次数和应用输出额度为 `null`。检查过的今天异常任务实际模型均为 `deepseek-flash`、`reasoning_effort=off`、wire `max_tokens=393216`。
- 从 owner 与成员已有 comparison store 中，仅导出匿名配置/计数，再针对五个异常任务提取必要轨迹。所有原文、工具参数、私人申请书内容及内部路径仅存忽略的 `.local/debug/web-baseline-fairness-audit-20261104/`。
- 快照共发现历史双栏 434 对，按时间取最近 100 对，时间覆盖 2026-10-31 至 2026-11-04。含合成压力诊断、问候、真实用户任务、失败和在途任务，不能据此估计平均质量或总体收益。快照时两侧都 completed 为 97 对，其余三对在途或未完成；100 对中有一对缺少完整双侧配置。

## 已验证的共同条件

| 场景 | 最近抽样对数 | 双侧配置完整 | 提示摘要相同 | 工具 schema 摘要相同 | 模型/推理/预算/来源版本相同 |
|---|---|---|---|---|---|
| PPT | 33 | 32 | 32/32 | 32/32 | 32/32 |
| Paper | 28 | 28 | 28/28 | 28/28 | 28/28 |
| Data | 33 | 33 | 33/33 | 33/33 | 33/33 |
| Video | 6 | 6 | 6/6 | 0/6 | 6/6 |

这里比较的是落盘的有效配置和来源版本。`instructions_sha256` 只覆盖场景指令，不能证明整个 system prompt、全部插件消息及每次实际 wire 请求逐字相同。工具摘要涵盖 schema 与顺序。来源比较按各侧 `scene_inputs` 中记录的内容版本进行。

## 四个场景分别分析

### PPT

**当前生产实现。** 两侧共享锁定的 ppt-master、场景提示和 25 个工具。优化侧仅在合格读取边上用认证结构接管。没有合格来源时记录 `rsi_requires_approved_sources`，随后使用普通模型。两侧都需要完成原生设计、生成、渲染及查看像素。入口见 `src/adapters/dsh_web_tasks.ts` 的 `preview/configureMotif` 与 `scenarios/ppt_master/prompt.md`。

**真实分叉 1。** `comparison-cb5086af-6d3b-4a12-8172-89c31f836723`，北京时间 11 月 4 日 15:32 开始，初始请求为“帮我画个雪峰”。双方模型、推理、输出容量、工具摘要和真实用户消息摘要相同，来源为空。Baseline 4 次请求、Motif 159 次请求、Verified Skip 为 0，优化侧明确记录缺少获准来源回退。

但后续输入已经不同。Baseline 三次提问收到“某个人或机构”“一份 PPT”“老师”“个人介绍/教学分享”等答案，最后等待具体材料。Motif 收到“是张雪峰”“你来定，我授权你自主设计”“传记/纪念式”等答案，随后检索、制作 9 页 PPT，并调用子 Agent。审计记录包含 36 次子 Agent 模型请求。因此这不是同等信息与同等工作量下的 4 对 159。这里仅追踪执行范围，没有核实人物事实或评价该 PPT 的内容质量。

**真实分叉 2。** `comparison-61f7da2e-4553-4553-9433-aba88e13e00a`，两侧最终有效模式均为 baseline，仍分别 169、70 次请求，工具调用中的 Bash 分别 130、55 次，Verified Skip 均 0。另一个 `comparison-3733b809-04ce-40d8-be81-03f260683145` 同为双 baseline，分别 85、112 次请求，错误 1、6 次。都要求制作三页 PPT，两侧报告完成了成品。这证明长链制作本身存在很大的路径差异。成品质量未盲评，未保存逐请求完整输入，采样波动与完整上下文差异各自贡献尚未分离。

**本地候选的新增条件。** 当前工作区的 `ppt_program_learning.ts` 会给 execute 任务加入页面程序目录、优先复用指导，`pptComponentScene` 还可能加入 `create_ppt_page`。即便最终复用为 0，也可能影响选路。`70f86583` 的生产宿主没有接入这段新增程序学习，所以它不能解释上面今天的生产异常。当前候选与生产需要分别验收。

### Paper

两侧共享论文工具和场景规则，当前生产库为 `paper_document_read_v1`。已认证的 pin/read 等读取续接可以减少模型决策，科研判断和报告正文仍由模型生成。

今天 `comparison-23227179-9e56-4db5-a153-6cbd8dcb4448` 的同一申请书建议任务，Baseline/Motif 分别 74/63 次请求，工具错误 2/6，优化侧 Verified Skip 为 1。两侧实际用户文字、文件版本、模型参数和工具 schema 相同，都生成了报告，但读取、外部核验及报告恢复路径不同。只能确认发生一次已验证请求旁路，剩余请求差额和建议内容差异尚不能全部归到这次旁路。没有独立盲评，不能用 completed 或 PDF 导出成功推断建议同质。

库不适配时 `configureMotif` 记录原因并走普通模型，在线 interceptor 无候选或守卫失败时调用原 `next()`。本轮没有发现这里悄悄改为较弱模型或减少输出容量的证据。场景提示本身有较多文献证据/报告流程要求，用户只要一般讨论时，两侧都可能受这些流程牵引，牵引强度随模型选路变化。

### Data

两侧共用分析工具、来源和场景指令，生产库为 `data_receipts_v3`。实际复用是精确 receipt 绑定及当前计划的 `allow_deterministic_continuation` 授权。库含十条确定性续接，例如分析到复算、绘图到检查、正文到组版、验证到交付。`approve_analysis`、`approve_presentation`、`submit_report_text` 三个语义关口保留模型判断。

抽样中十个已完成历史任务各发生十次 Verified Skip，例如 `comparison-9cf8d5cb-6b37-43b1-8ce1-9be9c0f60d2a` 为 28/13 次请求、错误 1/0；另一个为 50/18 次请求、错误 1/0。因此已发生的差额包含确定性续接和两侧恢复路径差异，不能把整个差额都计为“十次直接跳过”。

无合格研究来源、计划未授权或新语义关口时，interceptor 直接交还普通模型。这里尚未找到单侧模型/工具/预算条件差异。生成内容质量主要仍取决于三个语义判断、正文 token 绑定、数据转录和报告排版恢复，需要逐项对照真实结果。强制简报、限定统计设计和结构化交付会约束两侧的任务表达范围，其对不适配任务的影响没有独立测量。

### Video

**存在明确的实验条件差异。** 普通侧有 11 个视频工具，优化侧额外获得四个发布程序工具，加上共同工具后为 31 对 35 个。两侧仍可使用普通源码写入和渲染能力。实现见 `harless_video_program.ts:9`，它只在非 execute 侧移除程序工具。即使最终程序复用为 0，优化侧已经面对不同的工具选择集合。

今天 `comparison-1768a52b-f7da-481a-a19c-10dd07e69f87` 请求画静态人物图，实际 scene 为 `video-editing`。Baseline/Motif 分别 33/45 次请求，程序复用均为 0。Baseline 走普通代码绘图、读图及交付；Motif 走了六次 `render_composition`、五次 `inspect_render`，再交付静态图和一秒静止视频。优化侧还单独收到一次“卡通风格静态图”的澄清答案。

这例确认了超出视频任务范围时的实际绕路，额外程序工具对绕路的因果贡献仍需工具集合匹配消融。两侧均没有专用图像生成工具，产物依赖模型编写图形代码及其视觉修订。单凭成图观感，不能分离基础绘制能力、任务范围、额外工具和随机选路的贡献。

## 未支持场景及无 Motif 情况

### 真正未选择场景的普通 Chat

生产 `comparison_scenes` 不包含 `new-scene`。路由采用 `presentation=single`，只执行 baseline lane；快照中 403 条 `new-scene` comparison 记录全为单路，原生直接 Chat 还有另一条执行入口。单路内部字段叫 baseline，不会因此产生第二个优化侧。

因此，屏幕存在双栏时应先核对该轮落盘 scene。今天两个“画图”任务分别进入了 PPT、Video，任务内容虽然超出对应专用流程，场景提示和工具仍然生效。仅凭“没发生 Motif”不能将它们归入无场景的同条件实验。代码在正常新会话和消息后重置场景选择，但仍须用实际 task/effective-config 核对用户操作形成的最终路由。

若需要研究普通 Chat 的开关差异，应在同一个通用宿主上，冻结全部工具和提示后显式作两组实验。当前产品单路本身没有提供这项效果对照。

### 已选场景、任务超出范围，或库未命中

`configureMotif` 的 baseline 模式直接返回，读取 interceptor 的空候选和守卫失败分支调用同一个模型 `next()`。这是代码层面的回退路径。仍有五个需要分别控制的条件。

1. **澄清输入。** `geneloop_interactions.ts` 按 lane/task 保存独立待答问题，只把答案交回对应调用。今天 PPT 已实际发生不同补充答案。这解释后续任务范围变化，按用户最新口径归入过程记录，不凭此判定初始 prompt 不公平，也不要求强制同步双方问题。
2. **历史状态。** `harless_comparison.ts:325` 按各 lane 保存历史回答，`:335` 按各 lane 继承产物。换附件/换场景时会重新建子会话并传回各自历史。研究初始差异时优先选新会话，已有多轮对话单列为连续任务观察，其自然累积差异保留。
3. **工具及目录暴露。** Video 已确认不同，本地新 PPT 程序目录也会改变输入。没有实际调用复用工具，不能抵消其出现在模型输入中的影响。
4. **普通模型的执行路径。** 两侧均有 Bash、读图、搜索、子 Agent 等能力。首次选路后，失败、修复和检查次数可能快速分叉。双 baseline 的 169/70 次请求是已观察实例，未证明这种波动的全部来源。
5. **观测口径。** Verified Skip 只统计已核验旁路，零值不能排除失败接管、额外目录、工具变化及此前轮次影响。请求数还包含子 Agent、搜索或视觉等调用。完成状态与请求数均不能代替成品质量。

### 独立文件管理

当前 File 走 `harless_file_scene.ts`、独立 SDK 与自身文件工具/计量。公开单路投影同样使用 baseline 字段。它与主聊天的工具表和执行上下文不同，本次四个双栏场景的相等性结论不覆盖 File。跨入口比较时需先匹配宿主和能力集合。

## 公平性判断与修复优先级

### 补充调查 控制、展示和评价口径

用户随后明确先完成调查，再一起决定修改。本节补充实现与诊断证据，本轮交付范围继续为调查记录。

**双栏的模式控制与父会话偏好不同。** `dsh_web_tasks.ts` 的双栏 prepare 固定将左侧设为 baseline，右侧按库是否可用决定 execute/shadow/baseline，再直接覆盖子会话 selection。admit 并未传递父会话的 mode/rsi 作为本轮对照条件。因此父会话保存 `rsi=false, mode=shadow`，仍可能产生 execute 右侧。当前前端在 `paired_comparison=true` 时隐藏模式与 RSI 菜单，这说明双栏有其固定对照语义，不能仅据代码认定为意外遗漏；但用父会话偏好声称“两侧已关闭机制”会造成错误归类。

已在忽略目录复用原测试 fixture 做三项诊断。对 PPT、Paper、Data，先确认父会话确实保存 rsi=false/Shadow，再发送场景任务；原断言仍确认左 baseline、右 execute，三项通过。这是控制行为诊断，未调用真实模型。证据为 `paired-rsi-control-diagnostic.mjs/.tap`。生产 `70f86583` 同样具有该分流逻辑。本轮尚未复测生产里的用户设置变更。

**方法标签与实际执行模式有差距。** `harless_web_client/client.js` 的右侧标题仅在 shadow 时加“影子评估”，baseline 回退仍标题为 Motif，下面另显示回退说明。历史抽样 100 对中有 23 对两侧有效模式都是 baseline。若只按左右标题分组评分或统计，这 23 对会被误当作机制启用与禁用的效果对照。标题没有提供可靠的实验分组，实际组别需要结合 mode、回退原因、目录/工具暴露、接管尝试和回执判断。

**跨次重试的网页指标只显示当前尝试。** `harless_comparison.ts` 的 retry 增加 attempt，替换 task_id；`applyTask` 随后把 stats、开始/结束和 duration 替换为新 task 的值。之前任务的日志和账本仍保留，但当前 comparison lane 和网页指标没有合并之前失败尝试的请求、费用和时间。免费错误注入诊断中，右侧第一次失败 7 次请求，第二次成功 3 次请求，最终 lane 显示 3；不能把该值当成到成功为止的总请求 10。诊断 `retry-accounting-diagnostic.mjs/.tap` 通过。本次抽样所有 lane 的 attempt 都为 0，所以这项没有解释已抽样任务的差距，只是实际存在的测量边界。它可能偏向重试较多的一侧，具体方向取决于任务。

**现有评分不是盲评，失败还影响评分可用性。** 前端固定左 Baseline、右 Motif，评分时可见方法名；`scoring_available` 要求两侧都 completed，单侧失败后两侧数值评分均不可用。若用这些分数衡量纯质量差异，会同时混入标签预期和“只比较双方完成任务”的筛选。当前实现确认了这两个评价条件，尚未测量标签偏差的大小。失败率、交付质量和双方完成后的条件质量需分别报告，不能用评分样本替代全部任务。

上述发现按用户最新范围重新归类。首请求中的提示、工具与目录暴露是本轮公平性调查对象；后续澄清、选路与修复是自然运行观察；模式控制与标题用于解释实际方法分组；重试和可见标签属于测量边界。后二类保留记录，初始 prompt 调查优先推进。

| 项目 | 状态 | 判断及最小下一步 |
|---|---|---|
| 单侧模型更弱、推理更低、输出截断或预算更少 | 已查配置未发现 | 保留相同选择及逐请求校验，不用此次审计宣称所有历史请求已完整匹配 |
| 双侧收到不同澄清事实/授权 | 已观察，属于后续过程 | 记录其对任务范围的影响，后续提问自然展开，初始公平性判断另核首次请求 |
| Video 首次请求额外四工具 | 已确认方法输入差异 | 标明属于完整方法的能力扩展，单独识别与研究机制无关的额外偏置 |
| 普通任务进入专用场景后绕路 | 已观察 | 按最终 scene 和任务适配性分组，补通用任务的独立同宿主对照 |
| 多轮历史和产物分叉 | 代码已确认，属于连续过程 | 初始比较优先新会话，连续任务保留各方法自然历史 |
| 本地 PPT 目录/页面程序的零调用影响 | 接线已确认、生产尚未接入 | 候选独立测目录暴露、工具暴露、实际复用，避免解释成既有线上问题 |
| 首次模型请求的完整输入对照 | 未验证 | 首先只读捕获首请求的 system/messages/tools、模型参数及来源版本，区分公共内容与方法特有内容 |
| 父会话关闭/Shadow 偏好与双栏右侧模式不同 | 三项免费诊断复现 | 对照记录显式保存实际模式及控制作用范围，专门定义零机制实验入口 |
| 回退 baseline 仍显示 Motif 标题 | 实现及 23 对历史模式已确认 | 实验分组依据实际执行证据，区分方法标签和该轮机制状态 |
| 单侧重试后的指标覆盖先前失败尝试 | 免费错误注入复现，抽样未触发 | 报告成功前累计请求/费用/时间，同时保留单次值 |
| 固定方法标签及双方完成才可数值评分 | 实现已确认 | 独立匿名评审，同时纳入失败和未交付任务 |

当前 `model-request-config.json` 每次写入会覆盖同名文件，而且仅记录模型参数、工具顺序/摘要与真实用户消息摘要，没有记录完整 system 和插件消息前缀。问题答案位于 tool/result，也不被 human_message_sha256 覆盖。因此现有记录足以查上述差异，尚不足以逐请求证明零命中透明性。

实现定位可从以下入口复核。

- [执行宿主与模式分流](../../src/adapters/dsh_web_tasks.ts)、[对照历史与产物继承](../../src/adapters/harless_comparison.ts)、[独立问题与答案归属](../../src/adapters/geneloop_interactions.ts)。
- [读取 Motif 的空候选回退](../../src/adapters/dsh_online_motif.mjs)、[Data receipt 接管](../../src/adapters/harless_legacy_motif.ts)、[Data 三个语义关口](../../scenarios/data_analysis/report-prompt.md)。
- [Video 模式工具表](../../src/adapters/harless_video_program.ts)、[Video 工作流提示](../../scenarios/remotion_edit/web-prompt.md)、[候选 PPT 程序目录](../../src/adapters/ppt_program_learning.ts)。

以上链接指向当前工作区。生产差异用 `git show 70f86583:<仓库相对路径>` 复核，不能把当前候选文件直接当成生产实现。

后续验证按用户最新范围收窄为初始条件对照。先选择新会话、同一用户题面、相同材料版本和模型参数，捕获双方首次发往模型的完整请求。对每个差异标注公共层额外偏置、方法本身所需信息或仅任务标识差异，再由用户决定要改哪项。

- 四场景分别核对共同产品身份、任务流程、Skill、附件前处理及原生工具，列出 Motif 额外目录/工具/指导在首请求中的实际位置。
- 不适配场景和普通 Chat 分开核对初始选路与提示，尤其查有无无关的专用流程指令。
- 若首请求相同且未发生机制接管，后续差异首先作为普通运行波动的观察；多次重复后再判断是否存在稳定趋势。
- 首次请求后交由原生运行自然推进。提问、计划、工具选路、重试和修复均作为结果记录，公平性验收不要求双方路径一致。

成品质量与完整成本评价仍可保留，但其结果不要求干预执行过程。涉及额外消融或修改时，在首请求调查结果基础上再讨论。当前用户未提供独立评分，本轮也未启动新增付费实验。

## 验证、失败与复现

- 线上统一 `npm run service -- status`、`check` 通过，只读检查新增模型请求 0。
- 本地 Node 22.22.3，项目 Python 使用 `.venv312/bin/python`。
- `SSS_PYTHON="$PWD/.venv312/bin/python" node --test tests/test_dsh_online_motif.mjs tests/test_harless_comparison.mjs tests/test_ppt_program_learning.mjs tests/test_harless_product_prompt.mjs`，47/47 通过。
- `SSS_PYTHON="$PWD/.venv312/bin/python" node --test --test-name-pattern='new sessions ignore|parallel comparison keeps|native comparison images|reasoning' tests/test_dsh_web_tasks.mjs`，解除回环端口沙箱限制后 12/12 通过。首次 12 项均因 `listen EPERM 127.0.0.1` 失败，原失败日志保留。这些是确定性回归诊断，不作为生成质量证据。
- 补充调查在忽略目录建立既有测试 fixture 的诊断副本，增加父会话关闭/Shadow 控制和重试指标检查，分别 3/3、1/1 通过，新增真实模型请求 0。没有更改受版本控制的运行代码或测试文件。
- 首次远端采集使用系统 Python 3.6，因 `subprocess text` 参数失败。改用项目环境 Python 后采集成功。网络沙箱曾拒绝 SSH，获得只读执行审查后完成。
- 匿名配置快照为 `.local/debug/web-baseline-fairness-audit-20261104/server-snapshot.json`，必要任务摘录为 `task-details.json`、`interactions.json`，两轮诊断日志同时保留。文件可能包含私人信息，不进入 Git。服务器原轨迹保留在原任务目录。
- 本次交付为调查记录及交接。本次记录尚未提交、推送，成品盲评、逐请求完整输入比较和新增配对真实验收均未完成。没有本轮质量提升或净降本结论。


## 实现验收与交付

- 代码基线为 `origin/main` 的 `b8e042965487a80305c851324f1e911a57ccfa8a`，实现分支为 `codex/fair-comparison-ui-20261104`。单独检出隔离了其他分支的 Evolution 工作，私人材料未进入提交。
- Python 完整回归为 2405 通过、261 跳过。执行 `TMPDIR=<规范临时目录> npm test` 时 Python 全部完成，随后 Node 首轮发现两个缺少原生 Skill 服务的测试宿主、一处旧方法按钮断言和两项本地网络超时。已补齐测试宿主依赖并更新匿名断言，相关22项在原生回环端口权限下全部通过。
- 最终完整 Node 回归为1649通过、23跳过、0失败、0取消。命令为 `TMPDIR=<规范临时目录> SSS_PYTHON="$PWD/.venv312/bin/python" SSS_PURE_CODE_PYTHON="$PWD/.venv312/bin/python" node --test --test-concurrency=4 tests/test_*.mjs`。本次使用 `/private/tmp/` 下独立临时目录，实际路径记录在私有 `test-temp-path.txt`。首轮直接采用 macOS `/var` 临时别名时，原路径安全守卫拒绝若干夹具，规范路径后完整通过，守卫保留。
- `npm run smoke` 通过18项任务、83份来源的无模型工具检查。`npm run motif:check` 通过现有结构编译/执行检查。以上均为确定性诊断，本轮新增模型调用与费用均0，生成质量与降本效果未评测。
- 最终提示/原生 Skill/对照服务/浏览器组件专项115/115通过。匿名展示专项覆盖两种左右排列、刷新后顺序、失败侧重试、冷恢复、旧记录迁移、评分与反馈的真实 lane/结果哈希/位置绑定。旧版已完成节点缺少排列时等待服务端完成补齐后才展示结果与评分，避免加载时换位。结果前的方法标题、默认复用计数、回退提示及方法专属标题/选择器颜色已移除，辅助操作使用“回复1/回复2”。过程详情与模型原始内容仍可追溯，未做内容改写。
- 迁移核对确认88份原记录目的文件存在，旧路径已移除。178份受影响及集中调试 Markdown 的相对链接检查没有新增失效链接。历史 README 快照已有的仓库根相对链接按原语义保留，历史证书路径通过目录索引追溯。`git diff --check` 通过。
- PPT77/Paper79最终兼容导出成功，通过真实加载与版本守卫，原IR、schema及来源证据不变。最终13项库加载诊断通过。导出过程无新训练和模型请求。
- 本轮交付为 PR。生产服务与远端 Web 未重启或切换版本。当前验证覆盖本地原生插件、服务和浏览器组件，尚未进行部署后的真实浏览器与模型成品验收。
- 私有成功及失败日志包括 `pr-full-regression.log`、`pr-regression-fixes-native.log`、`pr-node-final-canonical.log`、`pr-smoke.log`、`pr-motif-check.log` 和 `library-export-final.json`，均集中保存并保持忽略。

首次向仓库旧地址推送收到 GitHub `failure in commit_refs`，已确认远端没有形成分支或PR，改用当前仓库地址重试。原错误保留在本轮操作记录中。
