# AgenticVBench P0：正常视频任务与执行后端准入诊断

## 问题、冻结范围与当前判断

最新状态：新C真实采用并交付合格清单/视频；原空库主配对的字段失败不改。随后预声明、
仅执行一次同任务正常恢复，两侧达到原固定合格门槛；累计恢复成本后R参考模型费低61.2%、
请求少52.9%、执行耗时低35.6%。这是一个固定决策任务的次级暖库结果，源学习尚未摊平，
编码未被C接管；不外推完整冷启动收益、稳定大库收益或递归SI。全部阶段已结束，不扩样。

本轮只研究正常任务学得可执行程序能否在变输入后替代重复模型工作，不启动 Evolution。
先取得正常剪辑程序并检查原后端准入，再决定是否进入学习、认证与冻结后继对照。
**初次预检未实现效率 SI，也没有启用正常学习。** 新Assembly开发诊断19请求后仍未交付，原评分0；两段真实
视觉测量Python程序均被原后端拒绝。没有认证C，不进入后继扩样。

实验 ID `efficiency-si-agentic-vbench-20261109`；正常开发题为官方 Assembly task2。
原 task1 旧运行只作故障定位，不并入本轮质量或收益。Sequencing task1/task2 仅作
适用性预检，不把零模型检查当作真实任务/回退验收。没有扩展 Repair/Repurpose。
未形成认证库前不运行暖库对照，也不消耗冻结后继题去修库。

## 官方任务核对

官方仓库 [PhiloLabs/agentic-vbench](https://github.com/PhiloLabs/agentic-vbench)，版本
`b2764ed4b2a4b5a1737026b63887b50bba62f793`。本机预备副本和服务器素材来源相同。
预检逐题读了题面、Dockerfile 与 TOML，没有读取 Oracle 或正确片段顺序。

- Assembly 共18题；实际镜头槽位为3段8题、4段4题、5段4题、6段2题，不能写死README的4段。
- Assembly task2：12个候选，4个故事板槽位，模型负责视觉识别、选择与顺序。
- Sequencing 共28题；task1/task2分别要求完整排列13/7段。
- 两类均要求真实 `output/solution.mp4` 和连续半开时间区间的 `output/solution.json`。
- 官方工具为 ffmpeg/ffprobe；评分器检查清单与实际视频片段的匹配，包含内容一致性校验，
  不是只比较 JSON 顺序。评分器在求解结束后注入，未向 Agent 提供答案。
- 环境将素材烘焙到 `/baked/materials`；正常任务先复制到隔离 `/workspace/materials`。
  Assembly task2沿用已有镜像 `sha256:9c3057962d457d088de9e15c0c990bde6d860566784eb53b9326f75638613bfd`。
  该镜像仅替换网络镜像源，原Dockerfile SHA256为
  `600586bc2975924c3c13ab343e7a154b56ef824451206db435d0fae01ac8a40f`。

## 复用原接口的检查与决定

代码起点 `5e21c75`，独立分支 `codex/agentic-vbench-efficiency-20261109` 快进最新main
`e2494b0d0df64d0e63949a9e36823ad973fd5b61`。未复制共享脏树或合入PR164。
已查相关开放PR：164为原生论文/Remotion候选，尚不能提供ffmpeg认证；Coding的
BENCH-01/02等Issue并非本视频侧的已交付适配。

检查了 `BenchmarkHost.trial()`、`SkillsBenchTrial`、原 Script/Artifact/Source 编译器、
Remotion `structured/learn_programs.py` 以及只读研究候选 `c2f332b` 的
`execution_learning_pipeline.advance_execution_learning()` 与 `collect_shell_call()`：

| 接缝 | 实际限制 | 本轮处理 |
|---|---|---|
| BenchmarkHost | SkillsBench根目录布局；ResearchHarness callback仅文本 | 不声称已接入官方视觉任务，沿用已有原生工具Runner |
| Script | 受限Python、只读与固定输入证据；不允许ffmpeg进程调用 | 原编译器检查，保留拒绝 |
| Artifact | `subprocess/cv2`不在准入模块；输入按有界UTF-8文件建立契约 | 不加入视频字节或开放子进程白名单 |
| Source | TSX/JavaScript实例化，执行属于既有场景后端 | 未包装成Remotion或另造后端 |
| Remotion Source学习 | 成功TSX、write_source/render_source事件、真实视频receipt及质量证据 | 不把shell/ffmpeg调用冒充该证据 |
| advance_execution_learning | 复用原Script/Artifact认证与Store，不提供ffmpeg执行后端 | 未有合格来源时不付费构造或空转认证 |

本轮新增 `scenarios/agentic_vbench/preflight.py`，仅作场景预检。
它将真实成功命令交给原解析器/编译器；`static_pass_only`不等于候选获认证。
没有从最终工作区补造调用前快照，也不从评分器生成程序。

## 实际运行配置与私有证据

Linux隔离根为私有 `.local/benchmarks/efficiency-si-agentic-vbench-20261109`；素材、凭证及
Node依赖只读沿用 `efficiency-si-20261108`，新输出和代码归本实验。没有修改正式服务。
代码以 `git archive e2494b0d` 同步，SHA256为
`bfece94594cc7149e3ac92f456fab6b0f0a0a6c5bcfdc97c61c23e5d70c57e90`。

正常任务沿用既有 `run-video-task.py`，私有副本只补900秒取消/关闭回退和简短输出策略，
未增加Agent循环。Runner SHA256为
`4d6dcd3ee9571efc402d2706ea07d0fd0f7e40c21d9faf989170c4238c14d76f`；原生TS工具SHA256为
`7b8a612888a45306acd9d49063595ca7b2218e9a236e31f844a985d539e6f8a5`。

| 配置 | 生效值 |
|---|---|
| 模型 | Kouri AI，SDK `deepseek-flash`，wire `deepseek-v4.1-flash` |
| reasoning / max_tokens | off / 393216 |
| 费用/请求预算 | null/null；继承原累计账本，不重置 |
| 诊断墙钟 | 900秒；官方题面为1800秒，本轮不是正式等时限benchmark成绩 |
| 工具顺序 | execute、read_image，原生注册，无MCP场景服务 |
| 图像 | 模型自己抽帧；原工具宽度最多1024px、等比例JPEG传输，原图与原视频保留 |
| 平台 | Linux 4.15.0-213-generic，Python3.10.21，Node22.23.3，DSH/SDK依赖锁见代码归档 |
| 库/匹配/embedding | 无认证库，未启动匹配或embedding |
| 压缩/重试 | 图像按上述工具传输；原始日志保留，未新增上下文压缩或模型重试循环 |

连续账本是原 `.local/experiments/remotion-motivation-20261027-v1/{cost-ledger.jsonl,budget-checkpoint.json}`；
本轮开始前6806请求、累计代理记账USD96.45768036。与ChartMimic按同一个
`capability-proposal.lock` 串行，新Gate不支持并发，未重建账本。
`SSS_BUDGET_CAP_USD=0`只是原Gate激活标记，实际State的`cap_usd=None`，未解释为可付费数值零。

私有run：`results/assembly-task2-development-380fa3f9bd`，保存 `effective.json`、原生工具、
Harness事件、原请求与费用回执、工作副本及官方评分。原始记录不进入Git。

## 本轮结果

### A 正常任务与 D 独立评价

2026-11-09完成一次新诊断，elapsed 904.944685秒。19个真实请求6807–6825，40个完整
原生工具调用（15 execute、25 read_image）；18个模型step结束，第19个未完成。
Agent生成联系表、多次候选单帧及两段光流/相机运动测量程序，仍未写成片和清单。
没有拼接/渲染交付，也没有调用能力后重写的案例。

钉住SDK对 `session/cancel` 返回 `unknown DeepSeek Harness SDK runtime method`；回退
`client.close()` 后记录 `runtime_closed=true`，原Runner以TransportClosedError保存失败。
不能把该RPC写成accepted取消。最后请求用量缺失并保留预留，不自动重试。

普通Runner异常分支未执行其评分段，因此另启动禁网、工作副本只读的评分容器，挂载原官方
`steps/solve/tests`，执行原 `/tests/test.sh`。独立 `reward=0.0`，原因为缺少solution.json；
清单/视频均为空，不能判断视觉选择是否正确。评分发生在求解容器关闭后，答案未进入求解
上下文或学习器。评分SHA256为 `e27b5f3b24eafabb05493a674c1c93de602516f5a3a8a6cb44b5ff7cd73a6cfd`。
未人工修订产物，无成片可作视觉盲评。

12份工作素材逐文件SHA256与镜像原 `/baked/materials` 相同；完整输入清单保存在私有
`audit-summary.json`，镜像ID也与准备时相同。没有将模型生成材料替换官方输入。

### B 学习准入与 C 后继复用

完整轨迹经原解析器预检：15个execute中，13个复合shell/管道命令不能作为单一Python
程序提取；2个真实成功Python调用提取出源码，但两个后端分别拒绝为 `import_not_admitted`
和 `program_import_not_admitted`，涉及cv2/glob及视频输入。两个调用分别为：

| 正常程序 | 原生call | 命令内源码SHA256 |
|---|---|---|
| flow.py，读取各候选并打印相邻帧位移统计 | call-6232ffa8-28cd-43b0-8770-b9a731b0b5fa | 3a7d86d1f4ae7d562281e8281da27f31a48877eb16d2d1cc92affcaf35ba152e |
| flow2.py，进一步测量相机运动 | call-c1d5a12f-3024-4cdd-b8e7-20e4e4b766dd | 69595102af46d284e996218093509776552f771262c549fc6543c67a0334a8b9 |

以上是正常模型生成的诊断程序，不是学出的C或剪辑程序。原工作区文件各多一个末尾换行，
文件SHA另见audit-summary；不混淆命令源码和磁盘字节。命令参数中原样提取的源码及call
映射另保留于本地私有 `witnessed-programs/`，没有手工参数化或写入公共能力库。
shell返回0也不代表每个管道子命令成功；原始错误输出保留。

静态预检不拥有完整调用前后快照，不能伪造认证来源。本次普通任务本身未合格，因而没有
向普通学习流程提交该失败经历为合格训练样本，也未调用Builder、认证器或Store进行发布。
**合格C为0，学习/认证/冻结库/后继采用均未进入；不能把它归因于匹配失败或学习成本过高。**

### 成本与研究问题的回答

| 量 | 本次结果 |
|---|---|
| 真实请求 | 19；18已结算，6825用量/费用未知 |
| 已知输入/输出Token | 275196 / 20652；未知请求不计零 |
| 已知缓存hit/miss输入 | 0 / 275196 |
| 已知代理估费 | USD0.1073412，下界，含全部已知失败成本 |
| 未知请求保守预留 | USD1.3741872，非实付、非实测费用 |
| 账本结束快照 | 6825请求、累计代理记账USD97.93920876，含历史/本次未知预留 |
| Kouri账单实付 | 未取得 |
| 学习/认证/匹配/修复请求 | 未进入这些阶段；本轮没有新增相应模型请求 |
| 人工修订/维护 | 无人工修订成品；开发与维护未独立计时，货币成本未知 |

1. 重复模型负担主要在联系表/帧探测代码、候选视觉比较和运动诊断。本次所有已执行工具
   均停在准备/视觉测量；没有观察到可量化的剪辑代码替代。
2. 自主学出的C没有产生；正常程序来源和拒绝见上表，不能把它们直接登记为能力。
3. 没有冻结库，未在变输入后继中测试自然采用；两项Sequencing只是接口适用性检查，
   没有声称真实安全回退已验收。
4. 没有同质量的A/C成品对照，也没有暖库前向收益、冷启动摊销或净省费结论。
5. 首要阻断为正常Agent未收尾；独立的接口阻断为实际shell/ffmpeg/cv2程序不能在现有
   受限后端编译并执行。不能由此推断不存在稳定抽象，更不能通过放宽沙箱来制造正例。

不扩到8–12题。下一项决定性条件是：先在正常、质量合格经历中自然出现可由既有后端
承接的稳定程序（例如实际生成的独立文本元数据处理程序），随后才用互斥认证和后继输入
走原学习链。如果真实剪辑始终依赖未支持的ffmpeg执行器，本轮保留此接口阻断，不另建后端。

私有最终证据：native工具SHA256 `98d007569e65987fece0d2834f37d944e34d6ae7433dbcf90765456450fa5a6f`；
Harness事件 `0de1c985ef1f93c302b5007214633e2e84bb12d4cf5b235e59a72e82797b02d4`；
费用回执 `a07d003495c42b12322f98dc426546075a12c4eb7b90128b5152f182310d2086`。
原素材和完整权威现场仍在服务器；必要结果/事件/诊断已同步本地，未清空私有材料。

## 复现与工程验证

零模型预检：

```sh
python scenarios/agentic_vbench/preflight.py \
  --official-root "$AGENTIC_VBENCH_ROOT" \
  --trace "$VIDEO_RUN/native-tools.jsonl" \
  --output "$NEW_DIAGNOSTIC/preflight.json"
python -m pytest -q tests/test_agentic_vbench_preflight.py \
  tests/test_artifact_motif_compiler.py tests/test_script_motif_compiler.py
```

真实入口仍是私有环境内已准备的原Runner副本：先在服务器项目根加载
`source .local/remote-env.sh`，令 `GENELOOP_BENCH_ROOT` 指向本实验隔离根，
`GENELOOP_LEDGER_ROOT` 指向上述原账本，再执行
`"$SSS_PYTHON" "$GENELOOP_BENCH_ROOT/run-video-task.py" assembly --task-id 2 --call-model`。
这会创建新的UUID输出并消耗真实API；复验不得覆盖本轮记录或把复跑当首次未见评价。

定向检查29通过，仅证明题面解析和既有拒绝边界；公共Runtime/依赖/Harness接口未改，
未为本预检重复运行全量npm测试，也不以这些工程检查作为视频质量结果。

## 后续改进：正常程序来源与供应商阻断

以下为新阶段，不把初次 `learning_enabled=False` 的预检写成一次失败的完整学习实验。
历史 Remotion 复用节省过源码生成、参数绑定、渲染与检查工作，其来源是真实 TSX 加原
Source 参数化/渲染认证。本题当前生成的 cv2 测量和 shell 命令不能直接走同一后端；
这个差别不证明官方视频题不存在可复用的确定性部分。

`trial.py` 接通原 Harness 的正常执行与共享原生工具，要求 Agent 自己设计 JSON/程序
边界、先完成当前最佳成片再修订。`learning.py` 将真实前后快照交给原
`collect_shell_call/advance_execution_learning`，认证和 Store 不另实现。认证题 Task6、
封存后继 Task13 在 `roles.json` 预先固定，均为4槽位/12候选；选题未读取答案。
场景适配、普通工具/消息策略的收益不能记作 Motif 收益；未来两侧须采用同样配置。

研究依赖显式固定 `c2f332b72997bb82b532ed4f13d0b04eea10df9e`，它是既有学习链的
研究候选，不能写成已合入主线。矿工、编译器、Store、执行后端保持该来源；共享接线
提交见 `f0a9295`、`48be82f`、`62182ed`、`5f105b9`。原采集器漏建空 `command-tmp`
会使原 Artifact 执行失败，已补齐；历史捕获不修改，只在逐文件验证 SHA 的派生执行
副本中还原该原有布局。没有放行 subprocess/cv2、制造视频执行器或手写目标 Motif。

新隔离根 `.local/benchmarks/efficiency-si-agentic-vbench-20261109-v2`，同一开发题的
两次复测均保留失败，不是两个独立未见样本：

| run | 请求 | 用时 | 实际终止 | 产物/原评分 | 已知代理估费 / 未知预留 |
|---|---|---|---|---|---|
| task2-source-v2-001 | 6902–6907，6次 | 128.04秒 | HTTP502 | 无 / 0 | USD0.0147624 / 0.8511234 |
| task2-source-v2-002 | 6910–6917，8次 | 324.75秒 | EMPTY_RESPONSE | 无 / 0 | USD0.0327900 / 无 |

两次均发送 `thinking.disabled`、max_tokens393216、费用/请求null，工具顺序为
execute/read_image，禁网 Docker 与官方真实素材。每次求解退出后才注入官方评分。
第二次原 `result.json` 在最终请求结算前取快照，因而金额为null；后置只读审计
`results/source-retests-audit.json` 确认8次均已结算，未追改历史。新适配在 Gate 退出并
排空记账线程后汇总，修正此竞态。正常执行仍未出现可提交的程序；原提取器对第二次
4个复合shell调用均拒绝 `single_python_invocation_required`，候选0、准入false。

### 最小原始响应诊断与 Luna 切换

原日志没有保存原始SSE，不能仅凭usage判断上游有效。通过原连续Gate做最小图像检查
和精确失败请求6917复放，保存原始响应：6918的真实图像进入请求，返回有效工具调用；
6919为HTTP200、577段 `reasoning`，共5456字符，正文仅空白，无tool_calls，finish=stop。
原 Harness DeepSeek adapter只识别reasoning_content，且不能把reasoning当工具调用；
这里同时存在供应商响应内容及字段兼容问题，不能直接归因模型能力或学习器。
同请求6920改为非流式，返回两个完整read_image调用；一次成功不证明稳定，且报告的
16558输入+83输出≠16700总token，原Gate保留未知费用，不放松一致性检查。
临时非流式适配未进入实际任务，后续按用户要求停止该路线，不修改上游Harness核心。

按用户确认 Kouri 支持 `gpt-6-luna`，新实验编号
`efficiency-si-agentic-vbench-luna-20261109-v1`。只改研究进程配置，不改生产默认。
[官方模型文档](https://developers.openai.com/api/docs/models/gpt-6-luna)明确图像输入与
Chat Completions函数调用需reasoning_effort=none，最大输出128000、窗口1050000。
通过原 Harness pi-ai adapter 的已有 `llm-pi-ai` 条目配置路由，wire为
`gpt-6-luna`、`max_completion_tokens:128000`、`reasoning_effort:none`、stream=true，
无DeepSeek thinking字段。共享接口在 `a7c0a6d`；原Gate继承原账本并支持对应输出字段、
nested cached_tokens与实际response_models记录。配置价格为官方参考估价，非Kouri实付。

`luna-native-probe-001` 重复挂载pi-ai在请求前失败，0请求；改为配置已有条目后，
`luna-native-probe-002` 用原 Agent循环完成真实JPEG读取→execute→可见回答：
6921–6923全HTTP200，上游均报告gpt-6-luna，3请求201.26秒，参考价USD0.0017407。
输入JPEG61976字节，SHA `ecb63290c2e02d3d8cd062b397b957c5cc91f27e8186d9c8f1f030a8322cee71`；
模型描述宇航员/飞船/橙色岩地与云，并读取实际printf返回的luna-roundtrip。
这只验收模型/图像/工具接线，不是视频完成、学习或SI证据。结束账本快照为
6923请求、USD101.00533726含全部旧未知预留；不清零，后续累计值以现场为准。

### Luna 正常 Task2 与当前修订

`task2-source-luna-v1-001` 沿上述配置执行，代码快照 `43eeae5`，原生工具SHA
`f4ddd969c275ef59edf74423cb33d9bf2d726350d3b68c9eedd98b65b714dc25`。
10请求6929–6938、755.61秒、官方参考价USD0.01166468，交付两份实际文件：
MP4为11063971字节，SHA `de180d51effa052be50f4627a3658d472bcf2d51be396b8466814b50ba65093d`；
JSON为624字节，SHA `73e325628dab24e4c054077be276bcde5766cd7b00e61cd7185b3db4b5a46b85`。
官方独立评价格式可解析，但4个槽位均不匹配，reward=0；评价SHA
`71c971a3b87fd4f4234f426f48ee27593cca7f1b0a2587f465a0056dd346d470`。
模型自行读取12份概览、设计实例JSON、写edit.py并修复路径错误，最终成片并非人工拼装。
但质量未合格，不能把它的产出直接登记为合格C。

实际程序另暴露明确学习边界：清单计算与subprocess调用ffmpeg混在同一模块，视频
中间件写在小程序输出区，可能使有界边界不完整。原后端不准入subprocess；这里仅根据
真实源码与原规则定位，尚未把本次完整边界送进原提取器，不能伪称认证已执行。
用户随后明确要求首次写码就考虑复用，把上下文变量集中到开头。`7045501`将该要求
加入正常任务提示，并明确纯数据程序与外部媒体执行分开；没有替模型写程序或固定选片。

同一提交先尝试通过原session续修；真实v1-002被钉住SDK的already exists拒绝，0请求、9.57秒。
查明其wire只提供initialize/session-prompt/shutdown，首次prompt总是create，不支持跨进程恢复。
2d91bc6改为原Harness的新会话载入同一开发题的工作文件和原题面，保留旧session与所有产物，
不改上游核心或另写Agent循环。v1-003以1000秒诊断启动，沿用Luna/原账本；来源初轮
755.61秒仍计入同一开发成本。仅反馈聚合reward=0与代码组织问题，不发送正确片段ID/
每槽答案。它是开发修订，不是独立未见评价；模型切换/提示改善不能记作Motif收益。

随后V100新SSH及原有会话均被远端关闭；原回归SSH退出255，远端测试进程/终态未知。
Chart当时的600秒工作窗口也掉线；随后恢复并只读确认原任务完成、Gate空闲，完成明确交接才续修。
未启动认证题/后继题，不操作正式服务。当前最新视频完成账本快照为6938请求、
USD101.09234343，含其他阶段/会话及未知预留，不是本轮实付。

新增预算/编译器定向53项、模型及其他Gate15项、续修归属/边界/预检9项通过。
共享原生与Capability传输Node6项通过；既有c2学习专项50项通过。
main隔离副本43eeae5完整npm test最终取得Python 3259通过/28跳过/31失败，26分09秒，
未进入Node阶段；其中增加的21项为旧发布库代码锁失效，旧10项解析/OCR环境失败保留。
43eeae5 hosted Ubuntu另为3267通过/30跳过/21失败，均不能写成全绿。共享Gate文件在旧发布库代码锁内，候选合入/发布前必须重新Execute
认证；不通过修改旧证书hash规避。没有合并、部署或重启服务。


### 配置前置后的真实结果与采集修复

v1-003在原Harness新会话续修同一Task2，18请求6953–6970，1009.52秒（1000秒取消后
收尾/评分），交付新MP4（15287824字节）和JSON（632字节），但超时且官方reward仍0。
15次用量完整，参考估费USD0.03019901；6955/6957/6958三次502用量未知，保留预留
USD0.455242，不记零。视频结束快照6970/代理记账USD101.66021063，不是实付。
同一Luna开发题两次付费运行合计28请求、1765.13秒；另一次错误恢复入口为0请求/9.57秒。
模型兼容检查、旧DeepSeek失败及所有历史未知费用另见上文，不从完整成本中抹去。

实际行为已变化：Agent自行将edit.py改为独立JSON驱动的build_manifest函数，实例选择
集中在instance.json，入口先读取配置，函数体按传入clips计算；ffmpeg在普通execute另跑。
原Artifact validate_source接受其AST（static_pass_only），源码SHA
`fdb9bdb3c616ce2388ba19de28959f2db1ba4ee1219e36305f2af668475e05d2`。
程序输出与最终交付JSON的SHA相同，为
`039397a58db9b3bba940fa7151c5583aa17555112ef814bf9f62346e6424be7a`，证明进入实际交付，
不是只写了未使用的示例。新MP4 SHA为
`08b6b1186a521b1a45a1881bfb4031a22491ddbdfcb4d64cf31eea30bdd5c628`。
这只是程序形态/参与数据流的证据，不是能力认证或收益证据。

原collect_shell_call实际提取v1-003仍为Script0/Artifact0、learning_eligible=false；
12个执行边界因继承旧视频而不完整。v1-001同样为0/0，拒绝包括复合调用、原执行失败
和不完整边界。原始失败保持不变，没有从最终工作区倒造合格的调用前状态。

97ef631修正续修环境：只归档新工作副本中的旧program-output树到媒体区，并在上下文
明确新位置；原结果/边界/文件不动。历史边界投影还保留真实空目录，不能靠省掉模型
预建的空输出目录制造fresh-output条件；首次写码提示明确让程序创建尚不存在的输出目录。
新配置layout为config-first-separated-data-v4，尚未用该配置跑新付费来源。

用真实v1-003工作文件做零模型预览与原生Docker execute smoke，8个旧输出归档逐字节
验证一致，原件不变；新调用before/after完整性均true。记录为
results/task2-archived-layout-preview-001/layout-smoke.json，scope明确为工程连通性。
最新续修/布局/预检10项通过。修复不追改v1-003的不完整快照，也不能把它升级为候选。

当前结论：变量前置和程序/渲染分离能在正常执行中产生可复用的纯程序形态；本题仍未
达到正常任务质量门槛，故无合格来源、认证C、冻结后继复用或效率SI收益。两次Luna
选片均未匹配，补查后段画面仍未解决，不能只归因首轮采样不足。程序组织介入来自用户/
开发修订，不声称自主发现；开发维护人工时间未独立计量，不能声称完整净降本。
不扩Task6/Task13或Sequencing，不修改冻结评价标准或旧证书求正例。

初次费用表的缓存命中0为旧代理字段回退值，不代表供应商实际未命中缓存。原Harness已知
usage另报告cacheRead18734、fresh input256462，合计输入275196。历史账本不追改；
a7c0a6d只对新请求解析nested cached_tokens，旧/新估费解析口径不能混作缓存收益对照。

### 独立局部认证：配置到清单

用户确认继续将局部计算认证与整段视频质量分开。新实验为
`efficiency-si-agentic-vbench-component-20261109-v1`，代码起点 `9889fde`，角色与程序摘要
事先固定在 `scenarios/agentic_vbench/component-roles.json`。这不追改上面的 Task2 零分、
超时或不完整边界，也不宣称完成官方 Task6/13 视频任务。

原图像传输抽查发现，最后请求6970确实包含 Agent 已查看的两份完整JPEG；第一镜头所选
素材有明显抬手指向动作，与要求的双手静放不动冲突。现有证据不能将选片失败归为适配器
丢图，完整视频质量仍未通过。

局部任务独立检查当前配置顺序、实际视频流时长、完整源区间、连续正区间及总时长；
评价器不读程序源码或官方选片答案。Task2来源保留原 `edit.py` 和 `instance.json` 原字节，
由原 Harness 正常 Agent 重新独立执行与实际交付。`task2-component-source-001` 完成，
5请求6986–6990、77.54秒、已知参考估费USD0.00219640，无新增未知用量。
交付JSON仍为 `039397a5…725625`，程序仍为 `fdb9bdb3…05d2`。继承旧MP4不计作本次产物。

原 `collect_shell_call` 从本次完整边界提取 Artifact1/Script0；局部准入true，整视频准入false。
候选 `artifact_62830cb2f278e70d599dca42` 的输入摘要和真实执行输出均绑定本次交付。
Task6 `task6-component-certification-001` 用当前媒体生成3段新配置，程序原字节不变，
独立检查通过；9请求6999–7007、306.47秒（含准备/收尾，模型诊断300秒）。8次已知参考
估费USD0.00561403；7002响应usage自相矛盾，费用未知，保留USD0.0659239预留，不记为零。

最初原提取拒绝其真实绝对源码路径为 `script_outside_workspace`。场景适配新增最小路径
投影：只将真实before快照中验SHA匹配的容器Python源码操作数映射到原 `/work`，其他命令、
shell语法与参数不变；原事件/命令摘要及投影另存证据。未知、变更或穿越路径不投影。
没有修改程序、重跑模型或放宽原认证。旧提取失败保留；`extract-002` 得到同一 Artifact，
`component-native-admission-002` 通过原 `advance_execution_learning` 和 Node 原生认证，
published1/rejected0，`quality_cost_promoted=false`，新增模型请求0。
C为 `cap_681acb4d9b6b69084766f1a1`，library SHA
`176f68ff88751caf588db201e2115df089d44cde7c05f112edfc34db31201e9b`；认证范围为配置到清单。

按用户后续纠偏，Task13尚未接触前改为先做正常视频后继小验证，沿原 `roles.json`，不执行
局部5段配对/准备方案，不改其旧冻结记录。Agent自主选片并决定是否采用C，检查生成清单
是否进入普通ffmpeg交付，最后走官方视频评分；小验证900秒，模型/账本不变。
没有完整同质对照前，不据局部程序认证声称整视频降本；简单脚本与完整投入仍独立评价。

局部相关15项检查通过；本机系统Python和旧`.venv`缺少pytest，改用已安装pytest的
Miniconda Python完成检查。没有因此修改环境依赖或重复运行全量回归。
旧推送 `18c93a0` 的Ubuntu CI为3272通过/21失败/30跳过，失败仍涉及旧发布库代码锁等；
Windows也失败。局部检查不能替代全量回归，草稿PR不合并或部署，不改证书摘要求绿。

### 正常后继与同题开发复验（2026-11-10）

Task13正常对照使用相同题面/素材/媒体测量哈希、镜像、适配代码、系统提示、模型、输出
上限、900秒诊断墙钟和四项工具schema，仅目录为认证Store或空Store；实际一致性已核验。

| 运行 | 请求 | 参考估费USD | 秒 | 官方分 | C调用 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 冻结Reuse `task13-normal-video-reuse-001` | 8 | 0.00600544 | 453.89 | 0 | 0 |
| 冻结Baseline `task13-normal-video-baseline-001` | 8 | 0.00292370 | 303.53 | 0 | 0 |
| 修订提示开发复验 `task13-reuse-choice-development-20261110-001` | 9 | 0.00641298 | 326.46 | 0 | 0 |

三次都交付MP4/JSON。旧Reuse重写633字节edit.py；Baseline在内联Python中重新累计时间；
开发复验同样内联重写，另手调末段终点。未观察到少写程序或自主C采用；两侧都0分不构成
合格任务上的同质降本。复验明确为已暴露Task13的开发运行，不是新未见评价，不从后继学习。
后续默认提示已删除必须重新实现的冲突，先核对现有接口、只补缺失行为，仍允许不采用。
真实复验表明，仅该提示修订没有解决本次未采用，不重复同策略付费试跑。

原Runtime零模型适用性检查 `task13-applicability-diagnostic-002` 用旧Reuse真实未改配置
成功执行C，输出与其自写程序最终JSON逐字节相同（`68f006d3…2a553a`）。它覆盖本题4个完整
片段的累计时间线，不锁素材ID、固定段数或实例路径；裁剪不在该程序接口内，本题也未要求。
目录仅1候选，没有候选排序或训练顺序导致漏选的证据。开发复验的末段终点手调尚未独立验证
为必需行为，不据此预写更通用剪辑器。首次适用性诊断把原输出虚拟路径误写成多层目录，
原Runtime正确拒绝；修正为其既有 `/work/outputs/<name>` 后通过，旧失败记录保留。

学习流程还有独立缺口：实际c2f332b Runtime的Artifact编译保留原source与首例IO shape；
本场景直接调 `advance_execution_learning`，未接原 `advance_normal_task_learning` 的
`parameter_learner` 和实际采用反馈。通用程序形态目前主要依赖普通Agent首次写法，而非
该场景主动完成上下文分离。实际四个相关源文件SHA已与原件一致性核对。
`representation-audit-20261110-001` 给出具体表示反例：源码的manifest_name有默认值，
删除真实输入中的该可选字段后，原程序仍正确生成相同JSON，但原契约精确shape拒绝输入。
这不是原Task13未采用的原因（其字段存在），却证明首例契约可能缩窄真实复用域。
证据已交绘图侧牵头公共参数学习修复；本分支不并行改公共模块、不修改旧C契约或证书。

本轮局部来源/认证/三次正常视频运行合计39请求，38次已知参考估费USD0.02315255，
7002未知预留USD0.0659239另列；模型诊断/编码/评分合计1467.89秒，不含排队和开发人工。
旧开发失败、模型探测、其他线程及历史未知费用仍在原累计账本，不包含于该局部小计。
最新自有收尾为7042/累计代理记账USD101.77228817，非Kouri实付，后续读共享账本现状。

### 公共参数学习接线与首次正常采用（2026-11-10）

新实验根`efficiency-si-agentic-vbench-method-20261110-v1`，不覆盖旧库或旧失败。
`learning.py parameterize`仅向原`learn_pending_parameters`提交独立局部合格的正常来源，
拒绝封存后继和完整视频失败来源，不另造参数学习器。公共研究Runtime基于`c2f332b`，
包含公共参数学习修复、`ad1834a`、提案转义兼容`e50c7e7`，最终归档`a073381`；
既有Luna路由/费用适配另记于服务器`runtime-method-v2/source-manifest.json`。

真实参数学习`results/parameter-learning-001`为1请求7046、7.569秒、参考估费USD0.001295，
明确返回`no_change/no_parameterizable_boundary_selected`。原程序已通过JSON传入当前选择，
本次不能声称发现新参数算法。按事前政策，Task2来源及Task6独立认证原轨迹在新Runtime
重新提取/认证，再冻结原程序。源SHA仍为`fdb9bdb3…05d2`；file/value两入口属于同一程序。

value入口初次零模型重放的真实失败是`dependency_binding_mismatch`：实际JSON参数在文件
物化前没有对应依赖证据。公共修复在原授权摘要校验后冻结参数，并以真实任务/grant绑定的
参数SHA建立`task-arguments`证据；保留文件变更、撤回、参数篡改与非空依赖守卫。旧失败
重放和Task6真实配置均通过，新JSON结果与原输出逐字节一致。这是兼容性修复，不是实际
模型采用，也不是放开subprocess/cv2或增加媒体后端。Linux定向18通过/1平台跳过。

真实工具检查排除了旧猜测：请求中完整存在所有参数，Harness按名称排序后的wire顺序为
`capability_call, capability_list, execute, read_image`，不是注册顺序；场景现在读取原请求
记录实际schema/hash并检查跨请求一致性。不能把早期未采用归因于缺失schema。

另两项普通工具质量修复来自实际执行反例，而不是答案：

- 旧Task13 Reuse的异尺寸thumbnail混用`tile`，原JPEG及重现SHA均为`e747b94f…10aa7`，
  只有4/12格非黑；先分别归一后12/12可见。联系表必须有实际ID和采样时间，不能由格位推ID。
- 媒体输入原`duration_seconds`是容器时长，可能包含尾部音频。现在保留旧字段并提供明确
  `video_duration_seconds`及codec/timebase信息。旧VFR拼接的平均帧率使cv2请求约2.42秒却
  返回约1.70秒；顺序读取像素本身接近原片，单改几何未修复。普通输出改为在混帧率时
  显式CFR并核验时间对应，不改官方校验器。详见`results/encoding-timebase-control-002`。

这些普通提示和输入改进同时给予两侧，不能计入Motif收益；旧Task13全部结果不变。

新Task14按下一官方编号选定，早于读取题面/素材/答案，角色已固定在`method-roles.json`。
9份素材与旧Task2/6/13逐字节无重合；Task14 ZIP SHA为`74d61b72…11fc18`，镜像ID为
`sha256:f01524cf33fbf9e0e856282b71f5dc34ad43b091c178949c2ab4794fceb53152`。
冻结证据在`inputs/task14-freeze.json`，库snapshot digest为
`d2514674f7fecd89c9caf6ec0b702ac571fff131e7646212ae49650437f2cbd2`。
代码`19c8b54`、Runtime`a073381`、Luna/none/128000、不限费用/次数、900秒/侧，
同题/素材/镜像/普通提示/工具；Reuse冻结库与Baseline空库，value入口两侧同开。
Task14保持封存后继，禁止用于提取/参数学习；同题重测必须标开发，不能再报独立未见。

| 运行 | 请求 | 参考估费USD | 秒 | 官方聚合结果 | C调用 |
| --- | ---: | ---: | ---: | --- | ---: |
| Task14 Reuse `task14-reuse-pair-v2-001` | 12（7047–7058） | 0.01473711 | 637.8282 | reward0；3槽位/1匹配/1内容校验通过 | 1成功 |
| Task14 Baseline `task14-baseline-pair-v2-001` | 9（7070–7078） | 0.00832075 | 236.1264 | reward0；3槽位/0匹配/0内容校验通过 | 0 |

Reuse实际采用file入口`cap_0ed0196ad1b442d335107ac9`，并未采用可选value入口。
正常Agent只写当前`instance.json`，没有重写清单算法；原Runtime生成483字节清单，
SHA`50fee4359660884b4c10f2df0b55cb22d054a58833fde2ef314db9c516fba183`，
与最终`solution.json`逐字节相同。实际MP4为3182779字节，SHA
`eed209758b7f9b928da8c25844a0bc69f7ee8c69d722fad6ce6efd4c3548acd9`。
原生工具回执还带同源程序SHA，不把封装内部执行记成模型重新写码。
证据在`results/task14-adoption-audit-001/audit.json`及原调用Runtime trace。

这是首次真实后继自主采用并实际交付，不是零模型强制调用。选片依然未满足官方质量门槛，
reward0不能写成“全部槽位错”或“无法渲染”；也不能把局部正确当完整成功。只读官方聚合
计分，不读取新题正确ID。Baseline随后按原冻结条件完成；真实模型/普通题面与系统策略/
素材/镜像/元数据/代码/工具schema及实际排序均一致，整段prompt哈希仅因附加认证目录与
空目录`[]`不同，mode标签按预期不同。审计先误将这两项预期差异判为不等，修正检查对象为
同一普通提示加独立目录差异后通过，未重跑模型、未追改原记录。

配对只读审计`results/task14-paired-audit-002/audit.json`：Reuse187125输入/4068输出token、
缓存hit66771/miss120354；Baseline124680输入/3104输出、hit63325/miss61355。
21请求均HTTP200、用量完整，无未知模型费用；Kouri实付仍未取得。Reuse观察费用高77.1%、
耗时2.70倍、请求多3次，没有前向降本。两侧都经历PIL缺失后的普通工具恢复；Reuse另有
再次编码等实际工作，不能把总差异简单归因于C接口，也不能以两个0分认定质量相同。

无需Oracle的后置局部检查，从各自最终选择的source ID及实测视频流时长派生检查输入：
Reuse清单算术通过；Baseline直接写清单数值并手调末段终点，触发`output_duration_mismatch`。
这是局部可靠性证据，不是选片合格、完整视频成功或新的认证来源；后继仍禁止用于学习。
Baseline视频/JSON真实存在，JSON SHA为`802780ab…5dacb`，MP4为`e2d86160…37c55a`。
本次自有收尾累计7078/代理记账USD101.81028606，含原历史及他侧用量，非本轮实付。

公共Runtime的`ad1834a`归档全量回归为Python3443通过/30失败/23跳过；独立Node1712通过/
1失败/8跳过。Python失败为19项发布库相关、4项PDF/Harness、6项管理/OCR与1项deadline；
Node唯一失败明确为旧Paper发布库`certified runtime code changed`。不能报绿，亦未改证书
求绿；deadline项单独复核1通过。最终`a073381`额外包含提案转义兼容，不将先前归档的
全量结果冒称最终归档的重新全量通过。
新核心代码与场景代码分开交付，未合并/部署。场景定向20项通过；全量结果不因此改绿。

### 原计划Sequencing适用性准备

`sequencing-roles.json`事前固定task2（7段）→task1（13段），仅依据原计划任务及公开输入
规模，不按得分选题或替换。继续同一C/Runtime及普通提示，每侧900秒，原费用/次数不限
与累计账本，先Reuse再空库。没有使用测试题修库，也不等待可选值接口；不扩Repair/Repurpose。

零模型`results/sequencing-interface-preflight-001/preflight.json`核对：两题确实要求每个
片段完整使用一次、连续半开区间，与现有清单接口兼容；原程序按clips迭代，原输入契约
不锁列表长度。task2全部1920×1080/25fps，task1全部1920×1080/30fps；官方素材ZIP SHA
分别`a03b2aaa…0251d`、`657db511…cd0e4`。直接HF下载连接失败保留在prepare001，沿既有
mirror路径下载并与官方SHA逐字节核验后成功（prepare002），不是换素材。
原两题环境recipe仅材料URL/SHA不同；在既有原Sequencing镜像上替换材料层，不改依赖，
新镜像ID分别`sha256:cd45a88ad26319c6ac56f90deddfc3e316a52d659acd3a141ec5cb3069ae7262`、
`sha256:49c33d41946c0bf836a1f0911b666ced681ac663f7828e1059c7e43b13168941`。
此处仅为接口与环境检查，不是正常采用、正确顺序或视频质量证据。两题素材与旧Assembly
Task2/6/13/14均无相同文件SHA，见同一预检目录`prior-material-overlap.json`；这不证明
底层影片语义完全不重合。正式求解未读取Oracle。

7段冻结对照已完成；两侧完整相同条件检查及后置用量见
`results/sequencing-task2-paired-audit-001/audit.json`，当前13段仍待原定窗口。

| 7段运行 | 状态 | 请求 | 参考估费USD | 秒 | 官方位置/内容校验 | reward | C |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| Reuse | completed | 13（7089–7101） | 0.01157220 | 683.60 | 2/7；7/7 | 0.06944444 | 0 |
| 空库Baseline | 900秒超时，成品存在 | 9（7111–7119） | 0.00629177（后置核账） | 940.34（含退出/评分） | 1/7；7/7 | 0 | 0 |

Baseline原`result.json`费用为null：最后请求7119在取消时下游断开，原摘要写入时未取得
结算；实际进程退出后原连续账本已经记录其HTTP200完整用量及USD0.00063792。只读审计
保留原null摘要，另按原账本9次已知值求和，不回写旧记录或手动改预留。全部9次现均已知，
Kouri实付仍未知。Reuse输入/输出200992/3979 token，cache hit/miss116850/84142；
Base112954/3503、hit/miss75057/37897。

取消时序另存`cancellation-accounting.json`：7119的请求文件在首事件后899.597秒创建，
900.201秒已关闭自有Runtime。账本`request_utc_epoch`实际在响应结束记账处赋值，不能当作
开始时间；其920.19秒是上游晚结算，不是900秒后新发请求。旧快照、取消与实际费用分开。

两侧均未采用C，故任何排序、时长或费用差异都不能归为C收益；未达到完整排序质量。
Reuse费高83.9%，实际总时长较短，但对照超时且质量不同，不作同质效率比较。13段按
预先角色及相同原C继续，不重跑7段追求命中，不在配对中修改库或提示。

### 成本累计口径

以下是互斥阶段的真实模型投入，不能只报后继一次调用。`已知参考价`不是账单实付；
未知请求保留原账本预留，不能当作实际费用，也不能记零。开发维护人工与硬件成本未独立
计量，故不能给出完整净收益或准确摊销次数。

| 阶段 | 请求 | 已知参考价USD | 用量未知的原预留USD |
| --- | ---: | ---: | ---: |
| 初始未学习预检 | 19 | 0.10734120（18次已知） | 1.37418720 |
| 两次DeepSeek来源失败 | 14 | 0.04755240 | 0.85112340 |
| Luna连通性检查 | 3 | 0.00174070 | 无 |
| Luna正常Task2来源及同题修订 | 28 | 0.04186369（25次已知） | 0.45524200 |
| 局部正常来源/独立认证 | 14 | 0.00781043（13次已知） | 0.06592390 |
| Task13两侧及同题提示开发复验 | 25 | 0.01534212 | 无 |
| 原参数学习，明确no_change | 1 | 0.00129500 | 无 |
| Task14冻结两侧 | 21 | 0.02305786 | 无 |

本表不覆盖全部共享账本：原始响应探测、其他线程及历史费用仍在原累计账本，未清零。
已知正常来源28次、局部来源/认证14次及参数学习1次合计43次；这些投入不能在前向比较
中消失。零模型提取/认证/回放仅表示没有新增模型请求，不表示开发维护免费。
当前比较是认证库对空库，尚未形成同质量下对简单保存脚本/缓存的额外收益结论。

### 稳定程序边界诊断：已学会累计，未接管媒体执行

Sequencing task2 Reuse已按预先条件完成，13请求7089–7101、683.60秒、参考USD0.0115722，
C0。官方位置正确2/7，内容一致性7/7，ordering/reward为0.06944444；完整排序未合格。
空库对照随后超时，结果与成本见上一节；不重跑该题求采用。

真实Agent先写当前`instance.json`，随后另外写同一选择的`concat.txt`并执行ffmpeg；
之后用内联Python重新累计清单，又按25fps改写区间，最后手调终点到45.04秒。
原C仅累计这7段完整视频时长，结果45.0秒。为区分必要行为与主观补丁，
`results/sequencing-task2-applicability-001`用**原Runtime、原C、该次真实未改配置**做零模型
事后适用性检查，复制原MP4，只替换诊断副本清单，再跑原官方评分。C执行成功、源SHA仍为
`fdb9bdb3…05d2`；原成品和诊断副本均为相同2/7位置正确、7/7内容校验通过及相同reward。
这证明本题末段手调不是维持原官方分数所必需，不能据此把未采用归为实质不适配；
原成品/评分保持不变，诊断不计作正常采用、独立样本或修复后的成功。

目前证据区分如下：

- **已经验证**：文件入口在Task14正常采用过；同一原C可处理当前7段，既不锁4段，也不需
  当前选择的特殊算法。Task2没有调用C，因而不存在该次调用被Runtime拒绝的证据。
- **尚无证据**：没有明确的工具拒用说明，不能断言未采用由接口难用或候选排序导致。
  Task14与Task2实际表现不同，也不能用单次采用把提示修订认定为唯一原因。
- **有代码依据的收益瓶颈**：目前C只负责清单累计。普通两侧仍需给出当前镜头/顺序和时长；
  该JSON本身不会因C而消失。Task14空库可直接写约482字节清单，Task2可用短内联循环，
  不能把历史1344字节完整源文件全部记成节省的模型输出。目录又增加每次请求的上下文；
  “C边界过小、其余稳定工作仍在模型侧”是当前最有支持的收益解释，仍非自主拒用的因果证明。

尚未进入C的最大重复执行段是：由当前片段计划生成concat/filter参数，处理帧率/音频和
时间轴，编码、导出并探测实际产物；两条真实轨迹都重写了这一段。视觉采样的布局/标签/
文件路径也有稳定部分，但“选哪段、动作是否符合、哪些证据足够”仍是当前语义判断。
复用不能省掉实际编码CPU成本，更不能冻结旧片段选择；目标是少写和少协调重复执行，
在保留核验与恢复的情况下跳过模型工作。

核对冻结研究Runtime`a073381`及既有业务实现后，当前边界不是再加一句“用C”能解决的：

| 既有路径 | 代码依据 | 可承接与当前缺口 |
| --- | --- | --- |
| Artifact | `artifact_motif_compiler.py:MODULES/validate_source/file_contract` | 可写小数据/文本；subprocess/cv2不准入，文件契约有界UTF-8，不能直接把当前ffmpeg或视频字节塞入C |
| Script | `script_motif_compiler.py:IMPORTS/FORBIDDEN` | 只读受限程序，不能承担写成片与媒体子进程 |
| 当前Benchmark适配 | `benchmark_script_materials.py:_run`、场景`learning.py` | 原生准入/执行只接受Script/Artifact；普通execute中的shell/ffmpeg不是已认证媒体能力 |
| 原Source路径 | `source_program_compiler.py:compile_source_program`、`source_capability_runtime.ts` | 接受真实TSX/JavaScript来源，既有worker走Remotion `program_server.render_program`，有实际产物回执；不是任意shell/ffmpeg后端 |
| 原Remotion学习/认证 | `structured/learn_programs.py:collect`、`certify_programs.py` | 要求正常write_source/render_source、冻结TSX/视频SHA和独立渲染检查；可复用更完整的构图与渲染程序，但当前shell轨迹不满足来源证据 |

最小修复方向分两层，当前冻结配对不改：先让后续**正常开发经历**在同一数据程序里产出
实际用到的清单与有序concat等小文本，仍由普通工具执行媒体命令；程序、接口和选项由Agent
依当前任务产生，再走原提取/独立认证，不手写目标C或把测试题回灌。这可扩大现有Artifact
边界，但还不能声称接管完整渲染。若要复用完整稳定媒体执行，应优先使用已有Remotion
Source的正常创作→认证→执行闭环，取得真正的TSX来源与新质量证据；当前Benchmark的
Script/Artifact适配不能直接消费Source，不伪装旧ffmpeg轨迹、不开放subprocess、不新造
剪辑引擎。是否迁移场景由公共方法/场景路线决定，不能把迁移或普通工具优化算成同一
冻结对照中的Motif收益。

### 下一阶段的正常材料视图（尚无新程序或收益）

13段Reuse已在普通媒体重编码阶段超时：8请求7129–7136、参考USD0.00517916、911.38秒，
最终目录为空、官方reward0/C0。原账本provider耗时合计92.844秒；普通execute在约185秒
即开始把151.23秒1080p源按medium/crf18/fps30重编码，未进入清单交付。不能把900秒都写成
模型推理慢，也不能由未到达清单阶段推出明确拒用C。当前仍按原条件完成13段空库侧。

在不改当前冻结运行的前提下，下一阶段已零模型核对一个真实输入契约问题：原`media.json`
按每个文件名作顶层键，原`file_contract`因此记录12个实例键；同一真实Task2测量去掉未用
条目形成3条的控制子集后，原TypeScript matcher拒绝。这是材料表示把实例ID当字段，
不是正常程序必须固定素材数。

新隔离根`efficiency-si-agentic-vbench-plan-20261110-v1`的
`results/media-array-contract-audit-001/audit.json`使用原Task2镜像和原probe、原Python
契约及原TypeScript matcher：map12→map3不匹配；将同一批测量无损写为正常行数组，
文件名放在`name`值中，其余字段原样，array12→array3匹配。逆变换与原测量完全一致。
这只证明表示/契约兼容，不是认证、实际采用或任务质量；没有从封存后继学习，没有放松
旧契约/模块限制，也没有让模型手抄元数据生成适配文件。

本地新场景版本已在原材料准备处保留旧对象文件、增加只读`media-records.json`和来源SHA；
后续两侧共用，普通数据程序可直接读测量并按当前ID/顺序查表，避免反复抄写duration。
它属于普通输入准备改进，不能计入Motif收益。22项场景定向检查通过；当前服务器冻结
场景仍为19c8b54，未同步覆盖正在进行的13段空库侧。

新版本还在最终清理后再次观察原Gate费用，前置快照保留；晚结算仍未知时继续null并由
原账本后置核对，不推定零费。没有修改SDK关闭策略：实际取消已在900秒发生，先前
`request_utc_epoch`的误读已由真实请求文件时间和事件时序排除。

### 13段配对收尾与媒体时钟诊断

13段空库侧也已结束：9请求7137–7145/USD0.01603627/909.31秒，900秒超时，仅有MP4、
无JSON；Reuse为8请求/USD0.00517916/911.38秒，最终目录空。两侧C0、官方0，失败形态
不同，不能判等质或称C降本。配对审计在`sequencing-task1-paired-audit-001`。

为区别CPU负担和数据计划错误，另做零模型反事实，沿用Reuse真实Actor顺序、实际材料、
原C1清单和普通FFmpeg，只在新诊断副本操作。普通stream copy 3.454秒、7/13内容校验；
唯一改变为concat每个file后增加实际video_duration_seconds，2.603秒、13/13校验。
排序仍0/13，reward=.0173992674，未修选片。两次分别保存在
`sequencing-task1-copy-diagnostic-001`和`sequencing-task1-copy-timing-control-002`。
这是研究者辅助的可行性诊断，不是正常Agent完成、学习或自主采用；不改旧结果，也不把
普通CPU策略收益归给Motif。相同codec/分辨率/fps乃至extradata不足以证明容器时钟兼容。

### 正常经历扩大的数据计划边界与独立质量

新研究根`efficiency-si-agentic-vbench-plan-20261110-v1`先在`plan-roles.json`固定：
原Task2开发、不同材料Task6认证，之后Assembly15先真空库后复用、Sequencing3先复用后
真空库；两族用同一冻结新代，不用后继修库。旧C保留。数组视图、codec/header测量、
普通媒体指导与文件接口两侧相同，不能算学习收益。Runtime仍`a073381`及原Luna适配；
没有引入其他线程后续kwargs候选、新Agent、矿工、Source迁移或媒体执行器。

| 同一Task2正常开发阶段 | 请求 | 参考USD | 秒 | 原提取/实际问题 |
| --- | ---: | ---: | ---: | --- |
| source-001 | 9（7151–7159） | .00919664 | 190.97 | Artifact0，程序实际调用混在媒体复合命令中 |
| replay-002 | 9（7161–7169） | .00454956 | 233.93 | Artifact0，新目录不在原outputs域；后又将MP4拷入code污染有界快照 |
| feedback-003 | 10（7171–7180） | .00863168 | 270.88 | Artifact1；原Actor改视频时钟、单独真实调用、媒体留媒体树 |
| 合计 | 28 | .02237788 | 695.78 | 一个开发经历，恢复成本全部保留，不算三份独立样本 |

原生零模型布局预检`normal-plan-layout-diagnostic-003`使用未改的002源码/配置，在同一
原native工具真实Docker执行并由原collect提取Artifact1，完整前后边界，Store写0。
之前两次诊断因tsx路径/研究runtime无native模块而未启动执行，失败原样保留。
容器`outputs/*`映射宿主`workspace/outputs/code/*`；没有改原fresh-output或模块guard。

新正常程序SHA`08f511b3da8e5b72e8c530a5bd63766be5a64750cf5488f1d9f26759a2bc545a`，
原提取ID`artifact_b5945b9982bb51dabff3d824`。入口读取实例、测量数组和新输出目录；
实例仅当前IDs与输出选项，不复制测量。稳定处理按ID从现成数组取路径/视频时长，产出
同一时钟的manifest与带duration指令的concat。当前正常选择仍1、7、8、5，不是Oracle。
它不生成完整编码argv、不执行媒体，语义选片、策略判断和FFmpeg仍由普通Agent/工具负责。
引号域只验证现有数字文件名，未宣称一般路径转义。

独立检查器`plan_quality.py`与`plan_evaluation.py`明确分开数据一致性、真实消费与视频质量。
`task2-plan-quality-004/qualification.json`绑定真实call-8所产两个文件、call-14成功的
FFmpeg输入与生成manifest交付、Actor声明的实际项目目录；所有4段各3次通用SSIM采样
通过，最低.9976，829/829帧完整解码、24fps视频时长34.5416667秒与manifest终点
34.541667一致。只从官方checker AST取五个通用帧函数及三个数字常量，不执行score/main
或读取预期排序。这是配置项目视频内容/时钟检查，未验音频或官方选片质量，也不是盲评。

Actor此次交付在`output/task2-normal-plan-source-replay-003`：735字节生成manifest
SHA`5ac2e1af...51b071`、新MP4为16760895字节。根级632字节旧manifest/旧视频仍在，
原trial结果保持`pending_independent_plan_checks`，不将根级旧交付误记为新计划输出。
新`qualify-plan`只重验独立报告、输入/输出/边界SHA和数据检查，并在新的
`task2-plan-qualified-003`附上配置项目准入；原候选源码、原提取、旧trial结果均不改。

`source-plan-freeze-001.json`在独立Task6前固定程序、实际双JSON接口、检查器与新角色。
Task6普通Agent只选择三份当前素材并写当前配置，源码不改，实际用生成计划渲染成片；
完成后同一独立检查和原`advance_execution_learning`认证/Store。此时尚未注册新C，
也未消费新后继。29项场景定向Python检查通过；全量/托管CI此前失败仍在，未宣称全绿。
源恢复、独立认证、维护与失败全部计入完整学习成本，不能只比较后继某个短调用。

独立Task6首次正常认证经历已实际结束：7请求7188–7194/USD.00572676/84.47秒。
未改源码的原提取Artifact1；三份新素材1/3/5的数据计划、真实消费、内容采样均通过
（最低SSIM.9937），但冻结视频时钟门槛拒绝：源总259帧，实际CFR输出261帧/24fps，
10.875秒对计划10.791667秒，多2帧，超过预设1帧容差。未注册新C，后继未消耗。
已知当前素材3/5的视频起点.041016秒、1为0；显式片段duration不自动清除输入PTS偏移。
因此新计划也不能被描述为通用正确copy时间轴，普通媒体执行仍负责时戳处理与验证。
保留质量失败、原准入拒绝及误提前调用原认证因缺少合格held summary而失败的记录。
后续仅在未改源码/选择/冻结门槛下调查普通媒体恢复，所有恢复计同一次认证任务。

Task6零模型媒体控制保留两次结果：001将视频按解码帧序号重建24fps时钟，但输入frame
metadata变化触发滤镜重置，计数器重启，实际仅165帧、6.875秒、内容2段失败。
002保留同一concat/manifest和编码画质策略，同时对已测同几何/同24fps输入关闭滤镜重置，
得到259帧、10.7916667秒、原内容/时钟检查通过；使用等价fps_mode语法替代deprecated
vsync。追加逐源、无窗口择优的全部帧一对一SSIM：97/99/63帧全对应，最低
.995436/.993787/.993118，输出无额外帧。原程序未改，未截断、未修改manifest、未注册。
这仍只是普通媒体诊断，不能直接当正常认证成功，也不适用于混帧率假设。
之后恢复仍是同一个Task6认证任务，保持原三ID、08f511b3源码和冻结质量门槛，普通Actor
重新实际执行媒体处理；费用包含初次失败和恢复，不能记两次独立认证。

### 同一独立认证经历的恢复与新代冻结

Task6正常恢复002实际结束：5请求7200–7204/USD.00389822/67.13秒，保持原1/3/5配置与
08f511b3源码。普通Actor自行修复FFmpeg参数位置错误后完成视频，manifest SHA仍
81526052...65cb43；但其Python调用合在复合shell中，该恢复的原提取正确为Artifact0。
无需为已存在的首次真实producer继续付费重复捕获，也不重写parser或拼造见证。

`task6-plan-quality-associated-003`仅将同一canonical Task6首次Artifact producer的独立输入/
源码/manifest/concat，与恢复媒体前的实际小文件边界逐SHA关联；两次题面、素材与测量、
配置、镜像/模型一致。恢复真实FFmpeg消费同字节计划并交付，完整259帧/24fps、3/3内容
和视频时钟通过；生成的帧检查worker与首次冻结文件字节完全相同（SHA c34acbf4...606041），
数据检查器也未改。这里只增加同一经历的恢复质量证据，原失败/原pending结果均保留，
不是第二个独立认证样本，也不将普通时戳指导计入C。只读消费审计支持实际成功shell行中
的字面路径赋值，不执行shell或为原学习器提取候选；未知展开不接受。

原`advance_execution_learning`以Task2真实source和Task6首次真实Artifact独立输入执行，
原native认证`published1/rejected0/model_requests0`，并在原Store登记新文件能力
`cap_c00a00710fd40c01fd9a752e`。原程序仍是08f511b3，只生成小计划，不执行媒体或选择
正确镜头。Task6首次与恢复合计12请求/USD.00962498/151.60秒；新源开发加认证40请求/
USD.03200286/847.38秒，更早失败、旧认证、零模型CPU和人工维护另计，不能只报一次成功。

两个后继任一侧运行前固定`successor-generation-freeze-001.json`，SHA
4d664de64abf9ab8a928937fc7c333c9d740b2fbc8614144add3c78e5b5e3a62。
增强库snapshot089ba3ea6bcccf7a152298d4e9810d5c6d16f530bcac00c8a7c4f20106b1bfc0，
含旧清单C和新双输入计划C；Baseline为同owner真空库snapshot5984c144...c6238d。
同一`scene-plan-v3`/v6数组与普通PTS提示、四工具schema及文件接口，两侧唯一计划差异为
冻结目录。Assembly15空库先、再复用；随后Sequencing3复用先、再空库。C可选，不从后继
学习或修库，继续原累计账本，Luna/none/128000、费用/次数null、每侧900秒。

镜像仅替换已有环境的公共材料层，版本、ZIP和image SHA均存
`inputs/successor-image-preparation.json`：Assembly15 ZIP SHA33221c3c...a0e171，响应
数据集commit66b983e7...6fa945；Sequencing3 ZIP SHA70466a33...b1b77与官方固定SHA一致，
数据集commit00e704c2...888d3。没有读取答案/排序，镜像制备不算模型任务成功。
此时新后继仅Task15空库单侧已启动，尚无新代采用、质量或效率结论。32项场景检查通过，
托管CI以当前Checks为准；未合并或部署。

## 冻结代四侧结果与下一断点（2026-11-10）

同一 `successor-generation-freeze-001` 的Assembly15空库→Reuse、Sequencing3 Reuse→空库四侧均完成。共同题面、素材/测量、模型/输出上限、系统提示、工具schema及顺序、镜像/依赖、墙钟和预算条件逐项一致，目录是预定差异；两Reuse各尝试一次新C，原Runtime均拒绝 `artifact_input_contract_changed`，继而普通回退。未发生成功新C采用。

| 后继/侧 | 请求 | 参考USD | 秒 | 原官方结果 |
| --- | ---: | ---: | ---: | --- |
| Assembly15 Base | 17 | .02027324 | 367.42 | 1/3正确且内容通过，reward0 |
| Assembly15 Reuse | 14 | .01564954 | 257.80 | 0/3正确，reward0 |
| Sequencing3 Base | 18 | .02317115 | 480.19 | 4/10位置、10/10内容，reward.05777778 |
| Sequencing3 Reuse | 12 | .00948587 | 382.01 | 2/10位置、10/10内容，reward.02488889 |

四侧61请求/USD.06857980；仅与新源开发/认证小计相加为101请求/USD.10058266，仍不含更早失败和维护/诊断完整成本。费用是原累计账本读取的参考估费，非Kouri账单；没有把未知算成零。只读配对审计完整保留两侧产物SHA、真实调用/失败回执及计量。另对各自声明片段做媒体校验，Assembly双方3/3、Sequencing双方10/10内容及实际完整解码/时钟通过；这不修复镜头选择/顺序质量，也不形成独立盲评或质量等价结论。不能把Reuse请求/费用下降写成C带来的效率增益。

断点可由原Task2源数据独立重现：源码支持输出选项缺省，但旧JSON对象键观察要求该键始终存在。新公共提交 `2f8586e` 在独立研究owner修复原编译/认证/TS匹配；程序仍由普通Agent写出，SHA08f511b3不变，不手写目标C、不放开对象、不靠提示补齐键。原Task2/Task6重新提取与原独立质量证据通过，再由原认证发布新C81447ad6。逐项/联合缺省受控执行、真实工具交付链及未知/必需项失败均有零模型证据；该验证是工程控制，未冒充自主新任务。

公共完整说明见该提交的 `docs/debug/artifact-json-defaults-20261110.md`；此文件位于独立公共owner Git对象库，不代表场景PR165已包含公共链。新一代先审具体冻结输入/质量/成本条件，再仅做一对“固定决策后的剪辑执行阶段”对照；顺序由独立预先规则给定，不由Oracle/人工答案取得，不与原官方语义任务成功混同。新增付费目前暂停，未合并、部署或服务重启。

## 新固定决策任务：已真实复用，等质净降本仍未成立

在上述公共修复与原Task2/6实际调用/成片控制通过后，封存一对新的固定决策后执行任务。
借用Assembly16的9份公共素材（数据集revision66b983e7…6fa945，逐文件SHA随冻结记录），
在看素材内容前规定按文件名1–9升序拼接全片。这是明确给定的剪辑请求，不是原官方故事板
或排序答案；两侧不读Oracle、不学习后继、不强制C。新素材与来源/认证素材零字节重合。

冻结SHA6e4b06ee…6ac9f3；双方同2f8586e公共Runtime、三份既有Luna传输覆盖、
同scope/owner、输入JSON和无损测量、工具schema与顺序、共同提示、900秒及费用/次数null，
仅单当前认证C与原真空库不同。Base先、R后，原账本不重置，没有额外通用框架要求。
两侧均实际exit0；原求解结果和产物不修改。

| 指标 | 空库Baseline | 单C Reuse |
| --- | ---: | ---: |
| 真实请求 | 7（7321–7327） | 8（7328–7335） |
| 原账本参考模型USD | .01037170 | .00640950 |
| 端到端秒 | 181.96 | 209.96 |
| prompt / completion token | 94269 / 2336 | 83797 / 2185 |
| cache hit token | 2480 | 34030 |
| C实际调用 | 0 | 1成功 |
| 原清单/成片质量 | 未通过：缺output字段 | 通过：9段、464帧 |

R原C源08f511b3未修改，最终清单SHA b3ff6798…5813与native产物/导出逐字节相同；
模型没有重写这部分时间线计算。固定IDs/顺序、完整视频区间和连续manifest通过；
9段×3采样SSIM最低.9965，原冻结worker完整解码464/464帧、24fps、19.333333秒，
与manifest19.333008秒差小于一帧。Base最终JSON使用start/end而没有要求的output；
原清单检查失败，原帧worker也因缺键退出。未将该失败写成视频像素已经不合格，未人工
改键后充当原自主通过，也没有用同为“完成”掩盖验收差异。

C的concat仅用于前期尝试；最终R视频是Actor另外组织filter_complex concat后编码。
因此确定被复用的是测量读取/清单时间线，编码/PTS组织和恢复仍耗模型，不把早期concat
消费说成最终完整编码链复用。B和R都发生媒体修复，全部请求/耗时保留。

观察模型参考费低38.2%，请求多1、耗时高15.4%；不能据此称等质量效率收益。两侧cache
不同；按同冻结价格将全部prompt按miss诊断重估为B.01059490、R.00947220，差10.6%，
只是拆分cache影响的参考计算，不是供应商账单或另一轮实验。双方费用已知，历史未知
仍保留。当前两臂15请求/USD.01678120；加此C源开发/认证为55请求/USD.04878406，
再含上一代四侧为116请求/USD.11736386；更早失败、未知预留、CPU及人工维护均未消失，
不能把本小计当完整研究净收益或用一次差值宣布已摊平学习成本。

审计task16-execution-paired-audit-002逐项核对共同条件和实际原回执。001误调已有四参
plan checker的arity错误保留；002沿已冻结三参manifest checker，用固定意图与原测量
形成独立期望输入，不从成品反推期望；原数据阈值/帧worker不变，不额外要求Base生成
concat作为交付。仅完成这一对，付费窗口已释放；没有同题修复重跑、扩样、合并或部署。
下一步须围绕明确的manifest接口和仍然重复的媒体时钟/编码负担设计新代，不能靠放宽
质量标准、手写目标C或持续试题取得正例。

## 同一B的一次正常恢复：合格交付的次级成本分析

原主配对结束及002结果封存后，先声明以下次级规则：任何不合格臂至多获得一次原检查
反馈后的同任务正常恢复，费用、请求及耗时与原阶段累计；合格臂保持原交付/成本。
本例只有B不合格。反馈仅为原missing output错误和原任务字段规范，没有R清单、数值、
代码或人工文件修订；沿既有continue-trial/followup及fresh原SDK会话/自己的工作文件。
它是同一个B的恢复，不是新未见样本、主配对重跑或从后继学习。原主评分保持失败。

恢复先冻结92989585…848f3b，场景91ed04f及40项定向检查通过。显式恢复报告绑定原B
manifest/测量SHA、同goal/task/model配置/runtime/native工具、固定执行scope及原空库
snapshot；旧development保护与sealed学习拒绝保留。时间上限为原900秒减181.959722秒，
余额718.040278秒；仅一阶段，失败也停止。等待绘图35实际退出、明确交回后才启动。

实际恢复10请求7356–7365、参考USD.00613510、143.88543秒、C0，正常退出。Actor自行
读自己的文件并修订清单/媒体；没有手改交付。恢复清单SHA a8198755…45e8fea4，
视频SHA5aa6dfe5…74b20fff。原冻结数据/帧checker通过9段采样及464帧完整解码/时钟；
B实际平均fps24.05183585、R24，按原一帧门槛通过，未为结果改门槛，不声称像素/时间
完全相同或做过独立盲评。R原视频/清单、检查及费用逐SHA保持；主配对/002不重写。

| 合格交付成本，次级分析 | B原阶段＋一次正常恢复 | R原阶段，不追加恢复 |
| --- | ---: | ---: |
| 真实请求 | 17 | 8 |
| 原账本参考模型USD | .01650680 | .00640950 |
| 实际阶段执行秒之和 | 325.84515 | 209.95967 |
| prompt / completion token | 209829 / 4051 | 83797 / 2185 |
| cache hit token | 72240 | 34030 |
| 原固定门槛 | 合格 | 合格 |

R少9次请求（52.9%），参考模型费低61.2%，实际执行时间低35.6%。B恢复发生于另一个
窗口后，协调等待不计入表中的阶段执行时间；日期/原日志保留，不把它写成连续用户等待
时间。按相同冻结价格将所有prompt按miss作诊断重估：B.02300840、R.00947220，低58.8%。
这不是供应商实付或另一轮随机对照；本次只有一个任务的预声明次级恢复分析。

可执行结构的实际收益范围是当前测量读取/清单时间线及固定输出结构：原C源08f511b3
未修改，新任务上最终JSON来自真实native执行；R的最终编码仍由Actor组织。原主配对
的C采用与合格交付证据、原B失败、恢复反馈及额外成本形成完整链，不把C concat初稿
消费扩写成最终完整媒体流程复用，也不从单例声称一般稳定效率提升。

任务两臂含恢复25请求/USD.02291630；加原此C源开发/认证40请求/USD.03200286，为
65请求/USD.05491916；再含上一冻结代四侧为126请求/USD.12349896。更早已知/未知历史、
CPU和人工维护仍在原记录中，这些小计不是完整冷启动净收益；当前单例尚未摊平学习。
独立审计task16-repair-inclusive-audit-001核对原主结果/原R字节未变，并只对B新交付
运行原门槛。全部模型进程结束、窗口释放，不再扩样或续修；仍未合并、部署或重启服务。
