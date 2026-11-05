# 演化benchmark只读结果汇总

日期为2026-11-05。入口为`scripts/summarize-evolution-benchmark.py`，诊断为`tests/test_evolution_benchmark_summary.py`。

## 输入与输出

输入为一组实际实验输出目录及原`cost-ledger.jsonl`。原账本只读，汇总不创建新的请求分配或账本。

```bash
node scripts/project.mjs python scripts/summarize-evolution-benchmark.py \
  --run .local/results/<run-id> \
  --ledger-ref <original-ledger-root>/cost-ledger.jsonl \
  --output .local/results/<new-summary-id>.json
```

`--run`可重复。输出文件采用独占创建。复制结果在本地核对时，可用`--ledger-id`指定journal内原逻辑账本路径。Python函数`summarize`也接受现有FileRef作为账本输入。

输出按method、原session mode和任务split／label组织，包含以下事实。

- 原reward、明确阈值下的full quality、论文positive-reward条件分别保留。
- 原book与settlement request ID、cache hit／miss／output token、已知费用与未知请求。
- 原trial、session及provider的耗时。记录时长之和与整体wall time分别解释。
- 真实native skill加载、显式正文读取及可核验Runtime回执。
- 原生材料注册、递归候选和原发布状态，保留pending与失败。
- 原任务身份及相同输入清单的归并，重复运行和重命名的相同材料保持同一来源组。
- 比较条件及相同full-quality条件是否齐备。工具默认只报告这些条件，节省估计为空。

模型费用来自原ledger的`observed_peak_usd`，复用原`efficiency_rsi_measurement._cost`进行十进制与未知费用汇总。供应商账单、机器、人工修订与额外外部服务费用保留未知。

## 归属与去重

`CumulativeProposalGate`在upstream I/O前向原session的`requests.jsonl`登记booked request及ledger引用。原ledger结算记录包含request ID、attempt path、usage与费用。

汇总使用book归属，核对结算路径。同ID费用冲突保留未知，归属冲突单列。缺结算或usage的请求保留未知。父子输出目录重叠、根result复制子result、同一ID重复记录均进行去重。技能包与artifact等模型可生成目录排除于book／加载事件扫描。

booked-only请求表示已登记的尝试，其upstream派发状态保留未知。原请求与结果文件、原账本均保持。

## 已验证

原19项无模型汇总诊断在本地与Linux项目Python3.10均通过，覆盖嵌套去重、十进制、book归属、未知成本、部分quality、相同来源、原回执、递归候选／pending发布、失败和不完整journal。随后增加源码快照列表兼容，本地20项通过。列表按文件名与内容哈希汇总，忽略会话目录和顺序。与适配器36项及Harness23项合计本地79项通过。Linux原19项诊断输出保存在本轮代码快照的`.local/debug/evolution-benchmark-summary-20261105/pytest.log`。

真实`pilot-threejs-001`通过原账本只读核对。

| 事实 | 值 |
| --- | --- |
| 不重复请求数 | 86，全部已结算 |
| 原估算模型费用 | USD0.12637326 |
| cache hit input tokens | 6,775,808 |
| cache miss input tokens | 116,892 |
| output tokens | 42,209 |
| 原reward／full quality | 1.0／true |
| 原split | training |
| 原trial耗时 | 340.337秒 |
| 汇总警告 | 0 |

核对过程新增模型请求0。结果文件位于服务器本轮代码快照的`.local/results/summaries/pilot-threejs-001-facts.json`。该pilot的post-verification artifact继续排除于学习，质量与成本事实保留。
