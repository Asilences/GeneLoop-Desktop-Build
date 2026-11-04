# Skill∞论文复现适配

## 当前结论

已实现同一工具驱动优化器的任务层与meta层适配，32项确定性协议诊断通过。真实模型、benchmark质量和成本对照由公共实验入口继续验收。

## 依据与复现差异

依据为论文第3节、第4.1节与附录B、F、G。算法候选数默认外层4、内层2，任务层默认4，费用与模型请求上限沿实验宿主配置。[Skill∞论文](https://arxiv.org/html/2610.35434v1)

官方仓库仍处于代码待发布状态。本实现采用原创复述的seed说明，将论文CLI操作接到原Harness的function-call工具。基础模型、Harness及数据版本以实际实验配置为准。结果标注论文复现版。[官方仓库](https://github.com/taowangcheng/skill-infinity)

原生发现已通过GeneLoop研究插件接入原Harness的SkillRegistry及`skill`工具。名称与描述进入原生目录，模型主动加载正文。MCP资源读取作为补充入口，激活状态由实际读取或原生加载回执记录。

本轮共享benchmark宿主将候选的training与validation都安排为公开训练变体上的独立新运行，canonical任务留作版本冻结后的最终测试。返回值显式记录`validation_scope=fresh_run_of_training_variant`。这是本轮适配的评价划分，和发布链中使用canonical验证的流程存在差异；两侧按相同划分运行，复现结果保留该差异。

本轮两侧采用相同的无oracle协议。优化器可按需查看真实执行、工具结果与原评分器反馈，参考解和oracle文件保持不可读。这项访问策略属于本轮论文复现配置，结果中单独披露。

## 入口

源码为 `src/adapters/skill_infinity_baseline.py`。

- `create_seed_task_skill` 生成通用任务seed。
- `create_seed_meta_skill` 生成原生发现的meta-skill包。
- `optimize_task_skill` 执行一次任务skill优化。
- `refine_meta_skill` 用相同优化过程修订meta-skill，分数取各内层优化的平均验证增益。

`call_agent(request, dispatch)` 接收名称、描述和包路径及工具schema，实际正文由模型按需读取。`evaluate(request)` 接原任务评分器，返回score、激活状态与证据。`review(request)` 接独立新会话，返回accepted、reason及证据。原请求账本由公共runner负责。

每个输出目录保留seed、完整候选、提案、训练与验证结果、独立review、决策和工具调用。失败草稿消耗算法候选名额，未知费用保留未知。外层零候选明确标为seed-only。

### 原始证据读取

`evaluate`的可信返回可提供`evidence_refs`与`evidence_indexes`，每条均为原`FileRef`的`path`、`sha256`。`read_evidence(evidence_id, offset=0, limit=12000)`按sha256选择证据，返回原文分页、原引用和下一页位置，单页最多24000字符。读取复用原`verify`检查原始字节哈希，失败进入原工具回执。

宿主可生成JSON索引，显式包含下一层`evidence_refs`与`evidence_indexes`。读取可信索引后，其引用才进入允许读取集合。普通模型结果、轨迹或文本中的路径声明保持为原文，不扩大读取权限。Host应明确提供原模型结果、工具调用日志、verifier诊断及对应索引。

meta层自动继承inner层明确授权的宿主证据，并附inner实际优化请求、响应、工具回执与结果，因而可调查优化动作和任务质量之间的关系。

R3早期baseline仅暴露评分与不可读取的引用，优化器缺少原轨迹读取入口。该运行保留为接口诊断及真实成本记录，公平效果比较使用接通上述读取后的新实验ID。

### 激活状态与独立审查

论文§3.3明确要求Reviewer拒绝从未激活的候选，§3.5将描述纳入原生发现与优化范围。附录G定义的验证摘要中，`true`表示所有评测执行均确认加载，`false`表示至少一个执行未加载，`null`表示未知。因此部分加载也可能得到`false`。[论文正文及公开Seed](https://arxiv.org/html/2610.35434v1)

复现适配由独立Reviewer结合候选训练rollout、验证与原生加载回执判断是否从未激活，同时审查候选的实质修改、可用性与质量。Host继续强制拒绝内容未改的候选。原`skill_activated`摘要在review结果中按原值保留，`false`和`null`分别保持原始含义，候选被接受时仍须单独核对后续实际采用。

修订前Host用`is not True`统一拒绝部分加载与未知状态，超出了上述三态摘要能够支持的结论。本次修订保留独立审查的拒绝职责，并补齐候选自身训练rollout供Reviewer读取。原R4服务器会话未改写。

## 已验证

命令为 `.venv312/bin/python -m pytest -q tests/test_skill_infinity_baseline.py`，结果28项通过，新增模型请求0。

覆盖原生目录发现、候选与独立review、激活未知、失败保留、包冻结、评分异常、完整两层循环及seed-only区分。

证据读取新增5项诊断，覆盖原文分页、可信多级索引、模型正文伪造引用拒绝、未知路径及改写证据拒绝、meta层保留inner原宿主证据。

激活审查覆盖`false`和`null`由独立Reviewer接受或拒绝时均原样保留、部分加载同时呈现训练与验证证据，以及三态下无修改候选都受Host拒绝。

## R6优化器零请求故障

`code-r6/.local/results/baseline-econ-001`在codebook seed验证产生51次原请求后，inner优化器首轮结束为`incomplete`，原生事件记录HTTP400，provider请求为0。原会话为`session-96fbd67de5ce4b04a04ca8529e7288b5`，已有失败与费用保留。

精确根因在公共预算代理的`_image_count`。它递归扫描请求时，将工具JSON Schema的`type=["string","null"]`当作集合查询键，触发`TypeError: unhashable type: 'list'`。该异常在请求登记前被HTTP处理器转为400。用原事件中的`create_candidate.files` schema重建本机诊断请求，可在原`reservation`稳定复现。

修复只在媒体类型集合查询前检查类型值为字符串，保留合法union工具schema与原费用归属。真实`image_url`、`input_image`、`file`、`image`仍逐项计入媒体储备。原SDK、本机MCP、原生Skill、完整baseline工具集、原预算代理和本机合成SSE Provider完成3次往返，账本从5增至8，union schema原样转发。相关gate、Harness及baseline合计63项诊断通过，新增真实API调用0。

该代码文件属于managed library的执行代码锁，后续需通过既有兼容导出产生新独立版本。旧证书与R6运行保持原状。

## R7完整质量失败被误判为不可评分

原运行`code-r7/.local/results/baseline-threejs-001`的seed验证完成5次请求，技能已加载。原Three.js评分器实际完成3项测试，2项通过，几何质量断言失败，写入官方reward 0并返回退出码1。原`operation-0013.json`、verifier stdout、`ctrf.json`与reward保留。此前适配器要求评分器退出码为0才允许任何分数，因此将该质量失败记为`verifier_failed`和`score=None`，inner优化器在读取seed评分时退出，尚未进入改进循环。

修复复用原reward与CTRF，仅在评分器正常完成、退出码1、官方reward位于`[0,1)`、CTRF计数与记录完整一致且全部失败均为调用阶段断言失败时，记录`evaluated`和原分数，并附`verifier_outcome=quality_rejected`及原CTRF引用。原非0退出码与日志保持。缺报告、初始化／收集／导入错误、不完整计数和超时继续保留故障与未知评分。

155项相关无模型诊断通过，包含原Trial经Host把seed质量失败0分传入Skill∞优化器并实际调用后续优化入口。该回归仅验证失败反馈能够继续流转，真实策略优化效果待后续实验。原R7结果没有追改，新增真实模型调用0。

## R8选择顺序与review重入

原`code-r8/.local/results/baseline-threejs-002`最终因`skill_iteration_without_candidate`失败。Task优化器先调用`select_parent(seed, continue)`，同会话随后创建与评估候选被`skill_iteration_already_decided`拒绝。原约束在会话结束后才执行，反馈时机使模型无法在当前会话修正。

修复将现有continue约束前移到选择工具，当前轮未创建候选时返回明确错误，暂不写decision或设置`active_decision`。同会话仍可正常构造、评估、独立审查与选父，stop保留seed继续允许，候选预算与原run兜底保持。

同一R8运行中，另一inner候选的独立Reviewer返回自然语言长评，原严格JSON解析失败。重试review时，原`review-request.json`已存在，导致`FileExistsError`。修复为每次显式review调用新增独立`review-attempts/<id>/`，分别保存请求、原响应、合法判定或失败。首个`review-request.json`字节保留，合法成功后沿原`review.json`及候选状态接线。成功review再次读取复用已有结果。非法自然语言、非法accepted类型继续拒绝准入，模型调用与失败费用沿原宿主账本保留。

新增4项诊断覆盖过早continue后同会话修正、无候选stop、首次review失败后第二次可真实调用回调且原请求与费用前缀不变、非法review结果保留。baseline共32项通过，与Host合计81项通过，新增真实模型请求0。原R8运行记录未改写。

该R8真实运行累计233次请求，原代理观测费用USD0.47944473。局部OBJ task候选通过独立review并在验证与training中实际加载，单次同canonical reward保持1时，任务请求从33次降至8次；外层最终保留seed meta-skill，整体task优化未完成。本轮保留局部正向事实、元技能未更新和整体失败，完整优化开销单列。

新增 `tests/test_research_harness.py` 的13项诊断通过，包含真实本机MCP2.2、原SDK、原生skill加载、工具回调、任务timeout及原累计费用账本。完整SDK诊断使用本机合成SSE Provider，原请求计数5→8，实际工具为`skill`和研究MCP工具，新增真实模型请求0。

这批诊断发现并复核了资源读取激活误判、缺少请求证据、结束异常下费用归属恢复等问题。原生skill加载的内容摘要以注册时字节计算，避免将后续磁盘内容误记为已加载正文。

共享benchmark宿主的 `tests/test_evolution_benchmark.py` 13项诊断通过，覆盖同源输入、原生skill容器路径、训练与canonical划分、失败和原费用证据、独立review读取原记录。verifier失败时保留原reward但有效score未知，失败review会话保留失败并阻止候选准入。
