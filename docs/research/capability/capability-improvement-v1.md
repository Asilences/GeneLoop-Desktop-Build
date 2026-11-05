# Capability 改进协议 v1

当前优先完善机制，再接产品聊天入口。这个协议负责离线改进流程，不替代Harness模型循环、TS在线Runtime、原账本或场景检查器。代码入口为 `src/adapters/capability_improvement.py`；机器契约为 `schemas/capability-improvement-v1.schema.json`。

## 目标与输入

- `cost_reduction`：已有合格任务的降本机会。复用F02 `optimization_assessment` 的开始/暂缓/跳过决定，校验记录及发现任务关联；没有评估就暂缓，不从重复次数推算节省。
- `capability_acquisition`：失败任务或新需求驱动的能力构造。无需基线先成功，不宣称没有做过的基线失败。输入观测必须引用固定字节；heldout不得用于机会选择或修复。
- 输入可以是显式jobs，也可以是Source适配器从已登记的正常任务记录生成的机会；两者进入同一控制器。宿主提供任务族、接口和独立验收配置，仍未自动扫描任意应用或推断任意场景契约。模型自主选择Compose步骤和参数流，不由控制器指定C/D依赖。

## 流程与权责

1. 运行前校验全部任务与观测摘要，冻结策略；Source适配器在模型调用前读取固定的验证/后继任务配置。
2. 每个机会开始时从Store重新生成构造目录：保留显式种子原语及历史发布根，逐版本验证证据，使用固定依赖闭包。候选、拒绝和归档能力不能作为新选择，依赖无效同样排除。认证只覆盖发布记录中的验证范围，不代表任意新输入都合格。
3. 调用既有Harness提案入口和Builder；每次调用前写入attempt开始事件，结束后引用完整结果及原账本费用。构造目录、任务在同一修复链内固定。
4. 新候选由TS Runtime实际执行，由独立检查器验收，Store内部完成认证和不可变发布。模型不能填写通过结论、改验证器或账本。
5. 每次修复使用新任务目录与身份，不覆盖失败产物。相同错误重复、明确的修复次数上限或基础设施错误触发暂缓。`max_repairs: null`为不限，不恢复平台默认额度。此策略不保证所有不同错误最终收敛；可取消并保留记录。
6. 发布后重新读取Store，确认新能力出现在下一Builder目录，再进入下一机会。后继执行失败且已发布时停止整个轮次，要求复核；不自动再次发布或继续构造。

## 三类记录与基本反馈

事件写入私有 `events.jsonl`：`opportunity`记录机会，`attempt`记录全部尝试，`contribution`记录执行/构造贡献；`decision`记录实际分支及策略摘要。各事件含run ID、序号和上一事件摘要；追加后fsync。`plan.json`与`effective.json`保留计划、策略和关键代码摘要。相同attempt目录名必须结合run/opportunity及完整结果路径识别，不能仅按`attempt-0`跨任务合并。

- 构造侧分别记录可见根、编译后实际选择的直接依赖、参与独立验证通过的新能力。未实现模型内部“看过/考虑过”的遥测，不伪造这些事实。
- 执行侧记录独立后继任务通过，引用实际执行/验证产物。构造谱系与执行回执分开。
- `retain`表示通过构造贡献继续保留能力、供后续选择；目录不按直接调用频率淘汰已认证构造材料。构造贡献现会提高下一Builder目录中的展示优先级；宿主可在共同质量范围和兼容契约检查后显式归档旧执行入口，但保留其构造材料与依赖。没有容量受限的全局淘汰算法。
- 失败反馈实际进入下一次Harness构造；重复失败触发暂缓。发布结果实际改变下一轮Builder输入。
- `benefit`始终为null，表示未测因果收益；原始模型费用单独引用，不把未知费用当零。当前没有价值预测器、收益驱动的自动预算再投资或节省结论。

## 运行与恢复

Source适配入口：

```bash
npm run rsi:improve:source -- --plan "$PRIVATE_PLAN"
# 服务器加载项目私有环境后，真实执行（沿用原累计账本）
npm run rsi:improve:source -- --plan "$PRIVATE_PLAN" --call-model
```

默认只生成预览，不调用模型或发布。计划包含owner、种子/目录摘要引用、原ledger_root、独立store/output、policy及jobs；每个job引用任务、观测和验证配置。输出必须在当前候选代码的`.local/`；新轮次必须使用新目录。没有自动崩溃续跑：先核对journal、Store最新指针和实际任务状态，再显式安排后续任务，避免重复副作用。Linux/macOS支持实验子进程组取消；没有Windows或任意宿主崩溃恢复声明。

Source检查器支持宿主冻结的 `outputs[].result_path`，用于从嵌套交付中选择真实视频；省略时沿用`videos[index]`。路径和检查标准由宿主制定，模型不能扩大验收范围。这里只支持隔离目录产物，不授权外部应用写操作。

## 最小验收与边界

免费诊断：`npm run rsi:efficiency:check`，覆盖候选排除、旧发布证据损坏、目录累积、修复/暂缓、已提交失败禁止重放，以及构造贡献与执行贡献分离。诊断的合成适配器不代表真实模型行为。

真实验收需观察C发布后自动进入Builder、模型自行选择C构造D、D实际执行并独立验证；未选择C、构造失败、负收益全部保留。完整机制收益仍需后续匹配质量与资源的对照。本轮真实运行状态见[实验记录](../../experiments/efficiency-rsi-recursive-20261102.md)。

## 构造接口与定位修复（2026-11-02续）

模型侧使用`capability_compose_draft_v1`，宿主在effective记录版本；模型不必返回format。固定契约任务只返回steps/output：每步为`{id,use,args}`，use为当前冻结目录的c1/c2等别名。参数与输出使用普通对象/数组组装，`{"$input":["edit"]}`读取当前输入，`{"$step":["edit_video"]}`读取此前步骤结果，`{"$literal":value}`表示字面JSON；其他标量为字面值。以$开头的字段保留给操作符，不猜测或隐式纠正未知操作符。

`capability_authoring.py`确定性补齐owner、协议版本、固定契约及精确版本引用，再交给原Builder。没有预设契约时模型仍须设计contract；组合步骤、参数流和输出均由模型决定。旧完整proposal继续严格校验，不自动修复。aliases.json与aliases_sha256保留别名映射；修复时版本、目录或映射变化则拒绝。原始answer、draft、展开proposal和candidate分别保存。

编译器在真实失败点附加位置、期望、实际值与此前通过的检查。JSON错误带行列；不可见引用、类型不兼容、未保证属性和前向引用可定位。编译诊断坐标是展开后的proposal，下一修复输入同时携带该proposal与诊断，不要求模型猜坐标。没有覆盖的错误保留通用错误码，不伪造细粒度定位。下一次Harness调用接收这些证据；模型仍返回完整修订draft，不能自行声明通过。

重复失败签名比较错误、位置及候选内容；JSON键顺序变化不算内容变化。相同签名再次出现会暂缓；内容或位置变化只允许继续尝试，`progress=not_established`，不作为进展评分。已有显式max_repairs、基础设施错误及已提交失败守卫保留。

离线排障入口（零模型、零执行、零发布）：

```bash
node scripts/project.mjs python scripts/replay-capability-proposal.py \
  --answer "$SAVED_ANSWER" --task "$FROZEN_TASK" --snapshot "$FROZEN_SNAPSHOT" \
  --output "$NEW_PRIVATE_OUTPUT" --repair-object-wrappers
```

可选开关只在独立诊断副本中，为已经带类型的子绑定补缺失的对象包装，保存变更路径并重新编译；不改选择、绑定或原始文件，不修补非法JSON。该修改不是Agent自主修复。重放结果见[短记录](../../debug/efficiency-rsi-authoring-replay-20261102.md)。


## 正常记录到机会、双价值到选择（2026-11-02续）

旧视频`continue_form.py`已包含下一任务、正常源码采集、学习/认证及形式反思，PPT也有自动学习调度。本次补的是这些场景证据到新Capability流程的接缝，不是重新实现旧学习器。

计划可设`jobs: []`并提供`discovery`：

```json
{
  "discovery": [{
    "run": "<private completed run directory>",
    "kind": "native_source",
    "role": "training",
    "context": {"path": "<private context.json>", "sha256": "<raw file sha256>"}
  }],
  "feedback_directory": "<private persistent feedback directory>"
}
```

context必须恰含`owner`、`scope`、`contract`、`publication_plan`，最后一项沿用已有证据引用。宿主定义任务族/质量范围和独立验证任务，不填写组合步骤。相同context下至少两个不同任务输入，或一个真实失败，可生成`capability_acquisition`机会。这里只是探索触发条件，不证明两任务共享最优抽象或具有降本空间；模型读取原始证据自行构造。仅改任务名或复制同一输入不增加支持数；heldout禁止参与。

`native_source`复用`learn_programs.collect()`源码、原生调用及渲染回执核验；`capability_execution`读取execute模式的实际trace、snapshot、args及独立检查。后者成功记录必须含检查器新增的`evidence_binding`，逐项核对trace/manifest/specification原字节摘要；旧无绑定检查不能直接作为本入口的正向证据，不能补写历史通过。原始source/receipt/QA摘要随job保存，模型调用前和发布前复核。生成任务、原始引用及忽略原因写入本轮discovery目录，随后直接进入控制器，无需手写“构造C”。

`capability_feedback.py`在owner隔离私有目录内持久化事实，精确证据去重，写锁及原子替换；读取时复核原证据。成功发布并通过后继检查才给所选依赖记正向构造贡献，给新根记执行贡献；所有构造尝试和实际模型费用都保留。`execution_scope`用于执行质量范围，`feedback_key`用于机会族排序，不能混用。自动生成任务的新文件路径不改变机会身份。

反馈实际改变三项行为：

- Builder：有已验证构造贡献的材料优先展示，别名和版本绑定保持固定；不强迫模型选它。
- 执行：只在宿主显式承认可替换的`eligible`根内排序；优先较少失败、有合格证据的能力，再比较同scope已知模型费用。未知费用不补零，跨scope不比较费用；这不是实际总成本预测器。
- 机会：失败次数和已知尝试投入影响后续队列次序。同一原始证据已发布则跳过；跨轮同证据已有至少两次失败则暂缓，需新证据重新启动。这是机会准入策略，不改平台额度或原`max_repairs`语义；本轮内修复仍走既有签名/策略。

执行选择入口默认预览：

```bash
npm run rsi:select:source -- --plan "$PRIVATE_SELECTION_PLAN"
# Linux隔离执行，沿用TS Runtime与固定独立检查器；无模型请求
npm run rsi:select:source -- --plan "$PRIVATE_SELECTION_PLAN" --execute
```

selection plan含`owner/seed/store/feedback_directory/eligible/scope/manifest/args/output`，其中seed、manifest、args为文件路径，eligible为精确能力引用。execute另需`specification`路径；输出必须是新建的私有`.local`目录。宿主计划授权候选与工作区权限，Runtime继续核验。独立检查后的执行结果返回同一反馈库，影响下次选择；运行成功本身不能记质量通过。此入口未接正式聊天任务，也不调用模型。

## 最小失效与恢复

显式withdraw只阻断指定版本及依赖它的后继，保留原Store版本和无关能力。即使全部不可用，也保存`recovery-queue.json`，而非丢失恢复事项。已发布但后继失败的根会隔离；实际执行发生确定的版本守卫失败时隔离该执行根。当前通用错误不一定定位到具体坏叶，不能声称自动精确归因到A；任务输入变化不会因此全局撤回能力。

恢复接口要求可信宿主回调使用新生成的recovery任务身份，实际完成已有独立验证和Store发布/检查后才解除显式撤回，旧证书不能直接恢复。恢复任务尚未自动调度，也没有自动迁移任意旧依赖或崩溃续跑。显式archive只退出默认执行选择，不删除Builder材料；需不同替代根、相同契约和共同scope的独立合格证据，宿主仍负责可替代性判断。

上述工程接线以免费回归验证；未新增真实模型、视频渲染或效率对照。自动发现机会的真实有效性、选择收益、完整C→D以及节余再投资仍待验证。


## 跨场景公共入口与构造缺口

发现、提案和反馈现已从Source脚本抽出，`npm run rsi:improve`通过宿主固定的scene_adapter接入不同场景；Source旧入口继续兼容。发布/后继检查共用`capability_cycle.ts`，允许场景声明哪些失败可修复，保留严格证据与权限边界。模型明确报告缺原语/契约不兼容/证据不足时停止修复；能力池更新后可重新尝试。该结果不证明任务不可能。详见[跨场景接入协议](capability-scenes-v1.md)。
