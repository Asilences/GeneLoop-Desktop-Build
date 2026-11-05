# A：效率 RSI 计量修复与反例回归

- 实验 ID：`efficiency-rsi-measurement-20261102`。
- 类型：免费离线反例重放、booking 故障注入和回归；没有真实模型请求或新效果实验。
- 代码：分支 `codex/rsi-real-acceptance-20261102`，基线为已合并 PR #121 的 `71e3b7c`；本次实现以本记录所在提交为准。

## 问题与处理

此前已观察过程序复用收益。本次只修复研究核算，不能把“本轮未测增量收益”改写为“历史没有效率增益”。修复前的 F1/F2/F4/F5 在原基线上重新复现，私有证据保留在 `.local/rsi-real-acceptance-20261102/preflight/`；原审计目录未覆盖。

| 问题 | 原反例 | 本次结果 |
| --- | --- | --- |
| F1 费用范围混用 | baseline 首成功0.4，成功后再失败10；candidate0.2，预算各1，却报双方合规并节省10.2 | 全cell10.4判超预算，首成功仍为0.4；比较未解决、省费为null。后续只花0.1且仍合规时，物理费用0.7完整保留，首成功条件节省为0.2 |
| F2 请求归属漂移 | registry/provider均不变，将attempt请求挪到同臂overhead | registry v2固定request→owner/cell/category，测量拒绝；独立booking journal和可选网关接线在上游请求前持久绑定，结算不改变归属 |
| F4 无界/未知被当能力解锁 | budget=null，或成功费用未知，仍输出有限资源能力收益 | 保留质量观察，标记success_unbounded或success_budget_unknown；比较unresolved，不虚构能力解锁 |
| F5 浮点边界误判 | 0.1+0.2在0.3预算被判超支 | 十进制累计，0.3边界通过；0.3000000001仍超支。权重严格守恒，不用容差掩盖额外分摊 |

补充反例：cell未关闭、失败侧超预算、同名attempt目录、跨ledger相同request ID、库存遗漏/额外/重复、旧registry未绑定、journal残缺、冻结计划变化、写盘失败、JSON总金额溢出。修复不删失败或预留，不归零原累计费用和请求数。

## 配置、验证和复现

本地macOS；模型/provider/reasoning_effort均不适用。网关注入使用诊断凭证占位和不打开监听的替身，只直接调用既有 `State.book/log`；这是宿主记账测试，不是模型行为验收。原始数据、输入/日志和代码快照位于私有 `.local/rsi-real-acceptance-20261102/`，`code-A-sha256.json` 固定服务器验证快照。

```sh
node scripts/project.mjs python -m pytest -q \
  tests/test_efficiency_rsi_measurement.py \
  tests/test_efficiency_rsi_registry.py tests/test_capability_proposal_loop.py
npm run rsi:efficiency:check
TMPDIR="$(python3 -c 'import os,tempfile;print(os.path.realpath(tempfile.gettempdir()))')" npm test
npm run smoke
```

- 最新本地定向69项通过，日志 `targeted-A.log`。
- 本地完整回归1835 Python通过/237跳过、1509 Node通过/19跳过，0失败，日志 `full-tests-A.log`。该次全量后补了未来目录预登记兼容，随后最新69项定向覆盖该调整。
- `rsi:efficiency:check`：210 Python、93 Node通过，日志 `efficiency-check-A.log`；该次运行早于最后的未来目录反例增加。
- 无模型MCP smoke通过、SDK初始化通过，日志 `smoke-A.log`。
- 导出CLI→计量CLI串联通过，合成诊断产物保留在私有 `cli-A-*` 目录；未产生真实模型或收益证据。
- Linux隔离 `code-A` 快照69项定向通过，日志 `targeted-A-linux.log`；3052份快照文件摘要逐一一致，并核对其中Script编译器及其测试仍为基线版本，未混入并行会话后续改动。不启动正式服务，不调用模型。

## 结论与边界

F1/F2/F4/F5 的已知反例已由实现及回归覆盖。报告升级为measurement v2，registry升级为v2；历史原件和旧口径结果保留，不能只改format或从observations补造可信绑定。研究条件和observations仍为v1。

新journal只提供宿主登记与导出，提案网关显式传入才启用；其他Web/场景runner须在实际booking边界接入。全平台自动库存、在线研究预算执行、账单核对和任意崩溃恢复仍未完成。checkpoint预留与journal写入不是跨文件事务：写盘失败时禁止转发，保留原预留；中断后必须核对再导出，不自动重建。可信宿主本身或全部证据被重写也不能靠哈希证明真实性。

本轮新增模型请求0、模型费用0；没有质量收益、增量节省、完整经济成本或持续RSI的新结论。B负责真实Paper端到端验收；C→D与后续规模实验独立推进，生产自动演化仍未启用。
