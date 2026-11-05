# Capability 跨场景接入 v1

目标是让新场景复用同一改进机制：机会发现、Compose提案/修复、独立验证、版本发布、后继复用、双价值反馈、失效与恢复。场景提供真实记录解释、执行后端和质量标准。接口通用不意味着任意场景必然有效，也不意味着所有原生工具已经能执行。

## 已落地的公共层

| 模块 | 负责什么 | 场景不能替代什么 |
| --- | --- | --- |
| `capability_discovery.py` | 按冻结context汇集独立任务，生成机会，保留失败和原始引用 | 重复输入不增加独立支持数，heldout禁止参与 |
| `capability_proposal.py` | 既有Harness调用、精简draft、编译诊断、原账本 | 模型不能认证或发布；没有第二套Agent循环 |
| `capability_scene.py` | 原始记录入反馈、目录刷新、构造调用、机会准入和双价值规则 | 不按模型自报收益晋级 |
| `capability_improvement.py` | 同一修复链冻结证据，调度机会、构造和发布 | 已提交失败停止，不自动重放副作用 |
| `capability_cycle.ts` | 实际验证执行→Store发布→重新加载→不同输入的后继执行 | 检查owner/task/root/input/snapshot绑定与独立任务/真实工作区 |

Source原入口继续可用，提案脚本保留兼容转发。新统一入口：

```bash
npm run rsi:improve -- --plan "$PRIVATE_PLAN"
# 加载服务器项目私有环境，显式执行；原预算/账本策略沿用
npm run rsi:improve -- --plan "$PRIVATE_PLAN" --call-model
```

旧plan没有scene_adapter时使用Source。新场景在宿主计划中指定：

```json
{
  "scene_adapter": {"path": "<host adapter.py>", "sha256": "<raw file sha256>"},
  "scene_dependencies": [{"path": "<native backend or checker>", "sha256": "<raw file sha256>"}]
}
```

这是安装可信宿主适配代码的入口，与配置MCP一样具有宿主权限；不是模型可以生成或选择的插件，也不是代码沙箱。导入前校验精确字节及依赖，构造和发布前再次核验；源码变化须新计划/新轮次。场景依赖清单由宿主列完整，不宣称自动覆盖全部传递依赖。

## 接入一个场景需要什么

Python模块导出`create_adapter(plan)`，返回`CapabilityImprovementAdapter`子类。只实现三个场景方法：

1. `inspect_run(entry, owner)`：读取实际记录、核验输入/输出/质量关联，返回task_id、task_fingerprint、status、context、scope、evidence、trace、role、kind。fingerprint按真实输入定义，不能只用任务名称。若是可归因Capability执行，标记`capability_execution: true`，trace需含精确root和原生回执。公共层进一步拒绝heldout、非终态、context变化和缺失/变化的原证据。
2. `freeze_publication_inputs(job)`：在模型调用前冻结独立验证与后继任务配置。模型不能改这些标准。
3. `publish(job, candidate, attempt, expected_latest)`：连接既有执行与检查器，优先复用`completeCapabilityCycle`。成功返回status/published、publication_sha256和evidence_ref；失败返回error、committed、evidence_ref，以及宿主判断的`repairable`。公共控制器不再认识Source专用错误码。基础设施失败不要请求模型修复。

通用版本守卫撤回规则在基类中；场景可通过`withdrawal_reasons`补充明确的版本失效原因，不把普通输入失败等同于全局能力失效。

TypeScript生命周期接受场景`run(snapshot,input,mode,label)`和`check(run,label)`：前者必须调用已有原生后端并返回实际trace和产物bytes，后者独立检查当前产物。场景适配器仍负责原生授权、隔离、取消和外部副作用边界。现有公共Runtime的叶后端类别仍为Source Program与Artifact Motif；任意MCP工具到叶能力的映射尚未完成，不能把它假装为已认证Artifact。

QA的`evidence_binding`与发布verdict明确分开：原场景文件保留绑定信息，`publicationVerdict`只剥离这个已知、格式合格的传输字段，交给Store原有严格校验；未知字段继续拒绝。修复了上一轮增加QA绑定后会被Store顶层字段校验拒绝的兼容缺口。

## 缺材料时的行为

模型可返回一种明确暂缓结果，而不是不断生成非法组合：

```json
{"defer":{"reason":"missing_primitive","requirement":"需要能读取指定数据源并返回结构化记录的原生能力"}}
```

reason只允许missing_primitive、incompatible_contracts、insufficient_evidence。保存具体缺口及已花模型费用，停止当前修复链，反馈状态为unknown；这不是不可能性证明，也不是授予模型安装/执行新工具的权限。相同证据且能力池未变时暂缓；已认证目录摘要改变后允许重新尝试。新证据也能生成新机会。

目前尚未自动将缺口分派给Source/Artifact/Motif学习器，不宣称具备开放式原语生成。下一步优先连接现有学习器的输出、原生认证和能力目录，复用这条重新尝试机制。

## 两种验证，不混用结论

- 视频：旧Source适配器使用新的公共生命周期，在Linux新目录实际渲染/检查/发布并换输入复用历史模型候选。验证执行与后继执行各23项机械检查通过，模型请求0。它证明迁移后的这条真实执行路径可运行，不证明本轮模型能自主构造新能力。
- 数据计数：`examples/capability-scenes/counts/`是第二种场景的适配协议示例，使用同一发现/控制器/反馈/Store；固定Python程序确实执行，独立程序复算结果。任务、提案和准入权限是显式诊断夹具，不能连接生产用户会话或当作真实模型、真实Artifact认证或跨领域收益证据。

Source缺口分派和材料登记已增加，配置和限制见下节。更广泛的原生工具适配、普通任务结束自动采集、更有辨别力的机会发现、净成本与创造价值估计仍未完成。公共接口可复用不代表普遍有效。前轮证据见[记录](../../experiments/efficiency-rsi-scenes-20261102.md)。

## 原生材料获取与重新评价（2026-11-02续）

共同适配器增加可选`acquire(job,result,attempt)`，默认返回deferred。只有可信宿主可以选择学习器；模型仍只报告缺口。返回registered后，控制器重新读取、校验能力库和机会准入；只有可用目录真正变化才开始新的构造尝试，不沿用旧快照修复。队列内已暂缓的机会在后续发布改变目录后也会重新评价。历史decision/outcome保留，因此一个机会可以先deferred、后published，不能将两者算作独立任务。

原生材料保存在`store/materials/<owner哈希>/`，引用原library字节和认证/学习证据，读取时重验并调用原生映射器重建契约。固定seed不改写；原生source等价认证不等于新任务语义质量，Compose仍需独立验证、发布和换输入后继执行。Source任务manifest增加可选`additional_libraries:[{path,sha256}]`，每个叶执行按完整legacy_ref选择对应原生库。旧manifest继续可用。

Source计划可选`learning_routes:{path,sha256}`，文件格式为：

```json
{
  "format": "source_learning_routes_v1",
  "owner": "宿主所有者",
  "routes": [{
    "scope": "与机会execution_scope一致",
    "backend": "source_program",
    "runs": [{"run": "私有正常Source任务目录", "role": "training",
      "context": {"path": "宿主context.json", "sha256": "原字节摘要"},
      "evidence": [{"path": "原始证据文件", "sha256": "原字节摘要"}]}]
  }]
}
```

`evidence`必须完整包含原`capability_observations.inspect_run`返回的证据，不能只放摘要或宣称passed。只有missing_primitive、唯一scope路由和合格训练见证会分派。执行复用`learn_programs.py`及`certify_programs.py`，DeepSeek Flash/off/max_tokens393216，原`ledger_root`已有账本/检查点及同一proposal锁；费用/请求不限，不重置。服务器还需原`REMOTION_EXPERIMENT_ROOT`资产/运行环境。旧学习CLI默认6000保留历史配置，新路由显式覆盖。请求、学习、失败、认证及原机会关联留在acquisitions；相同证据已启动过的学习不自动重放，中断需检查原状态或提供新证据。

该学习器从见证源码参数化抽象，不会根据任意缺口凭空创造新算法。incompatible_contracts/insufficient_evidence及无合格素材保持deferred。当前不是跨Source/Artifact/Script的智能分派器，也不是常驻后台调度器；重新评价只发生在显式运行控制器时，且不重发原用户任务。

## 论文执行证据：独立只读入口

`node scripts/project.mjs python scripts/observe-capability-paper-tasks.py --request "$PRIVATE_PAPER_REQUEST"`读取原论文学习工作器的owner/scope/task_ids请求格式，将派生记录写到同owner私有`capability-trajectories/`。保留实际工具、参数、结果、事件位置、已有before/after边界、环境工具表和账本引用。未知参数来源、依赖与前提为null；失败不删，quality=unreviewed、split=unassigned，不把工具成功当论文正确。

旧工作器和认证库完全保留。当前入口需显式运行，尚未接默认任务结束触发。Script后端及论文学习路由现已接入，详见下节；paper_document_read仍未迁入，真实历史任务路由还需验证。

## 论文 Script 接入（2026-11-02续）

`scene_adapter`指向`scenarios/paper_proofreading/capability_adapter.py`的路径/摘要；`scene_dependencies`应固定同目录发布器、检查器及`src/adapters/paper_bibliography.py`。继续使用公共`npm run rsi:improve -- --plan ...`，只有显式`--call-model`才运行Builder。默认聊天不变。

```sh
node scripts/run-script-capability.mjs --catalog --library "$SCRIPT_LIBRARY" --owner "$CAPABILITY_OWNER"
node scripts/run-script-capability.mjs --manifest "$TASK_MANIFEST" --snapshot "$SNAPSHOT" --args "$ARGUMENTS"
```

目录返回原生引用、输入契约、认证输出形状和excluded原因。支持只读文件输入，参数为`{paths:["/work/inputs/…"]}`。输出含`stdout`；原证书具有稳定JSON形状时还含`value`，可用于组合。原生认证表示源码等价，不直接表示论文质量。

`script_capability_task_v1`由可信宿主提供：`owner/task_id/workspace/registry_path/libraries:[{path,sha256}]/inputs:[{path,sha256}]/grant`。input.path为虚拟输入路径，对应workspace/inputs；grant绑定`id/task_id/snapshot_sha256/root/arguments_sha256/mode/effects/revoked`，effects仅`["read"]`。候选不能自行授予权限。

论文job的`publication_plan`指向JSON摘要引用：

- `libraries`：原生库的`{path,sha256}`列表。
- `validation`和`followup`：各含`id`、`inputs`、`input`、`specification`，须不同任务、参数及输入内容。
- `inputs`：`[{path:"/work/inputs/check.bib",source:{path:"私有输入路径",sha256:"摘要"}}]`。
- `input`：实际组合参数，例如`{paths:["/work/inputs/check.bib"]}`。
- `specification`：`{kind:"bibtex_inventory_v1",source_path:"/work/inputs/check.bib",fields:{entry_count:["entry_count"],unique_key_count:["unique_key_count"],duplicate_keys:["duplicate_keys"]}}`。fields为组合输出中三个盘点字段的路径，可指向嵌套字段。

适配器为每次尝试创建输入副本，并补任务身份、权限和登记表；候选不能指定检查器。完整可执行配置生成示例见`tests/test_paper_capability.py`中的Linux原生诊断，勿将其确定性提案视为真实模型行为。

`learning_routes`可指向`paper_script_learning_routes_v1`，包含owner及routes。每条route含`scope/backend:"script_motif"/tasks`；tasks首项role为`certification`，其余为`training`，各含`path`和`evidence:[{path,sha256}]`。evidence至少完整包含`project_web_task`返回的原始证据。只接明确missing_primitive，复用原学习器与原生认证，无新增模型调用。失败/中断不自动重跑；入池后由公共控制器重读目录并重新准入。真实历史任务路由待验，直接原生认证诊断不能替代。

旧`code_locks`不改写。四个离线编译文件仅作来源记录，执行路径继续按当前哈希或仓库维护的精确转换表核验。白名单在`config/script-runtime-compatibility.json`，不接受候选自带例外；新增转换须核对具体变更并跑相关回归。

Store在Windows采用文件fsync与同卷原子rename，不尝试Node不支持的目录fsync；POSIX保留目录同步和I/O错误传播。当前未承诺Windows断电后的目录持久性或完整崩溃恢复。两端的CAS、原子指针、原生执行、独立验收及原字节重验保持一致。
