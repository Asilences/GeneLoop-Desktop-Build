# 条件化策略演化研究接口

策略由适用条件、开放决策文本、已认证 Capability 引用和原始证据组成，格式为 `capability_strategy_v1`。定义、父版本和来源使用既有摘要与 FileRef。独立宿主验收结果沿原 CapabilityFeedback 记录，后继使用需重读原证据、准入事实和撤回状态。

## 候选与继承

`create_strategy(definition,snapshot)` 接收 `owner / target / scope / applicability / decision_policy / capability_refs / evidence / parent`。target 可为 `task` 或 `construction`。策略文本最多4096 UTF-8字节，适用条件最多2048字节，依赖最多8项且须在当前snapshot中认证可见。

`admit_strategy(reference,snapshot,target=...,scope=...,evaluate=...,directory=...,feedback=...)` 使用宿主固定的独立评价回调。回调返回 `passed / checks / training_sources / heldout_sources / evidence`，每项check为 `{id,status}`。所有检查需通过，训练和留出来源的内容摘要不得重叠。候选证据也不得直接包含留出来源。来源是否构成独立研究决定由宿主评价器负责核对，不能只依文件名判断。

返回 selection 为 `{strategy:FileRef,evaluation:FileRef}`。`strategy_context(selection,snapshot,target=...,scope=...,feedback=...)` 重新核验依赖和撤回。能力库增长允许继续使用原版本，当前引用不满足认证、可见性或撤回条件时拒绝。

Builder 在 `source_catalog.inherited_strategy` 显式配置 `{enabled:true,selection,scope,feedback_directory}`。feedback_directory 使用原Feedback构造器的base目录。原 `prepare_attempt` 将一项策略及当前能力别名写入实际 Prompt，策略上下文最多12000 UTF-8字节。effective/result记录精确版本，repair保持同一选择。原Harness回合返回后、编译前复核撤回。原构造历史引用effective证据并回流，旧历史形状兼容。

`prompt_prepared_only` 表示预览已生成上下文，`prompt_exposure_only` 表示模型回合已获得该上下文。实际依赖采用须看原编译/Runtime回执，收益须做独立后继评价。

## 任务语义证据

`record_web_decision`、`record_construction_decision` 和 `inspect_decision` 复用原任务投影与构造历史。语义投影引用宿主批准的脱敏文件，其格式为 `capability_decision_context_v1`，含 `owner / source_evidence / objective / state / remaining_judgments / interactions / outcome`。

source_evidence必须逐项对应当前原始记录。interactions每项为 `{event_index,kind,summary}`，kind可为实际问讯 `clarification` 或原用户消息 `user_message`，事件位置必须存在。用户文本的语义解释由宿主审阅，原始内容保留在私有事件文件。比较主会话和同一决定的重试归为同一来源，缺可信归属时拒绝。

原Evolution Packet按宿主指定共同问题聚合语义证据，允许不同调用图支持同一策略问题。默认30KB上下文与跨任务要求继续执行。原调用图观察保留原聚合规则。

## 单次研究入口

运行 `node scripts/project.mjs python scripts/run-strategy-evolution.py --manifest PRIVATE.json --output .local/NEW_RUN` 预检。显式 `--call-model --budget-usd 3` 使用服务器原账本，单次最多1个真实请求，DeepSeek flash/off，输出容量393216。

manifest字段为 `snapshot / observations / scope / target / feedback_directory / ledger_root / host_adapter`，可选 `parent_selection`。snapshot与host_adapter使用FileRef，observations沿原 `{split:'training',scope,evidence}` 列表。host_adapter为操作员固定的项目内Python文件，提供 `evaluate_strategy(candidate)`。执行其核验后的同一份源码字节。模型没有选择宿主代码或验收器的入口。

Evolution候选新增 `task_strategy`，`construction_strategy` 同样支持版本化策略。其proposal恰含 `applicability / decision_policy / capability_refs / parent`，模型parent为null，父策略由宿主parent_selection固定并核验。候选支持证据由已核验观察提供，最多两个候选，允许no_change。独立验收后的selection可通过上述既有Builder配置继承。

任务策略已有表示、验收与上下文API。下一步接通用任务宿主的策略选择与继承，使条件策略影响任务分解、能力选择、执行顺序、验证范围和恢复方式。具体工具调用沿原Harness执行，问询是其中一种可能行为。验收需观察后继决策及实际结果，策略的稳定执行片段再沿原学习链积累。

策略实际使用中的稳定执行片段继续经过原Runtime回执、RAE投影、原Motif learner/compiler及Store认证。本轮继承接线不自动保证出现新的稳定片段或净收益。
