# RAE 递归机制验收：2026-11-04

## 问题、范围与证据等级

本轮验证同一个 Motif 学习算子能否反复消费包含已认证能力的真实执行图，以及反馈能否改变下一候选边界、Builder 自身构造轨迹能否进入相同路径。任务为可公开的确定性诊断，执行通过实际 TypeScript Runtime、Python 原生操作、原 Motif miner/compiler 与原 Store。不是真实模型自主创造实验。

初始主线经远程核对为 `5d73a4b90e4121e94c9e7240bc8823e8b6bb3bff`。完整设计、文件清单、T0–T8矩阵见[实现记录](../rae-implementation.md)。最高证据等级为 **wiring_passed**；autonomous_constructed 与 measured_improvement 本轮均未取得。若学习器不能消费 CapabilityCall，或后代必须人工重写 proposal 才能发布，T3 不成立；若 Builder 仅收到 guidance 文本，T6 不成立。

## 冻结条件与实际结果

| 项目 | 操作与观察 |
| --- | --- |
| 图闭包 | 独立发布 C 后，G1 实际调用 C 与 double；两份训练、一份留出进入原 Motif miner/compiler；生成 D 的原 compose proposal，独立 Store 验证及后继通过。G2 实际调用 D 与 subtract，同一学习器继续生成 E 并独立发布。D/E 未手写 |
| 参数和认证 | C 对 x 返回 x+1；D 对 x 返回 2(x+1)，发布验证输入11返回24，后继输入17返回36；E 返回2(x+1)-3，独立相应结果21/33。Capability 外层节点数不受内部展开层数影响，内部回执仍可核验 |
| 可信交接 | 实际执行已认证能力并通过宿主 predicate 后，只将有界义务标为已处理；权限撤销、证据错位、版本/状态变化、取消均保留或退回 frontier，组合新检查不丢失 |
| 形式演化 | 三节点能力能完成原任务，但用于更窄的局部义务时实际不合格。该失败进入原反馈后，确定性提案回调选择两节点区域；同一学习器生成不同ID/可执行体，经独立 Store 发布。旧版本与失败保留；后续单独执行原第三节点可恢复完整任务结果 |
| 双价值 | 阅读/提议不能增加执行或已测因果信用。编译引用、Runtime调用、验证使用分别绑定来源。计量复用原费用协议；未知总成本保持 null，零模型请求不推导零总成本 |
| Builder自应用 | 对不同源码构造实际执行原解析、冻结绑定阶段，捕获role=builder的Runtime轨迹；同一学习器学出组合，经两个新构造输入独立验收发布；下一Builder以一个外层Capability调用使用该组合。默认关闭恢复旧路径；候选不能改验收器 |
| 公共入口 | 学习CLI默认preview、显式execute输出candidate_ref；原scene.construct重新编译核对身份和host contract，原controller/Store独立发布D；没有第二套Registry或RSI循环 |

原语初始授权、义务、任务输入和提案器是公开诊断夹具；后代执行、参数绑定、学习、认证、发布、失败是实际过程。T4 的确定性边界提案不代表模型会自主发现该边界。T6 为原解析/绑定构造阶段复用，仍复算原编码器进行一致性验证；没有证明后继构造更便宜。无真实API请求，不用模拟Provider替代T8。

## 配置、证据与复现

```sh
npm run rsi:rae:check
TMPDIR=/private/tmp npm test
npm run smoke
npm run motif:check
npm run rsi:check
npm run rsi:efficiency:check
```

macOS需要可绑定本机端口的测试环境。`TMPDIR=/private/tmp` 避免系统 `/var` 与 `/private/var` 别名干扰已有严格文件身份检查；没有放宽生产守卫。Linux/Windows继续使用CI原流程。

验收原始记录保存在私有 `.local/rae-check-20261103T185141823956Z/`（UTC目录时间；北京时间11月4日）。`effective.json` 包含HEAD、未提交范围、源码字节哈希、Python/Node、实际命令；`traces/`保留G1/G2/后代发布、Builder输入和回执；`python.xml`与`check-*.log`保留逐项结果。重新执行命令产生新目录，不覆盖失败。Git最终仅附可分享测试源，不提交私人原始轨迹。

T1–T6与公共入口专项：**60 Python + 35 Node通过**。smoke、Motif、RSI协议43项、效率RSI协议95项通过。最终全部Python **2256通过、241跳过**；全部Node **1587通过、21跳过**，均无失败。Python最终日志`.local/rae-python-final-20261104.log`，Node最终日志`.local/rae-node-stable-20261104.log`；Node使用原全测试文件集合、`--test-concurrency=2`，耗时99.78秒，Python187.07秒。跳过不算通过，尤其macOS未运行的Linux隔离用例不代表Linux原生验收。

## 失败与修复记录

1. 早期交接测试预期使用 A/B，而实际原生计数样例为 workshop/poster。修正测试预期后实际原生执行通过，没有更改执行器结果。
2. 历史测试通过 `__new__` 构造旧适配器，缺少新增可选 learned_candidates；读取改为可选空映射，旧调用保持兼容。
3. 审计发现直接Python研究Gate分支遗漏semantic_view转发，修复两种入口同时生效，增加enabled/disabled/semantic三个回归。缺失时只是暴露额外底层详情，不改变原认证。
4. 边界提案回调返回后校验失败原先缺少failure.json，现与回调异常共用记录，并覆盖响应格式、无关反馈、prior变化和feedback变化四种情况。
5. 首次专项将pytest临时目录保留在.local，旧新增测试却假定tmp_path在.local外。测试改为明确的仓库根下未建唯一路径检验拒绝；没有改私有输出边界。首次53项中的1失败及35项Node通过原记录保留于 `.local/rae-check-20261103T183959556229Z/`。
6. 第一次全量受限环境不能绑定本机HTTP端口：70失败、15错误、2164通过、241跳过，主要PermissionError。没有据此改运行逻辑；允许本机测试监听后完整Python通过。受限失败日志保留 `.local/rae-full-regression-20261104.log`。
7. 允许监听后的首次全量Node出现1项旧任务路由fetch failed，单项原测试随后通过。另一次Node命令漏设TMPDIR，触发严格路径与费用来源守卫，并出现另一旧并发HTTP fetch失败；这些失败保留，未修改旧生产模块。最终用真实临时路径及文件并发2运行完整Node集合，1587通过。HTTP失败未能在单项复现，不能宣称已修复其根因；完整日志分别保留为`.local/rae-full-regression-20261104-unrestricted.log`、`.local/rae-node-final-20261104.log`、`.local/rae-task-routing-recheck-20261104.log`。

## 费用、边界与下一步

模型请求 **0**，模型费用0；CPU/耗时、人工及维护总成本未计价为 unknown。原累计账本未修改，未发预算信用。诊断质量由冻结数值/构造一致性谓词验收，未做真实用户交付质量评审或盲评。

已证实的是受限协议内的递归可执行闭包。真实任务自然产生何种新边界、C是否提高D获取成功率/减少总成本、再下一代是否继续获益，仍需独立前瞻任务对照。T8本轮未运行是范围选择，不是缺少既有API测试授权。研究模式默认关闭；本PR不部署、不接管聊天，也不修改任何独立验收或预算权限。
