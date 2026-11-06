# 跨代学习被无关能力池变化阻断

- 问题 ID：`recursive-snapshot-closure-20261105`；仅 R9 工程诊断，真实 R8 运行及冻结快照不改。
- 触发：两份训练轨迹在 M1 调用同版本 C 图；能力池增加未调用的材料后，独立留出轨迹在 M2 调用原图。整库摘要变化，旧宿主拆成 `2 training / 0 heldout` 和 `0 training / 1 heldout`，两组均 pending。发布适配器另有整库摘要相等检查，即使绕过分组也会拒绝。
- 零模型复现：使用既有真实 Runtime/Store 的合成算术夹具，M1 有 2 个 roots、M2 有 4 个 roots，实际执行的能力版本和依赖相同。旧 `_recursive_learning` 返回上述两组 pending；直接给原 `learn_capability_motifs` 两训练和一留出得到 1 个候选、0 拒绝，两条原 snapshot 均保持不变。它本来就逐条以各自 snapshot 校验原回执，无需换学习器。
- 修复：`benchmark_capability_publication.learning_dependency_snapshot` 从原轨迹重核后选择实际执行 roots 和精确递归依赖，建立独立的学习编译 snapshot。有 materials 时先按当前 catalog 检查可见性、版本、认证与生命周期。宿主按该执行闭包分组；发布适配器从原 evidence 与当前 catalog 独立重建闭包，重新调用原 learner 对比候选。原 trace/snapshot/receipt 字节、训练/最终留出角色、来源去重和原认证不改。
- 边界：未调用能力的增删不再拆散同版本图。已撤回、不可见、未认证或变更版本的执行依赖不能混用；不同执行根集合仍分别学习。未做不同集合公共子图的跨组搜索；无 current catalog 时只有历史离线候选，不授权发布。
- 验证入口：`node scripts/project.mjs python -m pytest -q tests/test_evolution_benchmark_gene.py tests/test_benchmark_capability_publication.py tests/test_capability_motif_learning.py`，93 项通过（47.08 秒）。补充明确的“两份 M1 训练＋一份 M2 留出”断言后，对应单项复核 1 项通过（4.52 秒），不相加计数。覆盖原始字节保留、发布前重核、版本组隔离、根与递归依赖撤回、owner 和回执篡改；算术发布诊断继续被原 Script 后端准入拒绝，没有伪造 Script 证书。`git diff --check`通过。
- 研究边界：新增模型请求 0；算术夹具验证代码接线，不是自主 C→D 研究成功，不与 R8 模型成绩合并。原 Script 独立发布、任务质量与后继实际采用仍需各自真实证据。
