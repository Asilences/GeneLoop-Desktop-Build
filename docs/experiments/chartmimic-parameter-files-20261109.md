# ChartMimic 参数文件与程序复用续调

用户在首轮三题诊断后明确要求：生成阶段减少实例数据过度内联，继续调试到原流程能学到并复用程序。首轮结果与20请求、未知费用保持在[原记录](chartmimic-efficiency-si-20261109.md)，不改写为成功。

## 固定的方法与新条件

正常 Agent 仍看官方原图、自行理解当前数据与视觉语义、编写并执行自己的算法。新增的只是代码组织约定：当前数值、文字、样式写入模型自行设计的 JSON；程序使用显式当前文件及全新输出目录参数，模块文档说明接口，导出可重复工件。没有手写 renderer、目标 Motif、数据答案或绘图 DAG。

普通程序按原 `collect_shell_call()` / `program_from_witness()` 提取，交原 `advance_execution_learning(..., backend='artifact_motif')`、原独立 namespace 认证与 `CapabilityMaterials`。若认证成立才冻结库；后继用原 `runArtifactCapability()` 执行，场景只冻结当前文件/授权和展示目录。原只读 Script 不取得写权限，原 Artifact 检查与代码锁不放宽。

新的 `roles-parameter-files-v2.json` 冻结学习 `line_1/5/10`、独立认证 `line_11`、后继 `line_15/14/13`。先取得一个源程序并在独立输入认证，再决定是否继续其余学习任务；后继不用于修库。`line_15` 检查数据点数和样式变化；后两项提供注释/多子图等边界，是否采用由正常 Agent 判断。此选择在新候选与后继结果产生前完成，仅参考官方允许的输入图，不读取后继参考代码。

## 实验身份与保留的失败

- `efficiency-si-chartmimic-interface-20261109-v2`：参数文件约定，无系统级路线强制。首源任务603.49秒取消，14请求6846–6859，仍只做像素测量，没有 JSON/程序/图；13次已知代理USD0.0289167，末次6859费用未知。原Harness不支持session/cancel时按原兼容边界关闭runtime，原取消与费用证据保留。没有候选，不进入认证。
- `efficiency-si-chartmimic-interface-20261109-v3`：在相同视觉质量要求下追加“先完整初稿，再测量/修订”。实际首请求已核对包含参数分离与该顺序约定，`thinking.type=disabled`。源 `line_1` 完成，587.38秒、22请求6862–6883，交付模型自行编写的程序、JSON、PNG/PDF；原提取器得到完整 Artifact 1、Script片段2。Script片段不计完整绘图复用。独立认证 `line_11` 的输入绑定仍在600秒内只做像素测量，603.57秒关闭，18请求，无JSON，未运行认证。
- `efficiency-si-chartmimic-interface-20261109-v4`：把先交付完整JSON的次序提升到本任务系统persona，仍保留原视觉要求；同一 `line_11` 重试75.83秒、2请求6908–6909，读图后原Harness报 `EMPTY_RESPONSE`，无JSON。代理费USD0.0027201；这是失败重试，不是新独立任务。
- 两轮分别保存新目录、prompt/effective/source-snapshot，原任务与旧账本不覆盖、不清零。当前仍请求Kouri Flash/off/393216，费用/请求无限，单题600秒诊断上限。请求的off与供应商实际返回的reasoning统计分开报告；不凭该差异自行更换共享模式或追改历史估费。

共享原生工具采集已由视频会话从本场景原实现无行为变化抽出：原提交 `f0a9295`，本分支cherry-pick为 `f83b5b3`，公共入口 `src/adapters/research_native_tools.ts`；Chart保留薄兼容导出。独立run复制自包含公共源进入source-snapshot，避免相对导入失效。双方沿原账本锁串行付费，零模型认证/检查可各自在独立目录推进。

## 薄适配位置与验证边界

`learn.py` 仅将原提取候选、真实输入见证和独立绑定任务传给旧编译/认证/材料池；`capability_tools.ts` 仅为正常 Agent 展示冻结目录并把其当前 JSON/输出选择交给旧 Runtime。调用成功后仍须核对新输入、原程序SHA、输出实际参与交付、是否又生成了同一绘图算法，以及独立质量和完整费用；认证/激活/调用成功均不单独作为效率结论。

参数化程序的官方评分只增加宿主 argv 与求解器自己产生的当前 JSON 绑定，原程序字节另存，官方四项评分逻辑不改。参考源码与评价资料始终在独立目录；原GPT4高层评审仍待配置，不能用较高低层分数代替完整质量。

后续结果在本记录追加。任何配置、源码、认证或冻结库变化都用新身份；冻结测试用于修库后不得仍报告为未见测试。

## 原程序回放与已观察边界

完整候选 `artifact_3ce772ed7855b0e3a28a4f5d` 的源码SHA256为 `035e1cc62cfdfbb2fbb29c4f51a1ebd0d629e6976d678193244390341b70b286`。接口是模型自己的模块文档和真实源JSON字段/类型投影，不携带源图数值。程序支持单坐标轴、动态曲线/点数、数值/标签/颜色/标记/网格/图例参数；没有标题、逐曲线线型、注释或多子图参数。是否适合新图仍由当前Agent判断，不能称通用ChartMimic解法。

零模型源回放发现两个适配环境错误：旧采集边界缺原Artifact运行所需空 `command-tmp`，以及嵌套venv解释器指向沙箱不可见的中间路径。历史快照不回写；执行副本增加空临时目录并记录原路径，新环境直接由实际base解释器创建。原沙箱、挂载守卫和认证比较标准未改。公共边界补空temp与定向测试采用视频会话 `62182ed` 的等价改动。

v4 `source-replay-002/result.json`：原 `runArtifactProgram()` 两个新namespace均成功，PNG `b67486fb74d2a041fd5e79cadb4a974eaf7f34c372568283b31ed9a6478de5c3`、PDF `536d9cd8c28b749657f2716495ae02c104ffcb10f465cc054d131ce65418dc5a`，与真实call-13历史工件逐字节相等。这里只证明同源可重放和确定性，没有授予证书或C。

最终源交付的官方低层F1：Text 0.521739、ChartType 1、Color 1、Layout 0。原Layout针对其支持的subplot introspection计数，当前程序使用 `add_axes` 并关闭figure；保留原0分，不修改评分器。人工看图发现图例顶部/右侧拥挤裁切，尚不称完整质量通过。原GPT4高层judge仍pending。

本地完整回归（共享原生工具抽取后、后续少量场景IO修正前）：Python 3045 passed /272 skipped，Node 1688 passed /25 skipped；边界空temp补丁后4项原生工具定向测试通过。没有因此声称模型行为或成本收益成立。

## Luna迁移、实际绑定与原认证拒绝

用户明确要求用Kouri GPT-6 Luna继续。`efficiency-si-chartmimic-luna-20261109-v1` 使用独立runtime：原干净c2f来源加共享 `a7c0a6d`（本分支 `e01af87`）的研究模型/额度/缓存记账覆盖，1165个源文件SHA清单；旧runtime与旧失败不覆盖。官方参数来源为[GPT-6 Luna模型页](https://developers.openai.com/api/docs/models/gpt-6-luna)。实际请求 `gpt-6-luna`、`reasoning_effort=none`、`max_completion_tokens=128000`、`stream=true`，原Harness公开pi-ai路由，不传DeepSeek thinking。账本沿原、额度不限；费用采用官方参考代理价格，非Kouri实付。

最小原Harness图像→execute→可见回答检查由视频会话完成，绘图侧直接复用结果。真实 `certification-line11-001` 用完整观察schema及先JSON约定，266.39秒完成，6924–6928共5请求；6925 HTTP502、用量未知，原Harness自动重试后完成。JSON SHA `b3782d125a9f02a2d9dbf6b22f82ba85efcfe71c0de9cc0ed77ce5e9e942e57c`，没有模型像素诊断循环，没有手填当前参数。绑定完成不表示图件已渲染或质量通过。

原 `advance_execution_learning()` / Artifact认证的 `certify-line1-line11-001` 返回 `no_qualified_programs`；原报告 `task_specific_content_not_parameterized`。只读定位原源/新输入发现唯一触发selector为 `black`：真实程序的 `labelcolor="black"` 仍硬编码，而正常Agent的新JSON用十六进制 `#000000`。不放宽原保守guard，也不改新JSON来凑认证。下一轮恢复同一学习任务，把原真实草稿和原拒绝报告交给正常Agent，要求把剩余实例属性在程序开头集中绑定并由JSON驱动；修订后必须实际出图，再提取真实新程序。已有line11参数只有在新程序接口确实兼容时才可用于原认证。

`efficiency-si-chartmimic-luna-20261109-v2` 为上述恢复准备，学习题身份仍是line1，不计新独立样本。新生成约定适用于后继Baseline与GeneLoop两侧；提示/模型切换本身不算Motif收益。原始程序来自DeepSeek，若由Luna恢复则保留混合来源链，不报为同模型从零学习证据。

共享Luna改动后完整npm test在Python阶段3025 passed/21 failed/272 skipped，失败均旧发布库 `certified runtime code changed`；Node未进入。既有发布库锁包括公共预算/模型文件，因此研究覆盖需在正式发布前重新Execute认证；不更改旧证书hash或删除测试。定向输入隔离5项、原生工具4项、记账12项通过；新增空目录基线API拒绝虚构capability，未取得执行权限。此处仍无C、无Store注册、无后继收益。

随后独立Node全量为1679 passed/6 failed/25 skipped：3项涉及旧发布库code lock，另外3项普通路由/附件/goal的超时或准备失败均在定向重跑通过（2+1），不追改原全量失败记录。

用户又明确要求“上下文相关变量都定义在一开始”，已同步生成约定：程序/入口函数开头集中读取当前输入和绑定数据、文字、样式、布局、路径，后面只引用绑定变量/上下文字段；实例值仍从当前JSON/argv传入，不能只移动成源码顶部常量。

v2 `learning-line1-recovery-001` 在下一共享窗口启动600秒Luna恢复。运行中V100新SSH连接连续被关闭，随后原运行连接也以255被远端关闭。一次短暂等待后只读重连确认TCP建立、但在SSH密钥交换前被关闭（`kex_exchange_identification`）；尚未进入认证或项目执行。当前无法核对远端Python、结果、账本和Gate，不报恢复成功或模型失败，不重启服务、不重复启动任务。待恢复原入口或提供同机备用入口后，先核对原进程与已有result，再续调；已向用户请求该必要外部信息。

## 原认证通过与冻结C

用户要求重测后连接恢复，先核验原v2任务与锁：该任务实际已completed，6939–6945共7请求、266.88秒、官方参考代理USD0.00543529，原进程无、Gate free。程序改为入口context绑定，但遗漏原 `labelcolor="black"`；原认证仍拒绝，没有将SSH断线当作模型失败或重跑依据。

v3 `learning-line1-recovery-002` 继续同一学习题，反馈为原报告/源码SHA引用及AST精确行号，不含手写程序补丁或认证图数据。正常Agent自行修成读取context，真实独立execute成功并read_image；原JSON未变，PNG/PDF与此前交付逐字节一致。6946–6952共7请求、148.12秒，6947为502且用量未知；保留原重试/失败，未计新独立任务。

原提取/认证/Store链路已成立：Artifact程序 `artifact_00f7440b0c38f074d6797489`，源码SHA `8c512dbf6382ca22c5996668afa437f7178a9805ea348985e38b6166f65930ac`；原报告published1/rejected0，原 `advance_execution_learning()` 返回registered，原CapabilityMaterials登记，owner `chartmimic-luna-v3`。源line1与认证line11各在两个全新namespace执行；源PNG/PDF复现真实历史工件，新输入输出不同且确定。`semantic_quality_accepted=false`、`quality_cost_promoted=false` 保持原值。

冻结C SHA `fabec688437179f6d4571c0fbbd3e01c1233f6bc9ea93cfb7a4c2e40f0c68540`，私有 `frozen-C/manifest.json` 保存原注册、共享目录、程序源码和混合模型来源。之后认证输入上的强制零模型 `capability-preflight-001` 通过原 `runArtifactCapability()` 并验证导出源码一致；这是接线检查，不是自主选择或独立后继成功。

后继配对计划 `efficiency-si-chartmimic-luna-pair-20261109-v1/pair-plan.json` 在两侧结果前冻结：line15，先GeneLoop后Baseline，每侧600秒、同Luna/none/128000/4工具schema，冻结C目录对空目录，学习关闭。排序不是随机化；保留缓存和失败，原四项低层评分不改，GPT4高层judge仍pending。此时尚未运行后继，不能提前报质量等价或效率收益。

## 首次冻结后继：正常Agent未采用C

line15两侧均completed并交付：GeneLoop 8请求6971–6978、289.88秒、代理USD0.00638273；Baseline 7请求、254.03秒。GeneLoop主动调用capability_list，但没有capability_call，重新生成plot.py（SHA `2a527ad2d4ef60123db9d54aae8a2d0b20eb95cb2c0edc9b251eec4a2a865d92`）；`reuse_output_present=false`。不能把新JSON沿用旧接口、查看目录或新绘图程序当作原Runtime复用。

官方低层F1分别为：Text两侧0.279070、ChartType两侧1、Color GeneLoop0.988815/Baseline0.982956、Layout两侧0。原高层judge仍pending，质量未接受。该结果保留为未采用/未证明收益，不因后续修复改写。

存在两项真实问题：新建程序的固定python调用约定与可选复用路由混在同一提示；此外line15需要水平网格，而冻结C1的 `grid` 固定双向。既有学习line10又需要独立刻度标签，C1未开放；line5需要虚线，C1也未开放。没有证据可以把不采用仅归因提示，不能强制不适用的C。

按原计划“任务选择可自主调整、不能改冻结结果”的边界，另外预先固定了只读原图审查16–30的顺序、真实C1适用条件及首个合格即停止规则（私有selection-plan SHA `2c4cdf4d096463d343672f838d8781d5736bb2b7436e6b9eaeba4b39d2492902`）。15张均有当前C1未覆盖的格式、轴、标题、线型、子图、注释或带状要求；无合格任务，没有新增模型试跑、没有扩大查找范围、没有读取参考代码或评分后换题。说明当前整图程序参数边界过窄。

下一轮回到原定learning line5（不是新增学习任务），新实验 `efficiency-si-chartmimic-native-config-20261109-v1`。生成规则v6要求顶部集中context/configuration中的命名参数映射，并将其交给固定的普通库API；代码保持静态调用结构，JSON只能是数据，禁止Python表达式、动态方法名列表或通用JSON执行器。接口和绘图算法仍由正常Agent从原图自行设计/执行，不提供手写renderer、DAG或实例数值。C1与所有既有冻结结果不改。复用/新建分支分别说明；后续真实新评估须用新冻结输入，已用于诊断的line15不得再称未见。

### line5 已完成程序与真实提取阻断

`learning-line5-001` 已正常完成：6991–6998共8次请求、229.22秒，已知代理估费USD0.00721457，供应商实付未知。源码SHA `c4701a192e9a16266f6a80e6b3dd14d65889b27abca9214253b240b00a964e23`，JSON SHA `5fbfd37df157bd1a02d832e9d7247b3ae86d30c62bd4212c0ea3039a5961271d`。Agent自行生成 `datasets` 与 `context`；figure/axes/plot/labels/typography/grid/legend/save在入口读取，静态Matplotlib API接收当前配置。可复用结构已存在，不能据整图C1不匹配推断没有复用机会。

原提取结果Artifact0、Script2。最后一个成功shell调用先用Python heredoc修改JSON，再运行绘图；原 `collect_shell_call` 的 `_invoked_heredoc_prefix` 只保留首个执行段，它读写同一JSON，触发 `artifact_output_read_before_write`。外层调用没有第二段开始前的原生快照，不能用调用后状态伪造绘图的调用前证据。精确源码的原Artifact admission通过；诊断binder因ARGV文件操作数非字面量而拒绝，但该诊断不能代替原生独立调用。最小恢复是正常Agent继续同题、保留现成程序/JSON并真实独立执行，不另建提取器。

零模型 `source-replay-diagnostic-001` 原样运行实际源码两次，PNG均为 `13812bc1de599f3c01489e07516345f11c769b42fb9dd59d4f098b5a83e7ed19`，PDF哈希不同且 `CreationDate` 不同。已准备真实证据反馈，交由原Agent修正输出确定性；尚未启动恢复，不把诊断当学习或独立认证。官方原四项评分：text F1=0.3571428571、chart_type=1、color=1、layout=0；原高层judge仍pending，完整质量未评审。

边界核对：原Artifact后端可认证并执行完整静态Python文件、不同JSON输入及文件输出，适合本次稳定执行程序；其Runtime还会导出原样 `geneloop_reused_program.py`。C1中的build_axes/draw_series/add_legend确有稳定片段，但现有证书覆盖完整CLI，不能把普通Python导入调用写成已独立认证的子能力。原Script切片为只读JSON计算，不能传递活的Matplotlib Figure；Source后端当前视频输出契约也不能直接当绘图函数接口。本轮优先保留line5已有完整执行结构，把当前判断作为输入；控制流/API变化继续普通回退或组合，不新增绘图框架或手写子Motif。

接口展示同步直接投影原Artifact input contract；不再对深层kwargs对象凭首例附加递归 `additionalProperties=false`。这是展示与原键/类型契约的一致性修正，原shape matcher、源准入、namespace、认证和Runtime未改。此时新line5任务尚未运行，未声称新C或复用收益。


## 2026-11-10：原参数学习器、累积库与真实后继

line5同题恢复已实际完成（7016–7022，7请求、73.43秒、代理USD0.00242678）：正常Agent将PDF时间戳设为确定值并补独立绘图调用，未手写修复。原提取得到完整Artifact 1；line11由正常Agent绑定新JSON（7023–7025，3请求、64.38秒、USD0.00054832），原独立认证注册C2 `artifact_3356e62abb26898033b20d20`，library SHA `6b3047864f324a9f102c93ffce0212a9180684c3c5deb4d1a6ad0509610c78e0`。源码SHA `11799d9429b871cd38fcd38000b30f1c93444df388205199dfaf43f6915fa696`；当前datasets/context在入口绑定，固定Matplotlib API接受当前kwargs。认证范围仍是源等价及换输入确定性，不能等同完整绘图质量。

原声明式参数学习并未绕过：三次真实提案7043/7044/7045共3请求、代理USD0.00319752。第一次只把技术比较词same另立参数，没有解决固定labelcolor；第二次no_change；第三次正常模型自主选择实际AST位置E181:19，将labelcolor绑定原JSON的`/labels/color`，并给出合法红色probe与多曲线描述。第三次回复外包单个`<escape>`，原严格JSON解析拒绝。修复只剥离这一完整外壳，仍拒绝额外文本、重复键和非有限数；重放真实7045不再请求模型，不另记学习任务/费用。

对应原方法修复在独立c2f工作树分支`codex/artifact-parameter-learning-20261110`：`dd53754/f4f5bac/17bd368/e50c7e7`。保留未选择的JSON字符串；保护协议比较词；仅对真实见证、值精确相同的现有输入字段开放显式API字符串keyword绑定，由模型决定语义归属并选择不同合法probe。没有手填目标绑定或目标Motif。使用原编译、原沙箱、原认证及Store，C3在真实独立line11 JSON注册。C2既有有效证书直接准入原Store，不为展示累积库重跑认证。

C2+C3的原材料目录SHA `9696cf85d27b8b23d9d3a7c0feb61ad88c80f70c5ed0f50f0ee9bd2b2f79920b`，含两个完整程序、两个文件输入root及各自原library refs。薄适配现在消费原Store的learned description/input roles/parameter interface，不再丢弃学习描述而恢复旧four-series叙述。新配置只冻结原库及当前输入/授权，未新建Registry、IR或执行器。

可选值入口沿原`buildArtifactValueCapabilities`/`runScriptCapability`，是同程序的输入视图，不算新Motif。共享`ad1834a`（本工作树`eebee00`）把真实已授权当前参数作为依赖，保留变更/撤回检查；`000f2e3`导出原样当前JSON侧车并核验复用源码。源码在原文件形式中本来已经交付，首轮重复导出引发EEXIST，已去重并保留失败。Linux原Runtime最终18通过/1跳过，未削弱守卫。参数文件简化`5a4110c`不再为空参数集附加空JSON：重放7045的受控源认证registered，但独立line11首轮再次认证报告historical_output_not_reproduced；核对发现继承通用SSS Python的MPL3.10.7/NumPy2.2.6。固定原render-env-direct的MPL3.8.4/NumPy1.26.1后，独立复验002 published1/rejected0并registered，library SHA `0cf88555b3a4bbc131ee6ccd584d370e8c135c5ee73d43e270d80ee79891c8fc`，新增模型请求0。原拒绝保留，源码/JSON/比较标准未改。当前配对仍继续旧C2+C3，不静默换库；新版本尚无正常后继采用/质量收益证据。

### line14：完整配对、未复用且没有效率收益

`efficiency-si-chartmimic-learned-pair-20261110-v2`计划SHA `90071909c84323207feb14974416c39c7aed0f33675a13a799b28d82bc921d74`，首请求前冻结原C2+C3对空库、同Luna/none/128000、相同4工具schema、各600秒、学习关闭。line14是原预选后继，先前合法PNG已用于适用性分析但从未求解；明确不称盲选。v1无模型预览发现capability revision比较字段错误，保留失败，新v2通过宿主和真实工具目录预览后才付费。

| 项目 | 带库侧 | 空库Baseline |
| --- | --- | --- |
| 请求 | 11（7059–7069） | 8（7079–7086） |
| 端到端秒 | 157.98 | 130.89 |
| 模型代理USD | 0.01044751 | 0.00509781 |
| 原Runtime调用 | 0 | 0 |
| 交付 | 自写源码、当前JSON、PNG/PDF | 自写源码、当前JSON、PNG/PDF |
| 官方低层Text/Type/Color/Layout F1 | .516129 / 1 / .963027 / 0 | .516129 / 1 / .988346 / 0 |
| 新固定GPT‑4o原rubric评分 | 100/100 | 100/100 |

带库侧没有调用C，也没有导入缓存源码，不能将新JSON或相似代码当作复用。它正常生成了阴影区与注释数组循环，但部分tick/spine/arrow样式仍固定；这份经历可在退出本代留出角色后用于下一代正常学习，不回写本代结果。

原GPT‑4 Vision已退役且Kouri列表没有旧ID；负责人明确批准新的独立judge `gpt-4o-2024-11-20`。此处是**原官方rubric + GPT‑4o 2024‑11‑20替代judge的新评价**，不是历史GPT4V分数。原`OPENAI_GPT`与`GPT4EvaluationAgent`源码/原prompt未改，SDK环境独立（openai1.2.0/httpx0.27.0/PyPDF2 3.0.1）；temperature .1/top_p .95/max_tokens4096，原图在前，方法名不进入对话，同两侧顺序在首评前冻结。无发明的通过阈值。7087/7088各1请求，返回model匹配，代理费USD0.0071425/0.0066925；原SDK单尝试、无额外重试，原响应完整保留。

替代judge漏看带库侧蓝线应虚线的差异，不能将100分写成像素完全一致、严格同质或人工接受。两个原分与人工差异观察均保留，不重评求分。此题带库侧请求、耗时与费用均更多，没有实际采用/降本；学习、认证、失败、评审和人工投入继续计入总口径，供应商实付仍未知。

### 下一冻结输入与验证状态

未看图/未求解的line31已在下一请求前冻结：`efficiency-si-chartmimic-forward-line31-20261110-v1`，plan SHA `08b2a4b6cab42575bf373132cb62ee881adeef041834b80c5b3de20e60e2a5ef`。采用原观察范围16–30之后的首个canonical编号，不根据本轮评分挑图；沿同C2+C3与文件路线。line14保留，line13按监督新优先级延后，不是按分数排除。line31 Reuse已在视频实际交回Gate后启动，当前结果待核对；不提前报告采用或收益。

方法owner工作树首次完整测试12失败由缺失本地DSH安装引起；核对锁定DSH0.1.5-rc.3后复用已有同版本依赖，完整重跑3223 Python通过/274跳过、1693 Node通过/28跳过，原日志保留。场景定向6 Python/5 Node通过，原SDK新judge两次真实响应已完成。main候选最新全量3027 Python通过/21失败/272跳过，均旧发布库code-lock不匹配，Node未进入；不改旧证书求绿，不据owner绿色宣称main可发布。研究隔离运行与合并/部署分开，未合并、未部署、未重启正式服务。

## line31 配对关闭与下一代正常经历

line31固定原C2+C3，未看题前按canonical顺序冻结；两侧均完成源程序、当前JSON、PNG/PDF。带库侧检查了缓存源码，但没有调用原Runtime或执行缓存程序，实际仍新写`ax.errorbar`绘图程序，因此记C0。

| 项目 | 带库侧 | 空库Baseline |
| --- | --- | --- |
| 请求 | 9（7102–7110） | 7（7120–7126） |
| 端到端秒 | 159.285 | 120.587 |
| 模型代理USD | .00636058 | .00488343 |
| 原四项Text/Type/Color/Layout F1 | .5 / 1 / 1 / 0 | .5 / 1 / .978299 / 0 |
| 固定替代judge原rubric评分 | 100/100 | 100/100 |

新judge为7127/7128两请求，代理USD .0082525/.0083625。人工事后查看三图，四组误差棒、坐标与图例的主要结构均在，字号、点线尺寸仍有差异；无独立盲评，不能称严格同质。带库侧更贵、更慢且未采用，不支持效率收益。官方低层旧报告的GPT4V pending保留，新judge作为独立评价追加。

关闭报告为`efficiency-si-chartmimic-learned-pair-20261110-v2/pair-assessment.json`（SHA `fcf9815f3cf178bf2da73e55b62d56840d7760ba4a9f3472aa50b48c12f4535b`）和`efficiency-si-chartmimic-forward-line31-20261110-v1/pair-assessment.json`（`fde08b232e39638ca340ff0a328d52dff273819d22038a0a8d5420377b2a171e`）。两份报告仅允许其完整、可追溯的Reuse侧正常经历进入下一代原学习/修复；没有宣称原任务质量或效率已接受。原试验角色、快照、分数不改写，Baseline/Oracle不进入学习。

下一代`chartmimic-sequence-20261110-v1`在看图或求解前冻结line32–36：计划v3 SHA `2e255f3d31ee357196bc8411020cd33ccfd39326181c0d628fe56306c317ebf0`，依次32 Reuse先、33 Baseline先、34 Reuse先、35 Baseline先、36 Reuse先。不按适用性或结果筛题，不清缓存；每题首请求前冻结当时Store/library，两侧同条件四工具schema，双方及评价结束后才让该题Reuse正常经历参与下一次原学习。保留旧14/31负例；先按14、31的经历顺序准备初始新库。当前尚未求解32–36。

### 真实固定调用的参数边界

原声明学习可提取已见常量/已有字符串字段，但无法开放调用中缺失的合法kwargs。line14实际`ax.plot`明确接收颜色、marker、宽度等，却未表达linestyle，因而入口JSON分离本身不能避免后继重复写程序。原line5已用kwargs映射，不能重复包裹它来冒充新学习。

方法owner提交`e02d808`增加原学习器的有界kwargs选择：模型仅从实际见证的静态调用及其现有对象表达式中选位置，声明当前JSON对象/对象数组上的可选字段和有限typed probe。编译器保持原API、位置参数、显式kwargs、控制流与默认JSON；默认字段为空映射。独立逐对象可设不同选项，不接受动态callee、代码或新API；原生契约必须已允许该数据对象。原认证检查历史默认工件逐字节相同、不同输入确定性，并逐组检查probe确实改变工件；probe参考是在同一原调用直接放入字面量kwargs。接口及来源进入原Store，不另建学习/运行框架。

工程验证：该owner最终完整`npm test`为3233 Python通过/276跳过，1693 Node通过/28跳过；隔离Linux原namespace认证12通过，含默认等价、逐对象选项及无效/无效应probe拒绝。首次Linux导入环境误入祖先src的失败保留，使用明确PYTHONPATH、独立pytest root后通过。手选测试声明不是自主学习或后继收益。

line14原PDF含CreationDate，原样两次执行PNG相同、PDF不同，不能直接认证。新隔离`efficiency-si-chartmimic-nextgen-20261110-v1`让普通Agent继续同一真实草稿，只修复PDF时钟：7146–7150共5请求、40.961秒、代理USD .00323066；唯一源码差异是在原savefig metadata加入CreationDate/ModDate=None，原JSON与PNG SHA完全不变，原`ax.plot`AST不变，未手填程序或kwargs。原提取得到Artifact 1。下一原模型提案将读取更新system prompt、实际调用/对象清单和真实诊断，自主选择接口；截至此处尚未发生真实kwargs提案或独立后继采用。

主分支`faf0384`已推送Draft PR166；GitHub Ubuntu/Windows均实际执行后失败，原因是旧发布库code-lock及相应runtime_kind/兼容断言，不能再记为账单阻断。main发布验收仍未通过，不修改旧证书求绿，未合并、部署或重启。

## 原学习与真实绑定恢复续验

7160在更新提示与真实调用清单下仍返回空声明，原学习器正确记录`no_change`（1请求/USD.00126111）。澄清三种声明操作后，7170自主选择原`ax.plot`的series对象及`/datasets/series`，新可选字段`api_options`、probe为`linestyle="--"`；没有手填调用ID、字段名或probe。默认JSON及PNG/PDF保持等价，原字面量参考与逐组工件效应通过，受控注册program `artifact_e46b93815962f7298dac9900`、library `8514cb00…b2e9`（1请求/USD.00136867/28.664秒）。它仍未通过独立认证，不能作为后继可用C。

原独立拒绝同时包含数组记录字段`xmin/xmax`与固定注释`ha='left'`。编译器修正仅沿固定argv输入、`json.load`、实际对象数组迭代的流，分类所有用法均为读取记录字段的键；普通实体映射/未知/重赋值/兼作输出文字不豁免，不设字段名白名单。监督复现的`cases.get('case_old', fallback)`反例留在检查中。owner`e9a06ce/ed2fbf6`，Linux原namespace32项通过，含空记录正例与复制文字拒绝。首次测试夹具缺输出目录的失败保留；代码与旧运行代分开。7205在新代码下仅重新确认同一组并改善描述（1请求/USD.00146031/28.150秒），源码/program ID未变，也未修`left`；新独立复验仍published0，不计新抽象、不进入后继池。固定样式的剩余边界保留为负例，不追改输入求过。

line31独立绑定初次7185–7187（3请求/29.813秒/USD.00125107）缺JSON闭合。7195–7199同题恢复（5请求/55.805秒/USD.00293118）两次把`true`写成Python标识符而NameError，继而用空series/context兜底，原契约正确拒绝。不能把这些completed状态当作合格输入，也不手补其值。

认证阶段新增极小的原Harness原生`submit_binding`：模型提交实际角色的JSON值，复用SDK原schema验证，固定路径序列化并返回文件SHA；不推断、不填默认值、不执行待认证程序。此工具不进入普通后继，后继两侧仍原四工具。新鲜真实目录7237–7239共3请求/30.901秒/USD.00310970，Actor提交5条series和9个context映射，文件SHA `b2a5b84a7d813a20471623ef576ef60903c892ca94239d1f9acc299f6f826024`与实际回执/最终文件一致；未写保存JSON的脚本。独立认证published1/registered，原误差棒源码未改，program `artifact_8d4932a01adc41db0dac5d84`、library `02d95a2d6d40f2a65a40549cd21c668b473caaf38003192639c1f8edb9cdb0d8`。这里证明源重放与真实换输入执行，完整视觉质量仍不等同结构认证。

record-key编译版本变化触发原code lock，C2/C4以原真实来源和已有独立输入作必要零API重认证，旧文件/哈希保持，非新学习任务。新libraries分别`7aa97dec…10daf`、`c1f5c31a…56525`；与原31合入原Store3个完整程序，catalog `0550128374d0816f523cb68010a0b67cd370a890a4207ae6edc4c944fbd1a7bf`，14未准入。可选字段/默认契约后续由视频牵头，当前绘图代不提前集成新候选。

呈现层保留完整冻结卡/原约束，启动菜单保留完整来源描述与编译选项；选ID才取完整接口。旧两C实际菜单1164字符，完整卡6366字符，卡与原bundle不变，未知ID拒绝。编译后的API/当前对象/键类型/默认值决定新增支持项，原描述作为来源保留，不能覆盖真实新增接口。此呈现与JSON物化均为工程修复，不能单独记为Motif效率收益。

最终相关12 Python/3 Node通过；新结构提交实际Linux SDK schema/值物化预检通过。main完整3033通过/21旧发布锁失败/272跳过，Node全量未进入；owner完整3222通过/19旧发布锁失败/278跳过，旧库未改。不据局部或组件通过宣称可合并/部署。供应商实付与完整开发维护成本仍未量化；所有上述失败与恢复进入总投入，旧冻结配对和评分不回写。

### line32 初始库与真实复用侧失败

line31准入的真实来源是正常经历中的成功独立初稿，源码SHA `577e6db580715c7933a9ec16c17a4e4bbed8bacadb5736ec49cb569980cdfc16`；最终交付源码SHA `1e6eaf23d8be987d2d2d5bd1ed74f34cf88438e2a72922b10c759cbcb2528752`后来调整了边距和spines，未形成新的独立提取调用。未手工移植最终修改；最终交付的judge分数也不充当初稿的独立视觉认证。

line32在首请求前冻结三程序Store、pair plan `f3cb17afe777b48963bdb74e7bb3efde6f6027edd730d13c42d6280ee9b1d69c`及sequence v5 `015ea939672c7dc0dfd8700317e9c03f8f2742f78d5d1b5a21a3c2612ea25d1e`。Reuse实际7252–7259共8请求、69.882秒、代理USD .00361227，没有PNG/PDF，C调用0。Actor查卡/源码后尝试写`/work/inputs/plot-spec.json`，被只读原材料挂载拒绝，继而误称整个`/work`不可写。实际当前文件应写可写`/work/plot-spec.json`，适配器再投影到Runtime的只读输入。该失败保留；不能算绘图能力不适用或成功复用，也没有合格经历可更新库。Baseline继续原冻结代码，不在配对中修提示或重跑。配对关闭后再区分调用者文件接口和Runtime内部路径，保留输入挂载只读。

line32配对已关闭：Baseline7278–7284共7请求、104.651秒、代理USD.00528545，交付源码/当前JSON/PNG/PDF；原四项Text/Type/Color/Layout为.4/.5/.478826/0。固定替代judge7285一次请求（14.769秒/USD.0086325）给100/100；人工事后观察网格覆盖曲线、字号/边距差异，原分和差异都保留。Reuse无交付，官方分数缺失而非零分；该题无可用于下一代学习的Reuse来源，三程序原Store保持。

私有评审driver首版误将auditor最终`ordinary_source_and_parameters_present`与中间`figures_present`状态比较，把Baseline误标无图，新增API实际0；原`judge-pair-plan.json`/`pair-assessment.json`保留并明确失效。修正只读取实际交付figures，首次真实评审使用`judge-baseline-002`；有效关闭记录`pair-assessment-v2.json` SHA `3b8b5a58fae03824dd7781e0439aab45766aca53db8f27363149cf5ac4b6b70b`，未重评求分。

下一题前实际零模型验证相同原`execute`→当前文件→原`capability_call`：使用既有独立line11 JSON b2a5…6024，不提供32或未来参数；在`/work/probe-current.json`写文件、适配器投影为只读输入，Runtime成功导出原31源码577e6db…cf16及PNG/PDF。输入挂载仍只读。首次诊断cp继承0600且文件属container root，导致宿主边界复制EACCES，001失败保留；002用普通Python新文件写入后成功，未改公共IO/权限。

line33首请求前冻结pair SHA `e13f57f0bb4fa1e0bddd70fefb319db7aeb087c9fe9a631dc88138d7002820dd`，原catalog055012…a7bf不变，先Baseline后Reuse。新隔离caller-v2仅区分真实调用者参数`input_files/output_directory`与保留的内部`native_input_schema`，并给两侧相同的可写当前文件/只读原材料说明；32源树及旧库不变，Runtime仍原record-key-v2。此处尚未观察33采用或收益。

### line33：真实完整程序复用，但整体更贵且缺少参考线

双方及固定评价已结束，关闭记录SHA `4fe3f124b16ae6b32eeaf99e7e35f67f72761ed078d4dc80c3f19f5c271657ca`。Reuse7290–7302共13请求/133.662秒/USD.00866811；Baseline7286–7289共4请求/57.487秒/USD.00233547。Reuse最终确实交付原C4程序`artifact_a13e1251d539309d9bfda700`，源码256121…58f0与认证版本逐字节相同，最终PNG5a11…1773/PDFecf5…35fd匹配原Runtime收据；未重写绘图算法。四次native尝试中两次成功，两次因复用已存在输出目录拒绝；这些重试及源码查看均计入成本，不能删掉后报告收益。

原四项Text/Type/Color/Layout：Reuse .5/.888889/.873259/0，Baseline .5/1/.982015/0；固定替代judge分别93与100（7304/7303，USD.0068425/.0066025）。事后独立查看三张实际PNG：Reuse四曲线/数值大体一致，但漏了参考x=20的蓝色竖向点线；Baseline保留。成功执行不等于覆盖全部要求，不能称同质收益，也不能将该题新增为发现/认证任务。C4版本的实际调用不单独证明此前labelcolor扩展在本题起了作用。

实际用量完整：Reuse输入159545/输出1631/cache-hit90021/miss69524；Baseline输入26599/输出1831/hit13777/miss12822。输出略少但总输入、请求、耗时和费用更多。先前`result.output_present=false`只检查固定`rendered`路径，不能否定最终`rendered-final`的真实交付；原结果保留，实际交付由冻结选择规则及source/input/artifact哈希审计确定。下一题复用现有delivery审计报告实际最终路径，并给两侧共同说明每次渲染/改参使用新的未占用目录，不改原fresh guard或当前成品。

## line35：修复后最小独立配对与新正常程序

按监督审阅后的新方案，仅运行原预定未见35（Baseline先）；34R保持未配对，不启动34B/36、不从34训练。首请求前冻结plan `d4458b485e47b511e59c82f4376a6f60600a9c0702b96701ae9efd3e304d8a5e`、catalog `57ed914444fc7f2dba35413ccd84e511b730bf030d81973ce528042462ca88ee`，场景逐文件匹配`c1b9cf9`。原三程序/905 Runtime不变，原value/file共6入口、菜单3操作，两侧同新版四工具schema、Luna/none/128000/600秒、原账本null。先冻结再看图，无适用性挑题。

| 项目 | 带库Reuse | 空库Baseline |
| --- | ---: | ---: |
| 请求 | 10（7344–7353） | 8（7336–7343） |
| 端到端秒 | 151.448 | 100.571 |
| 模型代理USD | .00679444 | .00312270 |
| 输入/输出token | 115176 / 3410 | 33750 / 2145 |
| cache-hit/miss | 71424 / 43752 | 14720 / 19030 |
| 原低层Text/Type/Color/Layout | .538462 / .2 / .195779 / 0 | .538462 / 1 / .984856 / 0 |
| 固定替代judge原rubric | 100 | 97 |
| 最终交付 | 新写普通程序/当前JSON/PNG/PDF | 新写普通程序/当前JSON/PNG/PDF |

Reuse确实通过既有value入口一次成功运行原C4，初稿没有先写JSON文件，也没有目录失败；随后检查图形/尺寸、读取完整缓存源码、回退新写`plot.py`并运行，最终不是原C4接管。新程序明确从当前JSON调用`ax.set_xscale`并表达竖向阈线；原C4没有x尺度入口/独立阈线样式。前端少一轮已修，但能力覆盖与适配选择仍阻止整体省模型工作。请求、输入、输出、耗时与费用均未改善；新judge高分不改变这一结论。

7354/7355固定judge各一请求，代理USD.0060225/.0064525；本对包含评价共20请求/USD.02239214，非账单实付。人工事后看三PNG：两侧主log轴/曲线/四条竖虚线均在，Baseline字号过大且ylabel边界裁切；Reuse竖线位置/布局仍偏移。原低层原分与新judge不重评，无独立盲评，不称严格同质。有效关闭`pair-assessment.json` SHA `5bbf610d8a51577b0390a138b2fd199ac17d44a25e45f15329b637f91f909f85`，后续只做零API原提取/体检，已停止新增付费。

原extract从最后真实独立CLI调用取得Artifact 1（`artifact_5642c5d839ccd9a755f296ee`）。源码`bdb1626bacd540683d2a6af63931155266b928c9c03bbc55d91b3082ee3854d4`、输入`dc05565f16384ae4614a603bf2d83bc6d552b11fd28b4b507f0bd655bbcdfc04`与最终真实文件一致，原admission通过；`learn.prepare`生成原observations/interface。原样两次隔离重放均与原PNG `a701fcc47c08241f0a331175742c2e8ce1664a470cf1b2705e41572ac5ffd31d`、PDF `b1ef8c7b3abc5f95f736d97405be61a20694f7635e4027288e87ae12f7dc0fbb`相同。不是独立认证或新C。

该源码在main入口绑定数据/axes/所有配置/路径；`for item in series`不固定N（静态推断），vertical使用当前标量x、curve使用当前x/y数组；尺度/阈值与稳定API分离。边界为线性y、无title/errorbar API、curve样式按类共享及固定zorder/capstyle。首记录的observed类型只描述vertical，不能把它当作curve所需数组类型的排他契约；原docstring明确两种分支。原预留认证11有标题和水平虚参考线，当前程序缺title/独立curve样式，不能忽略要求强行认证。未改源码，也未手写新Motif；最小不同输入认证计划须明确历史/未见范围后另行审阅。

已有连续账本能明确归属ChartMimic命名目录的模型请求263次，已知代理小计USD.36667712，6840/6925/6947三请求费用未知；包括前期学习、恢复、失败、配对与评价。它不是共享累计USD102的全部归属，也不包含完整开发/人工/维护成本，不能用此证明净收益。归属、原请求和未知字段保留在私有`all-chart-attributed-ledger-through35-001.json`。
