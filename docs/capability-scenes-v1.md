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

当前主要缺口仍是：缺材料到既有学习器的自动分派；更广泛的原生工具适配；从普通任务结束事件自动收集新记录；更有辨别力的机会发现；匹配质量范围的净成本与创造价值估计。复用公共流程已经实现，普遍有效性仍需真实场景证据。完整命令、失败和运行位置见[本轮记录](experiments/efficiency-rsi-scenes-20261102.md)。
