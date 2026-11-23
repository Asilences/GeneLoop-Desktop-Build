# AgenticVBench 视频侧当前交接

- 更新：2026-11-10；已完成原主配对与预声明的一次B正常恢复，全部付费进程退出。新C真实调用/原清单交付及9段成片通过；原B主配对字段失败封存，修复成本次级分析两侧均过原门槛：B累计17请求/USD.01650680/325.85秒，对R8请求/USD.00640950/209.96秒，参考费低61.2%、请求少52.9%、执行耗时低35.6%。这是一个固定决策任务的暖库单例，不是冷启动净收益、稳定大库检索收益或递归SI；最终编码仍由模型组织。当前不扩样、不再启动模型任务。
- 分支 `codex/agentic-vbench-efficiency-20261109`，主线基点 `e2494b0d`；局部认证接线 `9889fde`。[草稿 PR #165](https://github.com/jingyio/GeneLoop/pull/165)未合并、未部署、未重启正式服务；最新推送/CI须读 PR。
- 已定位：最初19请求是未启用学习的预检；真实 cv2/shell 不能直接走原受限后端。随后 DeepSeek 两次 Task2复测在 HTTP502/EMPTY_RESPONSE 中断。不能据此说不存在视频复用抽象。
- 已接通：共享原生 execute/read_image及真实前后文件边界 → 原 collect_shell_call/advance_execution_learning → 原认证/Store；后继使用原 Capability dispatcher/Runtime交付。没有新增 Agent循环、挖掘器、ffmpeg后端或放开subprocess。
- 初次正常交付：Luna Task2 `task2-source-luna-v1-001`，10请求6929–6938、755.61秒，交付MP4和JSON，官方reward=0；格式被接受，4槽位选片均不匹配。edit.py参数化了选择，却混合subprocess渲染与清单计算，大视频中间件污染有界采集区。未人工改成品，不把失败来源登记为能力。
- 用户最新要求已实现到首次写码提示：上下文变量先集中到配置/输入区，程序开头读取为变量，后面稳定函数只读这些变量；镜头数不写死。确定性小文件处理与普通ffmpeg分开，媒体中间件放 `/workspace/work`。提示改善不能记作Motif收益，未来两侧须相同。
- `--continue-trial/--followup` 在原Harness新会话中继续同一开发题，复制工作文件并保存旧session证据，旧产物/边界/历史不动。钉住SDK无持久session恢复入口，v1-002曾already exists、0请求；2d91bc6已按实际接口修正。拒绝跨模型/跨题/后继续修，不把复修算独立样本。v1-003已在1000秒诊断后退出；18请求、1009.52秒、reward仍0。
- 研究根为私有 `.local/benchmarks/efficiency-si-agentic-vbench-luna-20261109-v1`；官方 `b2764ed4`，学习Runtime固定 `c2f332b`，另叠加 `a7c0a6d` 的模型接线/记账。学习器/编译器/Store/执行后端未改。主线不包含完整该研究学习入口，不宣称独立产品已交付。
- 模型：Kouri `gpt-6-luna`，原Harness pi-ai路由 `kouri-luna`；wire为 `reasoning_effort:none`、`max_completion_tokens:128000`、stream=true，无DeepSeek thinking。费用/请求null；墙钟1800秒；`--request-recovery`为原Harness normal 5次请求重试。正式默认不变。
- Luna连通性已真实通过：6921–6923共3请求、201.26秒，实际JPEG→execute→可见回答，response_models均gpt-6-luna。共享配置 `config/research-gpt-6-luna.json` 与 research_luna.harness_patch()必须配置已有llm-pi-ai，不能重复insert。
- 账本沿原 `.local/experiments/remotion-motivation-20261027-v1`，不清零。v1-001收尾快照6938请求/代理记账USD101.09234343，含历史/他侧未知预留；Task2本次参考价USD0.01166468，非Kouri实付，后续累计值须读现状。旧DeepSeek失败/未知费用完整保留。
- 连接曾短暂中断，随后恢复。用户现授权继续独立局部认证；来源重取完成后已释放付费窗口给Chart，之后独立认证须等待明确交回，不并发争用原Gate，不重启正式服务。
- 验证：预算/编译器等53项、模型与其他Gate15项、新续修归属/布局/预检9项通过；原生/Capability Node6项通过，真实Docker图像接线通过。main隔离副本43eeae5完整npm test为3259通过/28跳过/31失败（21旧发布库锁+10解析/OCR环境），Node未进入；本候选共享Gate触及旧发布库代码锁，合入/发布前需重新Execute认证，不改旧证书hash求绿。
- 当前实验根 `.local/benchmarks/efficiency-si-agentic-vbench-component-20261109-v1`，角色在 `component-roles.json`，配置到清单与官方视频任务分开。Task2局部来源 `task2-component-source-001` 已完成：5请求6986–6990、77.54秒、参考估费USD0.00219640；原程序/配置未变，独立检查通过。原学习器提取 Artifact1/Script0，局部准入true、整视频准入false。
- Task6三段新配置独立检查通过；绝对源码操作数起初被原学习器判outside workspace，新增逐SHA核验的场景路径投影后，原认证published1/rejected0、0新增模型。旧拒绝证据保留。C为 `cap_681acb4d9b6b69084766f1a1`，隔离Store在该研究根 `/store`，尚无质量/费用提升认证。
- 正常Task13冻结对照已完成：Reuse/Baseline各8请求，USD0.00600544/0.00292370，453.89/303.53秒，均交付视频/JSON、官方0分、C0。真实输入/工具/镜像/系统提示等一致。提示冲突修订后，同题开发复验9请求/USD0.00641298/326.46秒，仍0分/C0；角色在 `retest-roles.json` 明确已暴露开发复验，原后继学习拒绝不变。代码至 `1e7690d`。
- 原Runtime零模型诊断证明旧Reuse真实配置下C输出与成品JSON逐字节相同，本题完整4段计算适用；目录仅1候选，无排序证据。新复验自写末段覆盖尚未独立验为必要行为。未发生自主采用，不称清单进入C→ffmpeg交付链，视频旧分不改，Sequencing不扩样。
- 下一关键由绘图侧牵头公共参数学习修复：本场景仅接原提取/认证/Store，未接原parameter_learner与采用反馈。已交实际反例：源码支持省略manifest_name，但首例shape契约拒绝；普通Docker执行正确，旧C/证书保持不变。新公共修复及重新认证尚未集成，不并行修改同模块；不再重复同提示试跑。Gate已交回Chart。

## 当前继续点：Task14冻结对照

此节保留原冻结配对配置与历史过程；最新继续点见下一节，原Gate交接文字不代表当前所有权。

- 场景代码`19c8b54`，公共研究Runtime为`a073381`（原`c2f332b`学习链、公共参数学习修复、`ad1834a`真实任务参数证据绑定及`e50c7e7`提案转义兼容），外叠既有Luna传输适配；均未合入主线或发布。核心提交位于私有研究工作树`.local/video-value-argument-owner`，不是场景分支同一Git对象库。
- 新根`.local/benchmarks/efficiency-si-agentic-vbench-method-20261110-v1`。原Task2/Task6轨迹经原认证重建；原参数学习真实1请求7046、7.57秒、USD0.001295，明确`no_change`，未学出新算法。沿预案冻结重认证原程序，两个file/value入口是同一程序，不能算两个C。
- Task14在看题面/素材前按下一官方编号选定，角色见`method-roles.json`；9份素材与旧Task2/6/13零字节重合。900秒/侧，Luna/none/128000、不限费用及次数、原累计账本；两侧同代码/提示/工具/素材/镜像，Reuse冻结库和Baseline空库，均启用value入口。已冻结，不能在中途集成其他接口修复。
- Reuse `results/task14-reuse-pair-v2-001`：请求7047–7058，C成功1次，实际走文件入口。正常Agent只写当前`instance.json`，未重写清单算法；Runtime清单与最终JSON同SHA`50fee435…ba183`。视频成功编码，官方3槽位1匹配/1内容校验通过，reward0；选片仍是独立质量瓶颈。
- Task14 Baseline已按冻结条件完成，9请求7070–7078/USD0.00832075/236.13秒/C0/官方0匹配；Reuse费用观察上高77.1%，不是降本。无Oracle后置清单算术Reuse通过，Base手写终点不一致；不能视两侧0分为同质。审计`results/task14-paired-audit-002`核验同普通提示/输入/代码/真实schema，完整prompt仅追加目录不同。当前Gate已交回Chart的line31空库及既定judge窗口；等明确交回后先Sequencing13段Reuse900秒单侧，不串联付费。
- 实际视觉错误另有证据：旧Task13混尺寸联系表只有4/12非黑格；VFR输出使cv2时间寻帧偏离真实时刻，不能归因几何尺寸或接口丢图。新普通工具提示要求逐格归一/标注/时序检查、使用视频流时长及显式CFR；两侧共同采用，不能算Motif收益。旧所有失败原样保留。
- 公共Runtime `ad1834a`归档回归：Python3443通过/30失败/23跳过；独立Node1712通过/1失败/8跳过。存在旧发布库锁与PDF/OCR环境失败，未全绿；deadline失败单独复核通过。最终`a073381`额外包含提案转义兼容，不冒称前次全量是最终重跑。新绑定定向Linux18通过/1平台跳过，真实旧失败重放通过，不替代全量或质量验收。
- 原计划Sequencing task2（7段）、task1（13段）完整片段接口已零模型核验兼容，角色在`sequencing-roles.json`。官方ZIP SHA验证后制备材料层，全部1920×1080、分别25/30fps；直接HF失败和mirror成功均保留。预检`results/sequencing-interface-preflight-001`；真实配对沿同一冻结C/a073381，不读Oracle、不强制C、不用测试题修库。不要继续把选片失败统称为没学出Motif。
- 7段配对已完成：Reuse13请求7089–7101/USD0.01157220/683.60秒/C0；空库9请求7111–7119/900秒超时，退出评分合计940.34秒/C0，后置原账本USD0.00629177。原费用null摘要保留，7119晚结算已知，不手改账本；官方位置2/7对1/7，内容校验均7/7，reward.06944444对0。两侧均未采用、质量不同，不作效率收益。原C用真实7段配置零模型重放、仅诊断副本替换JSON后官方指标完全相同，排除本例必须手调末端的说法；这不算正常采用。证据`sequencing-task2-paired-audit-001`及`sequencing-task2-applicability-001`。
- 后续方向已确认，但先结束原13段配对：在原学习题的正常开发经历中，让Agent自行把同一当前JSON所需的manifest、有序concat/必要argv或导出计划作为纯数据工件实际产出并使用；原提取/学习/认证只覆盖真实数据生成，普通execute仍执行媒体步骤。不手写目标C、不放宽subprocess、不为这次benchmark切Source；新程序独立认证后再用新未见后继检验，不改现有库或回灌Seq题。当前C边界只省累计，其余拼接/编码/探测仍由模型反复组织，详见实验报告边界诊断。

真实入口与复现配置见[场景README](../../scenarios/agentic_vbench/README.md)，历史失败、原始响应诊断和费用见[同一实验记录](../experiments/agentic-vbench-efficiency-20261109.md)。服务器连接恢复后先加载项目 `.local/remote-env.sh`。

## 当前继续点：正常计划程序与独立认证

- 原13段配对已实际结束：Reuse8请求/USD0.00517916/911.38秒，空库9请求/USD0.01603627/909.31秒；均900秒超时/C0/官方0。Reuse最终目录空，空库仅MP4无JSON，不能由同为0称质量等价。Reuse主要时间用于CPU重编码，非模型慢。
- 零模型同素材/同实际Actor顺序反事实：普通stream copy 3.45秒但仅7/13内容校验；只在concat加入测量视频时长后2.60秒、13/13校验通过。原C、源顺序、媒体命令不变。此为研究者诊断，非正常完成/学习/采用，不能计Motif收益。未来两侧共享实际codec/header与视频时钟指导。
- 新根`.local/benchmarks/efficiency-si-agentic-vbench-plan-20261110-v1`。Runtime继续钉住`a073381`及既有Luna适配；未集成Chart后续kwargs候选。源场景`scene-program-v1`、认证冻结场景`scene-plan-v2`；旧原配对`method.../scene`不覆盖。
- 同一正常Task2开发经历：source-001、replay-002、feedback-003合计28请求/USD0.02237788/695.78秒，全部计开发恢复成本。前两次原Artifact0，分别为复合命令与fresh目录不在outputs域；第二次还将媒体拷入小文件树。旧结果保留。原native零模型布局预检最终Artifact1、完整前后边界、原源码字节未改、Store写0；启动器两次诊断失败也保留。
- feedback-003由原Actor真实修改源码并执行，原提取Artifact1。程序`artifact_b5945b9982bb51dabff3d824`/SHA`08f511b3...bc545a`：`INSTANCE_JSON MEDIA_RECORDS_JSON OUTPUT_DIR`，当前实例只含IDs/输出选项，直接读取只读无损测量数组；输出manifest+带每段视频时长的concat。仍不执行媒体、不生成完整编码argv，不称完整媒体能力。
- 独立检查`results/task2-plan-quality-004/qualification.json`绑定真实call-8产物及call-14实际ffmpeg消费，4段各3采样SSIM≥.9976，829/829帧完整解码，24fps视频34.541667秒与计划终点一致。Actor真实交付在`output/task2-normal-plan-source-replay-003`；根级旧文件/原result的pending不改，不称官方选片或音频质量通过。`task2-plan-qualified-003`仅为独立配置项目准入。
- `source-plan-freeze-001.json`在Task6前固定源程序、双JSON接口、独立检查器及新角色；Task6普通Agent选择三份当前素材、源码不改，实际渲染并交付，再走相同独立检查与原`advance_execution_learning`认证/Store。当前运行`task6-normal-plan-certification-001`，Luna/none/128000，900秒、费用/次数null、原累计账本。Gate按对方线程明确交回/实际进程退出逐段交接，不凭锁空闲抢跑。
- 新能力若通过，保留旧C并冻结一代，Assembly15真空库先、再复用；Sequencing3复用先、再真空库。两侧同v5数组/普通媒体策略/文件接口，C可选，原官方质量和实际完整成本照常报告；不得用这两题修库。29项场景Python检查通过，既有全量/CI失败见上文；未合并、未部署。

### Task6恢复后的真实状态

- 首次Task6有原有效Artifact1，但普通CFR多2帧，独立检查失败；恢复002有实际媒体修复，却把Python调用合入shell，原提取Artifact0。没有改原parser、重造producer或把恢复算独立样本。
- `task6-plan-quality-associated-003`关联同一canonical Task6首次真实producer与恢复的实际media：任务/题面/素材/测量/配置/源程序/manifest/concat逐SHA一致；真实消费边界完整，生成的帧检查worker与首次冻结文件逐字节相同。实际259帧/24fps、3/3采样内容与完整时钟通过。原失败与原pending结果不改，新增同一经历的恢复质量证据；原认证仍使用首次独立输入及其Artifact见证。
- Task6含恢复12请求/USD.00962498/151.60秒；源开发加认证合计40请求/USD.03200286/847.38秒，不含更早开发/认证、诊断CPU和维护人工。后几项须保留，不能将此小计当完整净收益。
- 原`advance_execution_learning`认证`published1/rejected0/model0`，新文件C`cap_c00a00710fd40c01fd9a752e`，仍为源08f511b3纯数据程序，不接管媒体PTS修复、编码或语义选片。保留旧`cap_0ed...`。
- `successor-generation-freeze-001.json` SHA`4d664de6...5e3a62`：增强库digest`089ba3ea...b1bfc0`，真空库`5984c144...c6238d`，同`scene-plan-v3`/v6普通PTS指导/文件接口。新后继镜像和ZIP/版本SHA在`inputs/successor-image-preparation.json`。Assembly15 `task15-baseline-pair-v2-001`已启动900秒单侧；C可选、两侧不变、后继禁止学习。32项场景检查通过；PR165草稿，未合并、部署。

- 最新程序已由正常Agent拆为JSON输入/纯manifest计算/外部ffmpeg，原Artifact AST静态准入通过，生成JSON确实进入最终交付；仍非认证C。实际提取v1-003为0/0，12项不完整边界，且整体质量0。97ef631修复续修复制旧视频污染小程序区；真实Docker零模型复测新边界before/after均完整，8个旧输出归档哈希完全一致、原件不变。历史空目录也保留，不能伪造fresh-output。
- 完整视频Luna开发题：28付费请求、1765.13秒；v1-003的15次已知参考价USD0.03019901，3次502（6955/6957/6958）未知预留USD0.455242。Task6本次9请求6999–7007、306.47秒，8次已知USD0.00561403、7002 usage矛盾未知预留USD0.0659239；收尾累计USD101.75397095，含历史及他侧用量，应读现状。15项局部/路径/续修/布局检查通过；18c93a0 Ubuntu CI3272通过/21失败/30跳过，旧库代码锁阻断仍在，未合并/部署。
- 当前局部来源/认证/三次视频运行小计39请求，38次已知USD0.02315255，另7002未知预留USD0.0659239；历史/其他线程不纳入此小计但累计账本保留。自有最后收尾7042/累计代理记账USD101.77228817；新运行继续原账本，不重置。原始证据在该研究根 `/results`，本地必要摘要在 `.local/debug/agentic-vbench-component-20261109-v1`。

## 当前继续点：固定代负结果与源码缺省修复

原 `successor-generation-freeze-001` 四侧全部正常退出，除目录外共用条件核对通过，冻结中途未集成公共修复。

| 原官方后继 | 空库 | Reuse | 实际新C采用 |
| --- | --- | --- | --- |
| Assembly15 | 17请求 / USD.02027324 / 367.42秒；1/3匹配 | 14请求 / USD.01564954 / 257.80秒；0/3匹配 | 尝试1、失败1 |
| Sequencing3 | 18请求 / USD.02317115 / 480.19秒；4/10匹配，reward .05777778 | 12请求 / USD.00948587 / 382.01秒；2/10匹配，reward .02488889 | 尝试1、失败1 |

Assembly两侧reward均0，不能据同为0称同质量；Sequencing内容校验均10/10，排序仍不同。两项原生C失败均在有效输入缺省被精确键契约拒绝后走普通回退，真实失败回执保留。四侧61请求/USD.06857980（官方参考估费，不是账单）；不含之前开发/认证、诊断CPU及人工。只读审计为 `task15-paired-audit-003`、`sequencing-task3-paired-audit-001` 与两项 `all-claimed-media-audit-001`。

独立公共owner `.local/video-value-argument-owner` 已提交 `2f8586e`，分支 `codex/video-optional-json-contracts-20261110`（基线 `7a14ebc` 含Chart已交接字段分类）。原编译器从真实 `.get` JSON默认值生成有版本的缺项声明，原认证执行逐项/联合缺省，Python与原TS匹配共享声明；未知/必需项、来源、模块和输出授权守卫不放开。普通卡复用既有深层字段类型与实际原生契约。此公共提交不在本场景PR165的代码树内，不能把Draft场景PR单独写成已集成。

原正常Task2/Task6轨迹重取并沿原 `advance_execution_learning` 认证：新 `artifact_931f6f78bb58665ecec23674` / `cap_81447ad6c10b207e28f9b7b7`，源码仍08f511b3，发布1/拒绝0/模型0，单独 `store-optional-plan-candidate-v1`，旧库证书不改。`optional-plan-zero-model-adoption-002` 两次实际capability_call、导出读回、普通ffmpeg、原冻结媒体检查通过（829/259帧），未知字段和缺必需配置仍拒绝；研究者指定调用，不能称自然采用或效率收益。公共定向Linux160Python/23Node通过，1平台跳过；新增缺证明加载拒绝24项通过，全量旧锁结果单列在公共提交诊断记录。

下一项候选计划只做新的固定决策后剪辑执行阶段对照：Assembly16公共素材按预先确定的文件名数值升序给定全部片段，不取Oracle/人工正确答案，不冒充官方选片/排序通过。先冻结具体输入、同源runtime、新C/空库、共同提示/工具及原质量门槛，再由公共owner审阅恢复一对真实模型运行；当前未启动。原Task15/Sequencing3不重跑成未见证据，不并发占用Gate，不部署。

## 本轮收尾：新固定决策执行阶段（仅一对）

- 场景 `4096b41` / 公共源码默认修复 `2f8586e`（后续`87f4354`只补检查记录）。`execution-generation-freeze-001.json` SHA `6e4b06ee0881ba6b3336b0dbc8917eb1bd4bf630071f3323019f8bad1d6ac9f3` 固定Assembly16公共新素材1–9数值升序请求；与源Task2/6素材零字节重合，顺序不取Oracle/人工答案。只评固定决策后执行，未评官方选片/排序。
- 原两臂都实际exit0，无修补重跑。Baseline 7321–7327、7请求/USD.01037170/181.96秒/C0；Reuse 7328–7335、8请求/USD.00640950/209.96秒/C1成功。仅单当前C对空库，不是大库检索实验。
- Reuse最终JSON SHA `b3ff6798...5813` 与原native收据/导出逐字节一致；新源程序仍08f511b3。固定顺序/完整视频时长/连续区间通过，9段各3采样SSIM≥.9965，464/464帧、24fps、19.333333秒对计划19.333008秒通过。Baseline manifest用 `start/end` 缺要求的 `output`，原数据检查失败、原帧worker在缺字段处退出；不是视频内容已被判坏，也不将重命名后的版本计作原通过。
- R concat确实用于初稿尝试，最终MP4由Actor另外构造filter_complex生成；只有清单/测量读取与时间线计算的最终复用证据，不宣称完整媒体/编码流程复用。模型仍反复修复PTS/编码。
- 观察参考费降38.2%，请求增1、耗时增15.4%；prompt/cache-hit为B94269/2480、R83797/34030。按同冻结价将全部prompt按miss作诊断重估，B.01059490、R.00947220（低10.6%），不是实际账单或新的对照。未通过等质门槛，不从这些数字宣称等质效率SI。
- 当前两臂15请求/USD.01678120；加本C原source/cert为55请求/USD.04878406，再加上一冻结代四侧为116请求/USD.11736386。更早失败、未知预留、诊断CPU与维护仍另有原账本/日志，不将该小计当完整净收益。原结果/失败/标准不改，下一阶段须先审阅，不扩样。
- 只读审计 `results/task16-execution-paired-audit-002`；001误把四参plan checker当三参调用，原TypeError保留。002沿已有冻结manifest checker，以原固定IDs+共享测量生成独立期望数值，原帧worker字节和阈值不改。未额外要求空库生成C专属concat格式；没有归一/改写Baseline成品。必要证据及Reuse成片按需同步本机私有目录。场景32项通过；完整公共工程回归的既有失败见公共分支诊断记录。PR165仍Draft，未合并/部署。

### 已完成的次级修复成本分析（原主评分不变）

在原主配对/002结果完全封存后，追加同一失败臂至多一次正常恢复：仅空库B接收原missing output检查反馈及原规范，R原合格交付/成本保持不动。不是新未见任务、重跑主配对或人工修文件；B原7请求/USD.01037170/181.959722秒必须累计。沿原 `--continue-trial/--followup`，新增显式 `--baseline-recovery-report` 仅允许同baseline、固定执行scope/goal/task/model/runtime、原空库snapshot和同素材测量；旧development保护不变、sealed角色继续禁止学习。恢复最多用原900秒余额718.040278秒，失败也停止，不无穷续修。场景40项通过；新阶段运行前另冻结反馈/代码/原失败证据及费用规则，已在绘图35实际退出并明确交回窗口后执行，结果如下。

- 恢复条件先封存于 `repair-inclusive-freeze-001.json`（SHA92989585…848f3b），真实preview通过，未给R数据/未手修B文件。场景提交91ed04f；仅原CLI显式恢复，不增加Runner/学习路由。恢复7356–7365共10请求/USD.00613510/143.88543秒，C0，实际exit0；未超过718.040278秒余额，不再给下一阶段。
- B恢复后清单及9段原帧采样/完整464帧/时钟通过，实际fps24.05183585；R原fps24、原产物/费用完全不改。双方按同一个冻结门槛合格，不声称像素/时钟完全相同或独立盲评等价。B原字段错误、主配对/002和全部旧费用仍封存。
- 次级accepted-delivery成本：B17请求/USD.01650680/325.84515秒，R8请求/USD.00640950/209.95967秒；R少9请求、参考费低61.2%、实际执行时间低35.6%。B正常恢复发生于另一窗口后，不把等待协调的墙钟当模型执行时间；原日期/时间/阶段均可定位。按同冻结价把prompt按miss诊断重估，B.02300840对R.00947220，低58.8%，不是账单或新实验。
- 这25次任务请求参考费合计USD.02291630；加此C源开发/认证为65请求/USD.05491916，再加上一代四侧为126请求/USD.12349896；更早历史/未知和CPU/人工仍单列。学习40请求/USD.03200286尚未由这一任务摊平，不称完整冷启动净收益。
- 结果 `results/task16-repair-inclusive-audit-001`，主配对不重评分。已释放付费窗口，仅同步证据、文档和Draft PR；没有下一模型任务、合并或部署。
