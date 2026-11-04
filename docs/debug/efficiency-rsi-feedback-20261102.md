# 正常记录到机会、双价值到选择：工程诊断

- 实验ID：`efficiency-rsi-feedback-20261102`；2026-11-02，Codex。
- 问题：旧视频/PPT学习链路已存在，但新Capability控制器依赖显式jobs，双贡献记录主要停留在journal。本轮检验这些记录能否实际进入构造队列并改变下一次行为，不检验统计收益。
- 范围：Source正常源码见证/Capability execute回执→自动生成机会→原控制器；执行/构造贡献→Builder展示、宿主准入执行候选选择、机会排序；精确版本撤回→后继过滤和恢复清单。默认不接产品聊天。
- 实现：新增`capability_observations.py`复用原`learn_programs.collect`，新增`capability_feedback.py`持久化事实和决策；`select-capability-execution.py`复用TS Runtime及固定独立检查器。检查输出增加trace/manifest/specification字节绑定，禁止借用其他任务QA。原始证据在构造前和发布前复核。
- 类型：合成离线诊断，包含真实Python→TS Store导出；模型/视频运行使用明确的诊断适配器，不把它们算作真实任务验收。新增模型、实际视频渲染、发布及部署均为0。
- 配置：本地macOS及隔离Linux候选检出；基于3a77af6加本轮改动，最终提交见Git。私有`.local/efficiency-rsi-feedback-20261102/`保留完整日志、公开代码归档与两端关键文件摘要。无模型配置、预算消耗或原账本改写；继承既有权限约束。

## 验证与反例

1. `npm run rsi:efficiency:check`：本地/Linux均172 Python、87 Node通过。新增27项覆盖：自动机会真正进入原控制器，重复输入不冒充多任务、heldout拒绝、原始证据中途变化阻止发布、QA错配拒绝；创造贡献改变实际模型上下文而别名固定；执行选择真正进入既有Runtime调用参数，独立质量结果再改变下次选择；未知费用、owner隔离、已发布机会跳过、重复失败暂缓、A→C→D传递隔离、无关B保留、恢复和执行归档边界。
2. Linux `npm run smoke`：18项portfolio检查通过，SDK初始化通过，paid_model_requests=0；日志含预期的未pin来源拒绝。
3. 本地全量 `npm test` 初次：1768 Python通过/236跳过；Node1470通过/13失败/17跳过。12项涉及macOS临时目录别名，1项上传typed413时`write ECONNRESET`。随后完成最后5项测试与小修订。
4. 将TMPDIR解析为真实路径后，相关失败文件定向复核48通过/1跳过；最终全量1773 Python通过/236跳过，Node1482通过/1失败/17跳过。唯一失败仍为`tests/test_model_transport_gateway.mjs`的“oversized upload already in flight still receives typed 413”。该失败此前已有记录，本轮未修改此运行路径；单独复核通过而全量仍复现，原因未定位，不能称全部回归通过或已修复上传问题。
5. 新命令`npm run rsi:select:source -- --help`可运行；Git diff空白检查通过。Linux使用单独候选目录，不覆盖正式服务代码或私有配置；11份核心代码/协议/测试文件的两端SHA256一致。

## 结论与接手

支持：上述限定场景机制的工程接线可运行，反馈确实改变后续输入/选择，不仅是写入字段。所有benefit仍为null，自动执行观测未取得模型成本时cost仍为null；没有成本对照或人工质量评审。

不支持：真实模型能够稳定从新机会抽象出有用能力、真实C→D、持续降本、全场景自动发现和收益再投资。场景仍需登记原始记录并提供context/独立验收配置；普通任务完成后尚未部署自动后台触发。旧无QA绑定记录不能补写为新入口验收。恢复队列保留但未自动调度，通用版本错误仅隔离已知失败根，不猜具体坏叶。

下一步：可按用户决定进行一次已登记真实记录的完整机制验收，或保留效果pending待大规模测试；不要为小样本正向结果加试。上传ECONNRESET留作独立定位项。本轮仅本地提交，未推送/PR/部署；协议与操作入口见[改进协议](../capability-improvement-v1.md)。
