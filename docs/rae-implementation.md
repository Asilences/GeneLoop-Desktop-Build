# Recursive Abstraction Evolution：实现与验收

- 规格：[用户提供的完整规格](research/rae/GeneLoop_Recursive_Abstraction_Evolution_Codex_Spec.md)。
- 开始日期：2026-11-04；远程main经`ls-remote`与fetch核对为`5d73a4b90e4121e94c9e7240bc8823e8b6bb3bff`。
- 原分支：`codex/recursive-abstraction-evolution-20261104`，在当前工作区从该main建立；连续研发分支为 `codex/rae-stage1-real-20261104`；此前未推送研究分支完整保留，未整体带入。
- 网页会话已读取最近轮次；助手正文接口返回引用占位，具体实现以用户本次请求及附件规格为准。
- 完成口径：`Implemented`、`wiring_passed`、`autonomous_constructed`、`measured_improvement`分开。T8可选；新机制默认关闭、不部署。

## 连续研发审计修订（2026-11-04）

以下原矩阵主要描述确定性机制检查，不能等同真实 Controller 已自动接通。连续研发发现：`BuilderConstructionSession` 仅由诊断驱动实例化，真实 Frontier 未传入；宿主编译器函数也没有可复用的原生认证后端。因此 T6 的**真实构造接线仍待补齐**，原解析/冻结检查只记 wiring。当前改为复用实际 Builder 为新 helper 准备训练输入的 Script 前缀，不把诊断证书移入运行配置。

真实历史图还暴露嵌套参数投影缺口，已增加保留原 schema/参数来源的可逆投影；只读成功 Script 组合可从原 native stdout 和每节点 SHA 恢复。完整重复模式的拒绝保留，原 learner 可自动发现受支持的局部窗口。连续研发详细证据与失败见后续实验记录；未完成阶段不计通过。

## T0 最小机制审计

| 机制 | 当前已有 | 缺失/本轮最小位置 | 兼容性与风险 |
| --- | --- | --- | --- |
| 身份/协议/发布 | `capability_contract.py/.ts`固定身份与原IR；`capability_store.ts`原子发布、独立验收、旧版本；`capability_cycle.ts`后继执行 | 复用，不创建新Registry或IR | 不改原能力ID和旧证书 |
| 实际执行 | `capability_runtime.ts`固定snapshot、权限/版本/证据守卫、父子回执；原后端完成实际执行 | 保留实际入参与外层binding，通过新的离线轨迹适配供学习 | 回执hash不能凭模型描述构造；不同owner/版本不能混用 |
| 图闭包 | 原Motif miner/compiler可处理类型化tool与参数流；Builder可显式组合C | `capability_motif_learning.py`将真实CapabilityCall投影到原学习器，再机械转换回原compose proposal | 不把手写D图称为发现；不猜同值即数据流；两训练与独立留出 |
| 可信交接 | RSI obligation与Capability Runtime已有检查；没有完整Capability级义务消解/remaining frontier | `capability_discharge.ts`连接冻结的宿主义务、独立predicate、Runtime回执 | 未知/不合格义务保留；组合新检查保留；取消与证据变化不能静默成功 |
| 演化 | `CapabilityFeedback`已记录执行/构造并影响排序 | `capability_evolution.py`把有证据的边界提案送原学习器，产生新图/新版本；增强证据关系区分 | 不混合双价值成任意总分；未知成本不产生收益或额度 |
| Builder自应用 | `capability_source_authoring.py`有真实静态解析/绑定，`capability_program_encoding.py`冻结构造意图 | 原Builder显式研究会话记录这些结构操作的实际调用，role=builder进入同一学习器；经认证组合可接后继相同入口 | 不另建MetaAgent；宿主验证/预算权限不由产物改变；禁用沿原路径 |
| 可见抽象 | 当前context提供原生与语义接口，含内部定义 | 在研究入口提供契约摘要；原始内部定义/轨迹单独审计 | 不能仅压缩提示称作Separation |
| 回归/入口 | npm test、smoke、motif:check、rsi:check、rsi:efficiency:check、rsi:improve | 本轮增加可复现的RAE机制验收与矩阵 | 确定性真实数据流属于wiring，不等于模型自主构造 |

## 文件分工与集成顺序

1. 图闭包：原Runtime实际调用 → `capability_motif_learning.py` → 原miner/compiler/certifier → 原compose/Store → 下一代同路径。
2. 交接：`capability_discharge.ts` → 原Runtime/宿主独立验证 → bounded summary与剩余义务。
3. 演化：旧Feedback → 有来源的边界提案 → 同一图学习接口 → 原认证/新版本发布。
4. 自应用：原Builder结构操作 → 上述相同图学习入口 → 已认证构造原语 → 原Builder研究入口；宿主可禁用恢复。

前三项由独立子智能体实现专属文件；主智能体负责共享入口、自应用和验收集成。所有生成源码、真实日志、私有任务留在`.local/`，公共测试只含可分享诊断数据。

## T0–T8验收矩阵

| 项 | 目标 | 状态/证据 |
| --- | --- | --- |
| T0 | main/实际模块/兼容边界审计 | 上次远程核对为 `5d73a4b9`；本次远程认证不可用，已完成当前研发源码审计，不能称新核对最新 main |
| T1 | 宿主可信有界义务消解及失效回退 | `test_capability_discharge.mjs`：适用/权限/版本/证据/取消/组合新检查，未处理项保留 frontier |
| T2 | 原Runtime实际调用与受限摘要 | 同上，实际 Python 原生操作与完整回执；`test_capability_abstraction_view.py` 验证模型只见语义接口、内部审计保留 |
| T3 | C→真实G1→原miner/compiler产生D→发布→G2 | `test_capability_motif_learning.py`：实际发布 C、执行 G1，原 learner 学出 D、原 Store 发布，执行含 D 的 G2、继续学出并发布 E；原 DAG 拒绝前向/自引用 |
| T4 | 反馈驱动新边界候选及新版本 | `test_capability_evolution_runtime.py`：三节点旧边界实际验证失败；反馈参与两节点候选生成，同一学习器编译、独立发布新版本；完整任务另执行剩余节点 |
| T5 | 双价值/证据关系/费用未知 | `test_capability_evolution.py` 及原 feedback/efficiency 回归；材料阅读、编译引用、实际调用和独立测量分开；未知不产生额度 |
| T6 | Builder构造轨迹进入同学习流程并回用 | 原解析/冻结仅诊断驱动；现已接真实 helper 训练材料前缀，`test_builder_program_learning.py` 验证原学习/Store/后继消费与禁用恢复。真实模型本轮未产生该前缀，真实自应用 Research Pending |
| T7 | Python/Node/Motif/RSI回归 | 见[本轮执行记录](experiments/rae-mechanism-20261104.md)，包含公共学习与原 improvement 发布入口 |
| T8 | 小规模真实模型 | 连续研发11请求含失败；最终完整程序发布及后继通过，C调用0。另有真实历史图学习候选发布/复用通过；不能合并成一次新模型自主递归证明 |

## 实际闭包与最小复现

```text
原 Store 发布 C
    ↓ 原 Runtime 真正执行（外部 binding + 可展开内部 receipt）
G1 = [CapabilityCall(C), 原语]
    ↓ 原 Motif miner / compile_read_motif / certify_read_motif
原 Capability proposal → 原 compile_proposal → candidate D
    ↓ 宿主冻结的新输入与检查器 → 原 Store → published D
G2 = [CapabilityCall(D), 原语]
    ↓ 同一个学习与认证算子
published E
```

```sh
npm run rsi:rae:check
npm run rsi:rae:learn -- --manifest .local/MANIFEST.json --output .local/NEW_PREVIEW
npm run rsi:rae:learn -- --manifest .local/MANIFEST.json --output .local/NEW_LEARNING --execute
npm run rsi:improve -- --plan .local/PLAN.json --execute
```

第一个命令直接复现 T1–T6 并在新的 `.local/rae-check-<UTC>/` 保留完整 Runtime/Store/学习证据，不需私有论文或模型密钥。后三个入口用于宿主自己的固定输入，格式见[接口](interfaces.md#recursive-abstraction-evolution2026-11-04)。学习输出的 `candidate_ref` 放进原 plan 的 job.learned_candidate；必须配置 `recursive_abstraction.enabled=true`，独立发布计划仍由场景提供。新入口不认证自己、不创建第二个 Registry/Controller。

T3 诊断中的初始 C 由宿主指定并独立发布；后代 D/E 的完整 proposal 是原学习器从实际调用轨迹生成，未手写。T4 使用确定性宿主提案器根据真实失败反馈选择边界，不能当成模型自主抽象。T6 输入为不同的真实 Builder 源码构造，运行的解析/绑定是原代码；初始叶权限属于明确标记的诊断宿主，后代组合必须完成原 Store 验收。全部仅为 `wiring_passed`。

## 修改文件与权限边界

| 文件/组 | 实际职责 |
| --- | --- |
| `capability_motif_learning.py` | 将真实 Capability 调用接到原 Motif discovery/compiler，保留跨代节点与来源 |
| `capability_discharge.ts` | 原 Runtime 前后宿主义务、独立验收、有限摘要及剩余检查 |
| `capability_evolution.py`、`capability_feedback.py` | 有来源的双价值关系、边界提案/新图、原计量复用 |
| `capability_builder_application.py`、`capability_source_authoring.py` | 原解析/冻结操作的可选真实轨迹会话及已认证组合复用 |
| `capability_proposal.py` | 语义摘要视图、固定契约、repair模式守卫、原 Builder 可选会话 |
| `capability_scene.py`、`capability_improvement.py`、`capability_construction_history.py` | 冻结学习产物进入原构造/发布链，记录来源，不自行晋级认证 |
| `capability-improvement-v1.schema.json` | 仅添加可选开关与 job 候选引用，旧 plan 保持兼容 |
| `learn-recursive-capabilities.py`、`run-capability-improvement.py`、`check-recursive-abstraction.py`、`package.json` | 默认预览/显式执行/可复现验收 |
| `tests/test_capability_*`、`test_recursive_learning_cli.py`、`tests/fixtures/rae_*` | 原进程实际执行、负面守卫及独立验证，不接真实模型 |

## 已实现与仍待研究

**Implemented / Mechanism Verified：** 同一个学习算子能够反复消费含已学能力的后代轨迹；反馈能改变下一候选可执行边界；Builder 结构操作能参与同一流程。认证/版本/权限仍由原宿主控制，旧生产路径、能力版本与费用账本保留。

**Research Pending：** 在真实任务流上自主发现有用边界、模型自然采用后代抽象、同质量全成本 Creation Efficiency、持续跨代正反馈和一般性。没有本轮收益测量，不能抹去过去已观察的复用收益，也不能把过去收益归给本轮新机制。

实现范围是只读、嵌套封闭必需字段对象、JSON数组参数与原编译器支持的连续区域。嵌套可选参数、任意 MCP、副作用任务、原编译器不支持的同名重复节点不偷偷降级，而是记录 unsupported/rejected。独立验收器与场景输入需要宿主提供；本轮未让正常聊天自动启用演化。

原解析与冻结绑定自应用仅由诊断驱动接线，保留原编码器一致性复算。连续研发将真实 scene/Frontier 的 helper 训练材料准备接入同一机制，默认关闭；学得前缀需在当前库认证并与原参数关系严格一致才可替换。当前只有诊断纵切验证后继消费，未观察真实自主采用，也不宣称构造效率提升。

关闭开关或不注入 construction_session 即回原路径；研究产物留在私有独立目录，不删除旧版本。整个分支可直接弃用而不影响正式服务。未修改上游 Harness、共享账本或原 Capability 身份协议。

## 权限与交付

已授权创建独立PR，不合并、不部署。首轮诊断模型调用0；连续研发真实调用、费用和失败见[最新记录](experiments/rae-followup-20261104.md)，沿用原账本。开发起点已成功核对远程main；最终推送阶段HTTPS凭证不可用，现有SSH key对目标仓库无权限，浏览器登录不能代替Git推送权限。首轮机制提交和本轮增量在本地保留；最新测试与未通过研究门禁以连续研发记录为准。推送/PR/远程CI待Git访问恢复，不能写成已创建PR。原凭证和远程配置未改。PR正文与补交命令保留私有`.local/rae-pr-body.md`，Git bundle保留本轮提交。

交付更新（2026-11-04）：本机GitHub认证已恢复，已核对远程main `690d2340`且合并预演无冲突；分支已从Mac推送并创建[PR #132](https://github.com/jingyio/GeneLoop/pull/132)。当前远程CI运行中；前述认证阻塞属于此前状态。未合并、未部署。


## PR131 合并后的兼容整合（2026-11-04）

以远程 main `eda9409b` 整合 PR132，文档冲突保留两边接口和交接。首次全量出现17项 Python、1项 Node 失败，原因为三个公共控制器文件的源码锁变化，旧库按约定拒绝加载。原始失败留在私有 `.local/pr132-133-integration-20261104/`。

沿原 `reexport-ppt-managed-compat.py --rae-integration --write --update-registry --validation-record docs/rae-implementation.md` 导出 PPT76/Paper78，原库保留，`library.json`、`online-manifest.json`、`task.json`、`tool-schemas.json`、`source-evidence.json` 保持字节一致。新证书绑定当前控制器及RAE依赖，未重新挖掘训练或调用模型。独立验收、关闭开关与旧版本拒绝检查继续执行。最终回归及远程CI以PR最新head记录为准，真实自应用和收益研究仍待验证。
