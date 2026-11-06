# Evolution 产物分配检视

## 范围与结论

2026-11-05只读代码及历史运行审计。基点为研究分支`codex/evolution-overnight-20261105`、HEAD `6499d32c`，同时核对当前磁盘上未提交的语义质量反馈补丁。本次未修改源码、运行新模型、合并或部署。磁盘实现、冻结实验和生产状态分开评价。

产物分类与接收位置基本合理，实际运行入口覆盖不完整。任务策略主要依赖宿主显式选中，可执行能力已发生真实入池与后继试用；构造策略和边界改进在SkillsBench宿主仍为pending。当前证据不能把候选提出、独立验收、上下文展示、实际采用与价值改善合并为一个成功状态。

## 四层数据流

```text
真实经历与质量、费用反馈
    → Evolution候选
    → 按产物类型构造和独立评价
    → 认证能力 / 准入策略 / 新边界版本
    → 下一任务或Builder获得对应版本
    → 实际调用或行为变化
    → 新质量、完整成本及后继构造反馈
```

## 产物与接收位置

| 产物 | 接收者与用途 | 当前实现 |
| --- | --- | --- |
| `capability` | 原材料库、Capability目录、Runtime及后续构造可见能力 | SkillsBench经原Script学习和认证注册Python helper，下一任务读取最新catalog。语义质量另评 |
| `task_strategy` | 执行任务的模型，改变取证、分解、选择或恢复 | Web研究模式注入已选条件策略；benchmark生成原生可发现的SKILL包 |
| `construction_strategy` | Builder，改变能力构造方法 | 公共策略处理及Builder inherited_strategy已接；benchmark缺真实Builder评价适配 |
| `boundary` | 原Motif学习、编译及独立验收，产生新抽象版本 | 原离线Evolution入口已接；benchmark缺适配当前轨迹的边界宿主 |

`boundary`目前表达已观察轨迹中连续区域的选择。通用接口改造或Harness代码修改需要能落入现有能力表示或另行开发接线，当前没有任意Harness改写的自动投放入口。

## 实际入口覆盖

- `scripts/run-evolution-agent.py`实际只注册boundary handler。其余类型通过格式检查后仍会因没有宿主入口保持pending。
- `scripts/run-strategy-evolution.py`由宿主配置task或construction，只注册对应策略handler，并要求实际评价适配器。
- `src/adapters/evolution_benchmark_gene.py`接task_strategy，并在配置原生材料后接capability；construction_strategy和boundary明确保留pending。新增材料作为下一任务材料快照可见；同轮策略引用新材料时返回`new_material_requires_next_generation_snapshot`。
- benchmark逐代写continuation；保存续接记录不等于已经自动启动下一代。生产任务策略按研究配置、场景和任务起点冻结，研究运行与正式生产分别判断。

## 选择、采用与价值

策略目前按target、scope和宿主selection进入固定接收位置。Web路径把一个已选策略的applicability及decision_policy送给任务模型；Builder路径读取一个显式inherited_strategy；benchmark保留最新独立准入的selected策略并生成可发现包。多策略按当前任务自动检索、排序和选择的完整通用路径尚未发现。

自然语言applicability允许模型判断适用性，不能单独证明策略已被正确选用。Web收据明确记录prepared_only或prompt_submitted，semantic_adoption仍为null；benchmark区分原生skill_activated，但实际语义作用仍要求检查原任务行动。

能力调用能够由Runtime回执确认。策略采用应定位到后继行动，说明采用了什么决策方法，随后再评价质量和成本。认证等价、独立任务质量、执行收益和创造贡献各自需要证据。

## 已核对真实产物

| 运行 | 结果 |
| --- | --- |
| 11月4日原Evolution real-001 | 两候选原始结果因描述字段校验拒绝；离线格式修复另记。没有发布或后继采用 |
| 11月4日原Evolution real-002 | no_change，无待分配的新产物 |
| `gene-econ-001` | selection=null，无新材料；原结果明确保留构造策略及边界适配pending |
| `gene-threejs-004` | 一份OBJ检查程序注册为两个接口root；selection=null。后继实际文件两次调用输入形状失败，小样本试用成功；递归学习pending |

原始结果来自服务器隔离`code-r6`、`code-r11`及本地已有`evolution-agent-20261104`同步副本，没有重写旧结果。以上范围不能外推为其他所有场景均无策略采用。

## 后续检视用的五个问题

1. 候选提出的是待解决工作、决策方法，还是已有能力内部实现？
2. 当前入口确实接收该类型，还是只允许输出而保留pending？
3. 下一任务如何拿到对应版本，当前是否还需显式宿主selection或续接？
4. 后继证据属于可见、读取、实际调用，还是可定位的行为变化？
5. 独立质量、完整成本及后继构造表现分别改变了什么？

优先补齐真实论文语义任务的产物接收和采用验收，再决定是否需要多策略选择机制。保留有界条件Prompt形式，复用原Registry、Builder、Feedback和Runtime。

## 用户指定的五篇重复实验检视包

用户明确复用2026-10-21五篇各两次实验。先前准备的Skill∞新任务被替换，原下载材料保留为未运行备选。原五篇数据与运行记录已在旧`paper-script-motif`工作区找到，复制到当前私有`.local/debug/evolution-artifact-routing-20261105/five-paper-replay-001/`。

包含QLoRA、S4、RoFormer、Prefix-Tuning、DDPM的五份原BibTeX、摘要与原protocol相同的题面、10次Baseline及两批各10次Motif原回答和运行summary/result/manifest，共30次历史记录；逐文件复制摘要与原文件一致。Baseline请求合计195，修复后110，核心正确率两者均9/10，失败身份与未知费用按原记录保留。完整网页事件另需按task_id定位，不能把本包的result/summary称为已完整复制的原生事件。

本次准备新增模型请求0，旧输入与轨迹未改。先观察既有结构复用正例、未接管和误报反例，确认剩余负担，再评价新Evolution产物的增量。原任务范围为书目文件完整性与同标题分组，确定性质量验收和自然语言解释评价分别处理；不直接写成整篇论文语义审查或持续RSI结果。

## 当前输入机制审计

本次按`7fd8c1fd`及当前未提交文档继续只读核对。`capability_investigation.py`已有总览、经历/能力/历史搜索，以及context、quality、actions和原件分页读取；`capability_decision_evidence.py`已有原质量评价绑定，能把任务和工件的逐项评价接入调查。旧一次性packet和新的工具调查入口分别识别，不能把旧空候选当作新分层入口的完整验收。

旧packet按宿主relation、stage和能力引用分组，调查接口则允许模型自行检索和选取经历。relation是证据组织线索，相关性、问题成因和适当改进仍是待调查假设。当前概览提供状态、质量和费用范围，未实现从全部日志自动计算可节省负担。

通用Web经历的source_identity基于账户内decision_root和会话/父任务关系，主要防止同一决定续写重复计数。它不足以单独保证同一BibTeX在不同独立会话重复时仍计为一个输入；五篇实验适配必须复用原source_sha256组织独立性。原构造经历已有成本汇总，通用Web语义经历的observed_cost_usd仍为None，须与原账本归属衔接。

质量check可给出证据引用，绑定到任务和回答；将具体误报关联到实际解析、比较和最终判断仍待真实事件重建。原actions接口和按需证据读取可复用。五篇30次记录尚未正式进入这套调查入口，因此当前结论为输入访问机制已有、真实数据组织和诊断依据未验收。

## 修订3概念审计落实

2026-11-05，用户要求只修订概念后再次核查。通用协议改为调查、验收、交付/采用和效果四维研究视图；明确host_selected、model_selected及实际执行，三类数据角色及暴露转移，来源派生、证据强度、局部准入及归因范围。no_change从候选类型分离，增加有限调查步骤/期限与恢复规则，费用/请求仍沿显式null授权。

主批次30次记录恢复提升为当前事实，后续从skeleton、质量与动作关联推进；旧逐论断搜索为历史。完整C,C,report拒绝与局部C→report成功按主线历史记录分别保留，本次未重跑。首轮优先G1/G2，后端和长期研究缺口分列pending。

修订2私有快照、审议原文位于同问题私有protocol-review-v3目录。本次只编辑文档，新增模型请求0，源码及旧实验原件未修改。T1—T12为拟补检查矩阵，本次仅检查Markdown、链接和概念覆盖。文档仍待用户核查，未宣布冻结。

## paper-evolution-20261105-001真实执行与门禁定位

真实源码a3e96f59，前后3632文件一致。34次工具动作、1个真实策略、3次容器评价，原账本61请求/USD0.10151940代理观测费。最终inconclusive及3次结束拒绝保留。默认summary原本就返回content，门禁按参数字面判断导致误拒，修正为检查真实成功返回正文。另允许已试验候选后作维持决定，重投影FileRef仅路径变化不导致重访。修复回归103项通过，完整回归及原工具重放另追加。

私有完整结果位于.local/debug/evolution-artifact-routing-20261105/server-results/paper-evolution-20261105-001，根result.json、agent/tool-*.json、candidate-evaluation-0/result.json及host/trials保留原字节。预热manifest在真实API前冻结了两份评价器/题面/环境摘要；新CLI进一步将其纳入effective.json。原记录不追改。

本地受限沙箱的端口拒绝、Linux首次误列不存在测试文件的收集失败、GitHubAPI暂时EOF均留日志。允许回环端口后本地2971Python/1662Node通过，Linux纠正列表后302项通过。GitHub当前a3e96f59的job注解明确付款/消费额度导致未启动，steps为0。

### 真实反馈002与最终门禁状态

81b6c306下原30次工具重放no_change，0模型请求；Linux304、本地2973 Python/1662 Node及smoke/Motif/RSI通过。随后原入口检视三次新评价经历，20动作/12真实请求，完成no_change。相同快照重访为revisit_skipped，0请求。新增USD0.01977294代理观测，账本5144—5155全部已结算，两轮73请求/USD0.12129234。私有同目录server-results/paper-evolution-feedback-20261105-002保留全部回答及revisit/result.json，真实源码两轮前后均未变。

反馈解释出现可复现的模型推断错误。它将明确由模型发起的execute修复归为Runtime内部，且把三次通过外推为家族质量饱和。原动作投影的deterministic_host_callback_action_projection描述容易混淆投影生成者与动作发起者。这是下一步输入语义定位点，当前不把模型解释全部标为正确。原成本差为已测neutral，保留其错误说法并给出审计反证。

用户询问Prompt位置后又明确保留现有代码形式用于队友讨论。当前主Prompt仍在capability_evolution_investigation.py的SYSTEM，运行时追加规则在request构造处，完整生效文本和工具在每轮agent/request.json。没有新增Prompt文件。

## 用户Prompt审议后的最小增量

采用用户提供的调查目标调整，增加效率与性能压力、成功经历中的剩余负担、已有能力使后继目标可行、Builder构造与Creation Efficiency。沿原SYSTEM代码形式，提交/修复接口继续复用。为真实反馈误判补充动作来源须回到原事件核对、模型命令/修复仍属模型工作、工具调用次数不等于请求次数；note字段明确使用观察ID。

真实G1/G2入口已显式开启require_no_change_evidence=True，100/5400和20/600均为实际冻结的有限步骤/期限。严格开关本来就进入调查身份，宽松旧记录不能命中严格模式身份。本次不把这个默认值误报为真实运行遗漏。

修复局部模式工具描述仍要求两来源的不一致。只有被拒且未形成合法候选的尝试，默认结束改为inconclusive；显式proposal需要schema与证据校验通过的候选。结果新增completion_scope=investigation_only、investigation_decision和candidate_counts，独立验收、采用和收益继续读取原结果，不从completed推断。

定向107项通过。本次更新的模型效果待新唯一快照验证，前述73次真实请求仍对应a3e96f59/81b6c306的旧Prompt。当前论文初始能力快照为空、没有Builder构造经历，不能仅靠新目标指令声称观测Creation Efficiency或新高层任务可行性。

4a020696最终完整回归2977 Python/1662 Node通过，Linux308通过，smoke/Motif/RSI全通过，模型0；本地日志abstraction-prompt-full.log、abstraction-prompt-targeted.log及同前缀各检查日志，服务器快照code-paper-evolution-003/.local/linux-regression.log。后续只同步验证与交接文档。首次推送遇GitHub SSL_ERROR_SYSCALL，保留失败后按原分支重试。

## 2026-11-05 组合输入与连续反馈修正

按用户审议撤销bf15185a对普通真实Evolution的Builder输入硬门。专项输入检查独立为--require-builder-evidence；当前入口为Task Strategy Pilot。Builder清单继续复用原snapshot与decision证据，不新增Registry或学习流程。来源计数只证明不同构造任务身份，家族独立性需宿主核对；historically_exposed明确为宿主声明加原角色/原件复核。

Investigation.continue_with保留原能力目录、任务/Builder分流、笔记、历史和已暴露原件，合并新结果；新BenchmarkHost从创建时绑定当前owner。无候选、实际新结果、多代证据保留、封存角色转移均有回归。已完成no_change不因新增笔记/续接/选择记账重开，实际新评价仍改变调查标识。

任务策略采用新增原review_skill的可选行为检查，宿主冻结policy及300秒/64次读取。模型接受时必须引用两侧已经读取的动作证据，失败和未知不准入。后继按预冻质量/成本政策及稳定摘要排序，取消最后候选选择。模型评审仍是可核查的语义判断，真实校准和持续收益未完成。

服务器连接恢复后只读核对原C与Builder记录。builder-input-audit-001.json确认seed摘要一致、C认证且active、4能力闭包；owner=frontier-20261103。恢复两条construction-evidence均指向同一task摘要a37c816c…，是同任务两次尝试，不能作为独立构造问题。不得改owner接入script-motif-real论文pilot。下一真实Builder试验沿原owner做局部后继验收，继续使用已有策略接收、inherited_strategy及Builder流程。

首次全量保留2失败，分别为macOS /var符号链接临时目录守卫和测试运行期间更新的候选选择夹具；定向复核选择已通过，正式全量改用TMPDIR=/private/tmp固定代码后重跑。原失败日志context-continuity-full.log保留，最终验证另记录。此次新增模型请求0。

## 2026-11-05 通用Core、真实003与恢复终验

39b3b89e/25383ae6把Paper主脚本生命周期收回通用Core，场景以轻量回调提供经历、inspector、receiver与评价。Core不含Paper任务/评分判断；执行经历可单独启动，Builder专项另设显式门禁。旧经历、能力快照和Builder inspector不再在续接时丢失。原则已落到AGENTS、接口与通用协议。

真实003两次提交同一候选、完成两对4次任务，均未准入，原inconclusive保留。98请求/USD0.18567348代理观测费用全部结算。失败定位为日志晚结算追加破坏FileRef、重复开发暴露掩盖评价、CTRF0.3.5缺失raw_status；24b3effc增加不可变日志捕获、幂等暴露和断言拒绝识别。通用反馈完成阶段可从原决定FileRef零模型恢复，原18+新4=22条、第三续接22条、4份独立输入，快照保持，原失败质量与费用不重写。

最终定向192、本地3010 Python/1662 Node、Linux356通过，3639源码摘要不变。24b3effc再次smoke、Motif、RSI、效率RSI及RAE均退出0。日志final-*.log、完整回归evolution-core-recovery-*.log和765份私有结果均关联同问题ID。两候选原oracle断言失败，行为review不确定；尚无净收益、Builder真实策略评价或Creation Efficiency结论。细节见[正式实验](../experiments/evolution-core-20261105-003.md)。
