# Skill∞论文复现适配

## 当前结论

已实现同一工具驱动优化器的任务层与meta层适配，17项确定性协议诊断通过。真实模型、benchmark质量和成本对照由公共实验入口继续验收。

## 依据与复现差异

依据为论文第3节、第4.1节与附录B、F、G。算法候选数默认外层4、内层2，任务层默认4，费用与模型请求上限沿实验宿主配置。[Skill∞论文](https://arxiv.org/html/2610.35434v1)

官方仓库仍处于代码待发布状态。本实现采用原创复述的seed说明，将论文CLI操作接到原Harness的function-call工具。基础模型、Harness及数据版本以实际实验配置为准。结果标注论文复现版。[官方仓库](https://github.com/taowangcheng/skill-infinity)

原生发现已通过GeneLoop研究插件接入原Harness的SkillRegistry及`skill`工具。名称与描述进入原生目录，模型主动加载正文。MCP资源读取作为补充入口，激活状态由实际读取或原生加载回执记录。

本轮共享benchmark宿主将候选的training与validation都安排为公开训练变体上的独立新运行，canonical任务留作版本冻结后的最终测试。返回值显式记录`validation_scope=fresh_run_of_training_variant`。这是本轮适配的评价划分，和发布链中使用canonical验证的流程存在差异；两侧按相同划分运行，复现结果保留该差异。

## 入口

源码为 `src/adapters/skill_infinity_baseline.py`。

- `create_seed_task_skill` 生成通用任务seed。
- `create_seed_meta_skill` 生成原生发现的meta-skill包。
- `optimize_task_skill` 执行一次任务skill优化。
- `refine_meta_skill` 用相同优化过程修订meta-skill，分数取各内层优化的平均验证增益。

`call_agent(request, dispatch)` 接收名称、描述和包路径及工具schema，实际正文由模型按需读取。`evaluate(request)` 接原任务评分器，返回score、激活状态与证据。`review(request)` 接独立新会话，返回accepted、reason及证据。原请求账本由公共runner负责。

每个输出目录保留seed、完整候选、提案、训练与验证结果、独立review、决策和工具调用。失败草稿消耗算法候选名额，未知费用保留未知。外层零候选明确标为seed-only。

## 已验证

命令为 `.venv312/bin/python -m pytest -q tests/test_skill_infinity_baseline.py`，结果17项通过，新增模型请求0。

覆盖原生目录发现、候选与独立review、激活未知、失败保留、包冻结、评分异常、完整两层循环及seed-only区分。

新增 `tests/test_research_harness.py` 的13项诊断通过，包含真实本机MCP2.2、原SDK、原生skill加载、工具回调、任务timeout及原累计费用账本。完整SDK诊断使用本机合成SSE Provider，原请求计数5→8，实际工具为`skill`和研究MCP工具，新增真实模型请求0。

这批诊断发现并复核了资源读取激活误判、缺少请求证据、结束异常下费用归属恢复等问题。原生skill加载的内容摘要以注册时字节计算，避免将后续磁盘内容误记为已加载正文。

共享benchmark宿主的 `tests/test_evolution_benchmark.py` 13项诊断通过，覆盖同源输入、原生skill容器路径、训练与canonical划分、失败和原费用证据、独立review读取原记录。verifier失败时保留原reward但有效score未知，失败review会话保留失败并阻止候选准入。
