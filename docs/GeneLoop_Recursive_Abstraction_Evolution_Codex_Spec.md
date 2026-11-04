# GeneLoop — Recursive Abstraction Evolution (RAE) 实施规格

> 面向 Codex 的研发任务；拟基于最新 `main` 增量实现。2026-11-04。
> **执行前须在本地读取 `AGENTS.md`、HEAD SHA、现有 Capability / Motif / Frontier / Builder / Feedback / Store / 认证协议。** 此规格根据公开 README 与此前讨论定位，尚未直接审阅最新仓库逐行源码；文件、函数与协议以实际仓库为准，不可依据本文假定缺失。

## 一、不可改变的研究目标

实现 `Separation → Abstraction → Recomposition → Evolution` 的最小可运行递归闭环。

- **Separation**：识别可由已认证结构承担的局部义务，未知条件仍由 LLM 决定；不等同于仅压缩模型上下文。
- **Abstraction**：把已解决的局部执行图提升为具备契约、版本、适用边界与执行回执的 Capability。
- **Recomposition**：在下一轮 Runtime/Builder 中把 Capability 作为一等原语，**新轨迹仍记录这次调用的外部依赖关系**，可展开审计，但不要求模型重复推演内部节点。
- **Evolution**：基于实际执行及后续创造反馈，允许调整抽象边界、粒度或构造方式；不能止于修改候选分数。

目标不是工具调用深度，而是 **同一个学习-认证算子可以反复作用于包含已学原语的后代轨迹**；并允许能力在下一轮的构造/验证中发挥作用。不能强制 D 调用 C，也不能将来源相关性直接宣称为创造价值。

## 二、先审计：必须输出机制缺口表

至少检索并阅读实际等价模块（以下仅为先前出现过的可能文件名）：

- `src/adapters/capability_discovery.py`：PR #126 的能力变化触发/机会发现、候选去重与真实来源
- `src/adapters/capability_improvement.py`：公共 Controller、Builder、认证、发布、下一轮材料更新
- `src/adapters/capability_feedback.py`：Execution Value / Creation Value、证据来源、成本反馈
- `src/adapters/capability_authoring.py`、场景 author：已有能力在生成新程序时如何暴露/引用
- Capability Registry/Store、Script/Motif 编译器、Script/Tool Runtime、Binder、Frontier、negative guard、质量/成本计量
- `schemas/capability-improvement-v1.schema.json`、现有测试与 `package.json` 脚本

输出：现有机制 / 缺失环节 / 最小修改位置 / 禁止修改的旧路径 / 风险。复用已有 ID、schema、store 和账本。不得重复造一套 `RecursiveRegistry`、`MetaAgent`、`StrategyManager` 或第二个 IR。

## 三、统一契约：Verified Capability 当作一等原语

优先在已有 Capability 契约上按需要增量补充（若等价字段已存在，不改 schema）：

```yaml
capability_ref: "<id>@<immutable_version>"
kind: "executable"  # 不强制按层级分类
input_schema: ...
output_schema: ...
applicability:
  environment_versions: ...
  permission_scope: ...
  guard_refs: ...
verified_claims:
  - claim_id: ...
    scope: ...             # 仅在被验收的适用范围内
    verifier_ref: ...
    evidence_ref: ...      # 独立验证证据，非模型自述
composition:
  effects: ...
  data_provenance: ...
  parent_refs: ...         # 真实运行/构造的版本引用；不代表已证明因果价值
```

目标：允许 Builder 只看到 **用途、输入/输出、适用边界、已验收的行为、成本经验**，不要求每次回传完整内部轨迹。Runtime 仍保留按需审计/异常展开接口。

**强约束**：工具说明、模型生成的目标和模型写出的 `verified=true` 不构成宿主可信证据；只有当前上下文与版本核验、授权、有效执行回执及独立 verifier 才能确认该子问题已被处理。

## 四、核心机制 A：有界子问题消解（Subproblem Discharge）

不是要求宿主证明任意自然语言命题。MVP 只处理**有对应独立验收谓词、输入输出结构明确**的局部义务。

```python
# 伪代码；接入现有 Discovery/Matcher/Binder/Runtime/Verifier

def try_discharge(obligation, task_state, catalog):
    for cap in catalog.retrieve_by_interface_and_scope(obligation):
        if not host_contract_can_cover(obligation, cap.verified_claims):
            continue
        binding = existing_binder.bind(cap.input_schema, task_state)
        if not binding.valid or not existing_guards_allow(cap, binding):
            continue
        receipt = existing_runtime.execute_pinned(cap, binding)
        if existing_verifier.accepts(receipt, obligation, cap.claim_scope):
            return Solved(
                obligation_id=obligation.id,
                capability_ref=cap.immutable_ref,
                artifact_refs=receipt.artifacts,
                receipt_ref=receipt.id,
                evidence_scope=cap.claim_scope,
            )
    return Unresolved(obligation_id=obligation.id)
```

`remaining_frontier` = 已明确声明的义务 - **确已通过检查**的义务，加上由组合引入的新依赖/冲突检查；不得对未知需求自动宣布 `solved`。发生版本不匹配、权限变化、Guard 失效、证据过期或验证拒绝时，原有语义路径继续执行/请求新判断。现有任务的非结构化开放语义交由 LLM，不能“静默省略”。

## 五、核心机制 B：递归图闭包（C 成为后代图的原生节点）

这是本轮**最高优先级**，并非仅在 Builder 的 Prompt 中提到 C。

1. `publish(C)`：认证完成后由现有 Registry 原子发布不可变版本，旧版本保留；新版本进入 Runtime 可调用目录和 Builder 可用原语目录。
2. `run(task, C)`：调用 C 时，在新一代轨迹中记录一个类型化的 **CapabilityCall 节点**：`capability_ref, input_binding, output_refs, status, receipt_ref, guard_evidence, parent_trace_id`；内部执行细节放在可按需展开的证据对象中。
3. **关键闭包条件**：现有 Motif discovery / compiler 必须能消费这种节点或其合法的类型化投影，并将其视为普通可组合的原语；不能只认识底层 Bash 或 Script 节点。
4. `discover(G_{t+1})`：从含 C 的新轨迹中提出可复用模式，仍沿用当前参数流、依赖图、Guard、适用条件、认证协议。允许新候选的执行图引用 C，不做不透明的文本扁平化。
5. `publish(D)`：独立验证 D 的**新约束**。D 获得与 C 相同的版本化 Registry/Runtime/Builder 资格；下一轮 G 再次可包含 D。
6. 防循环：发布时检查静态依赖 DAG、禁止 C→D→C 运行环/自引用死循环（除非旧 Runtime 已具备明确、可验证的有界递归协议，且该场景显式允许）。执行时已有超时、次数和资源上限仍生效。

不能把“D 引用了 C”当作进步；这只是闭包接线验收。D 可以独立生成，若未调用 C，就记录真实来源/构造/验证贡献，不强制嵌套。

## 六、核心机制 C：反馈驱动抽象边界调整

先复用现有 Improvement 和 Feedback，不新建 Meta Controller。

- 从真实轨迹抽取可复用局部区域；根据复用失败、绑定修复、频次、异常边界和组合负担，**提出替代的抽象边界/形式**。
- 候选可以是更小的局部 Motif、较高层组合、适用条件收缩、输入/输出更清晰的等价替代、或当前不学。它们只是模型/学习器的候选结果，不是手工规定的固定进化方向。
- 每个候选必须具备可执行体、契约、完整来源、独立检查；和旧版本并存，不能就地覆盖。
- 核验反馈：质量是门槛，之后分别保留 `ExecutionValue` 和 `CreationValue`，**不急着用一个任意权重的标量把二者混合**。
- `ExecutionValue`：同等质量的任务，真实减少的模型调用、Token、完整执行/学习/验证总成本；费用缺失为 unknown 而不是零。
- `CreationValue`：已有能力真实参与后代发现、构造或验证的证据，以及独立对照下改善后代能力获取的结果。区分 `proposed_parent / material_read / compile_ref / runtime_call / verify_used / measured_causal_effect`。
- 对 Creation Value 的预测只影响探索顺序，不作为已实现收益；低频基础能力不能因短期不回本立即删除。版本替代先进行影子对照，必要时回退。

关键成功判据：**反馈实际改变下一轮抽象候选的边界/表示/复用行为**；仅更新评分、摘要或计数，不满足 Evolution。

## 七、核心机制 D：最小自应用入口

不是单独实现 Meta Skill Library，而是允许 **Capability Builder 的正常构造轨迹**进入现有 Motif/Capability 学习链。

- 记录构造任务的工具/能力调用、程序生成后的实际修复、绑定与验证结果，保留用户数据与系统权限边界。
- 可认证的局部构造子过程，与普通任务一样被抽象，作为后续 Builder 可以发现和调用的原语。
- 如果学到的是构造**选择规则**，必须体现为有输入/输出、可实际执行的 `construction plan` 或现有协议可表达的决策行为；普通文本经验只有候选资格，不自动视为有效 Meta 改进。
- 对新学构造方式采用受限的独立后继任务对照，证明它确实改变分解、候选选择、绑定或验证步骤并改善后继结果，才允许在实验环境中替换原构造方式。
- 受保护的验证器、授权范围、预算与 Registry 权限始终由宿主固定执行；不允许候选自改验收标准来通过。

本轮必须接上 Builder trace→同一学习流程的路径；复杂的自主 Strategy Optimizer 和任意核心源代码自修改不在本轮范围。

## 八、验证：今晚必须完成的机制测试

**T0 审计**：最新 HEAD SHA、路径/接口对照、兼容性、现有测试命令，先在 PR 描述中可追踪地记录。

**T1 分离**：适用且独立验证通过的 C 可以处理有界 obligation；未满足条件、无权限、证据冲突、版本变化时回到 LLM/原路径；从不假装已解决。

**T2 实际调用**：C 通过已有 Registry/Runtime 运行、保留真实 binding/receipt；模型上下文只收到受限摘要与 artifact，按需可展开原始审计。

**T3 递归闭包**：利用 C 的真实调用生成新轨迹 G1；原有 Motif discovery + compiler **实际消费**该节点；在冻结验证器下认证 D；D 在 G2 中可再次作为普通 Capability 被调用/用于学习。防循环有效。

**T4 失败与粒度变化**：模拟一个过大/绑定昂贵的候选与一个经验证的更合适边界；反馈能够实际产生/采用第二个**新版本**，不能只更新分数。失败案例保留。

**T5 双价值**：Execution/Creation 分别记证据；所有成本有来源、失败重试入账；材料被模型阅读≠实际被调用≠因果证明。含未知费用时不发放虚假预算。

**T6 自应用**：Builder 构造轨迹进入同一候选提取路径；已学、经过验证的构造原语可影响后继 Builder 行为（例如决定某局部处理方法），禁用后恢复旧行为；旧验证标准不可修改。

**T7 回归**：运行本地现有全部 Python/Node 测试，至少执行原 `npm run rsi:check`、`npm run rsi:efficiency:check`、相关 `rsi:improve` 诊断（实际命令以 package.json 确认为准）；查 Motif 旧库、两个语言的 schema、一致性、版本/权限/取消/中断/成本账本。

**T8 小规模真实模型验证（可选、需明确本轮预算授权）**：使用既有论文或视频场景完成真实 C 发布、由任务需求引发的 D 候选、独立认证与后继复用。不人工安排 D 的完整算法；完整报告所有失败。没有授权/环境时只报告机制闭合，不冒充真实自主 RSI。

区分三种证据等级：`wiring_passed`（确定性机制）、`autonomous_constructed`（真实模型与实际调用）、`measured_improvement`（同质量、全成本、独立对照）。前一等级不能替代后一等级。

## 九、工程约束与发布路径

- 在独立分支上做一个可审阅 PR，分提交：审计/契约 → Graph Closure → Discharge/Handoff → Feedback Evolution → Self-application → tests/docs。
- 新功能实验 Feature Flag 默认 `off`；不接管正式 DeepSeek Web Chat，不自动部署或重启服务，不改用户权限、共享逻辑、正式账本、新旧 Capability ID。
- 所有新产物按账号/任务隔离，运行时固定版本；不要读写其他用户的私有轨迹；不要默认上传跨用户抽象。
- 原 Builder、原 Runtime、原 Registry 与旧库保持有效。错误、取消、版本冲突和缺失环境必须可靠回退；所有失败与未知费用保留。
- 若已存在 PR1 Verified Savings 或 PR2 Budget-Aware Scheduling，保持其账本约束并只读复用，不重复开发预算系统；预算再投资不是本轮递归闭包的前置条件。
- 必须阅读根目录 `AGENTS.md`，遵守本仓库安全策略；以现有 `service` 脚本为唯一生产入口，但本轮禁止生产部署。

## 十、交付与停止条件

提交：实现 PR、逐文件改动说明、版本/契约差异、T0–T8 验收矩阵、可复现命令与证据样例、费用记录、反例清单、无需部署的回退步骤。报告须分 `Implemented`、`Mechanism Verified`、`Research Pending`。

若今晚无法满足 T3（递归图闭包）或 T6（Builder 自应用），不得宣布“完整 RSI”。应在 PR 中保留已实现的端到端最小纵切、记录阻断点，不用模拟测试替代真实数据流。真正意义上的 Creation Efficiency 和跨代正反馈仍需后续对照实验验证。

**优先级：先保证 C→含 C 的 G1→D→含 D 的 G2 的同协议闭包；再做反馈真的改变抽象形式；最后接 Builder 自应用。**
