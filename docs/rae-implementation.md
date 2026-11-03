# Recursive Abstraction Evolution：实现与验收

- 规格：[用户提供的完整规格](GeneLoop_Recursive_Abstraction_Evolution_Codex_Spec.md)。
- 开始日期：2026-11-04；远程main经`ls-remote`与fetch核对为`5d73a4b90e4121e94c9e7240bc8823e8b6bb3bff`。
- 分支：`codex/recursive-abstraction-evolution-20261104`，在当前工作区从该main建立；此前未推送研究分支完整保留，未整体带入。
- 网页会话已读取最近轮次；助手正文接口返回引用占位，具体实现以用户本次请求及附件规格为准。
- 完成口径：`Implemented`、`wiring_passed`、`autonomous_constructed`、`measured_improvement`分开。T8可选；新机制默认关闭、不部署。

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

## T0–T8验收矩阵（执行后更新）

| 项 | 目标 | 状态/证据 |
| --- | --- | --- |
| T0 | 最新main/实际模块/兼容边界审计 | 已完成，见上表 |
| T1 | 宿主可信有界义务消解及失效回退 | 待实现/运行 |
| T2 | 原Runtime实际调用与受限摘要 | 待实现/运行 |
| T3 | C→真实G1→原miner/compiler产生D→发布→G2 | 待实现/运行；最高优先级 |
| T4 | 反馈驱动新边界候选及新版本 | 待实现/运行 |
| T5 | 双价值/证据关系/费用未知 | 待实现/运行 |
| T6 | Builder真实轨迹进入同学习流程并回用 | 待实现/运行 |
| T7 | Python/Node/Motif/RSI回归 | 待最终合流后运行 |
| T8 | 小规模真实模型 | 可选，另行记录实际模型/本批额度/输出上限；不以mock替代 |

## 权限与交付

本轮授权创建独立PR，不合并、不部署。实际运行使用原账本；不存在本轮新增模型调用时如实记0。gh当前未登录，Git remote可读；最终PR可复用已认证浏览器，无需改变用户凭证。先完成代码/测试/可审阅描述，再处理PR创建。
