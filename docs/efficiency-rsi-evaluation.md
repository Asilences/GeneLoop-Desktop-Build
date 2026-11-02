# 效率 RSI：冻结研究条件与离线测量 v1

本模块独立评价执行成本、构造成本与能力可达性，不是发布策略或执行授权。新增能力可以在 baseline 失败时形成研究证据；既有 `rsi_optimization` 的费用型发布门槛保持原样。不要为发表能力收益而降低产品发布质量或权限守卫。

代码入口为 `src/adapters/efficiency_rsi_measurement.py`，跨入口结构见 `schemas/efficiency-rsi-study-v1.schema.json`，CLI 为 `scripts/measure-efficiency-rsi.py`。本轮仅实现离线验证/核算与合成回归；不代表真实能力增长、实付节省或持续 RSI 已通过。

## 最小实验矩阵

在任何评测运行前冻结任务来源、模型/版本/提示与工具顺序、压缩/缓存/重试策略、质量规则、评测器、研究预算、随机重复与能力快照。`conditions_sha256` 绑定有效配置的规范化快照；题面 `sha256` 绑定实际题面版本。每个 task × replicate × phase 都必须覆盖全部组，相同预算及尝试上限。预注册后的任务不得因 baseline 失败被删除。

| 独立研究 | 组间变化 | 主评价 |
| --- | --- | --- |
| 执行复用 | 执行可见能力快照；构造可见集相同 | 全任务成功率、双方成功的条件成本、真实调用见证 |
| 构造复用 | 构造可见能力快照；任务与初始预算相同 | 构造成功率、首成功成本、失败/耗尽、结构依赖与跨代调用 |
| 预算再投资 | 预注册资源分配规则；独立 study ID | 分摊学习成本后是否产生更多合格新能力 |

执行与构造用不同 `phase`，预算再投资使用独立 study；本版没有自动调预算或探索循环。A/B→C→D 不能写成固定场景 DAG；由 Agent 在相同题面下生成 C/D。快照引用只证明暴露条件；真正的组合/跨代主张还需要 runtime 调用见证和生成谱系，本测量器不会从依赖图自动推导“已实现 RSI”。

`tasks[].split` 为 `training`、`validation`、`final_test`。训练任务不能进入评价 cell；相同题面哈希不能改名跨集合复用。在线选择/修复只能用 training/validation，最终 heldout 在冻结后独立执行，其质量记录不得作为优化反馈。检查哈希只能识别字节相同的泄漏；相近题面的独立性仍需人工审核。报告保留 split，并给每组独立 split 分母；跨 split 汇总仅作库存统计，不能当论文最终测试成绩。

## 接口与信任边界

```python
validate_study(plan: dict) -> dict
measure_study(plan: dict, observations: dict, *, registry: dict, evidence_root: Path) -> dict
```

三个 JSON 都由同一 schema 的版本化定义校验：

- `efficiency_rsi_study_v1`：固定任务/组/cell 清单、条件/质量规则摘要、评测器文件引用、研究预算和 overhead 分摊政策。
- `efficiency_rsi_registry_v1`：可信 runner 的独立完整库存；绑定 plan 摘要，包含每个 cell 的有序 attempt IDs/closed 状态，以及 `overhead_ids` 与唯一 `request_refs` 全集。
- `efficiency_rsi_observations_v1`：绑定 plan 和 registry 摘要；包含所有 attempts、overheads、provider 账目，包括失败、重试和未结算预留。

registry 在运行中由 runner 独立追加，导出后冻结。它不能从筛选后的 observations 反推。即使尚无尝试，每个预注册 cell 也必须在 registry 中；未执行 cell 仍占分母。所有注册 attempt/overhead/request 必须完整导出，遗漏失败尝试或整段学习及其请求均拒绝；每个请求唯一归属一个 attempt 或 overhead。重试顺序和 parent attempt 必须与 registry 一致。

摘要能验证绑定和导出内部完整性，不能认证伪造的 registry 或评审身份。可信 runner/reviewer 的获取、不可变存储、预注册时间与独立评价隔离仍是研究执行责任。CLI 不执行评测器，也不证明 Agent 未看过 heldout。导出中的花费使用 proxy 估费，不冒称账单实付。

能力引用沿用 T1：`{id: "cap_" + sha256[:24], sha256: revision_sha256}`。执行/构造快照摘要及可见引用分别固定，attempt 必须精确匹配对应 arm；非空引用要求快照摘要。这些引用不会授予执行权限。完整快照真实性及可执行性由 capability/runtime 验证器负责。

## 质量与结果分母

复用 `rsi_quality.quality_status`、`verify_quality_files`，校验 task/artifact/rubric 摘要、必需 checks、冻结 evaluator ID 和真实文件。评测器源码本身也核对冻结摘要。正例须为 `completed` 且独立质量 passed；技术退出成功、空 quality 或 artifact 存在均不足以判成功。

每组分母始终为全部预注册 cells。区分 `success`、`failed`、`budget_exhausted`、`not_observed`、`pending`、`unreviewed`、`infrastructure_error`、`cancelled`，并另列 `success_over_budget`、`success_budget_unknown`。`complete` 只表示 cells 均关闭且有尝试，不代表全部质量已审或实验成功。基础设施失败、取消、缺评和未观测均不构成能力不足证据。

对照分别报告 `both_success`、`capability_unlock`、`capability_regression`、`both_unsuccessful`；其余为 `unresolved`。baseline 耗尽/质量失败而 candidate 成功可进入能力增益格，无须 baseline 全部成功。只有双方在预算内成功且费用已知，才计算条件成本差；失败 baseline 的“成功费用”和“节省率”保持 `null`，不取无穷大或伪造反事实。

首成功成本累计该 cell 首成功前所有尝试、失败和重试。没有成功则成功获取成本为 `null`；budget exhausted 单列右删失与实际已花费，不将其解释成达到成功所需的真实成本。框架错误或未运行不是预算删失。不能只保留两边成功的任务报告整体收益。

## 预算与费用口径

v1 明确冻结 `budget_scope: attempt_execution`：cell 预算包含它的全部尝试请求，**不包含共享学习/认证等 overhead**。报告的 `success_rate_scope` 明示这一点；当前预算内成功率不能称为“包含构造/认证的全生命周期同总预算能力率”。`budget_policy: research_comparison_not_platform_authorization` 只定义研究控制，不重设平台额度、既有累计支出或副作用授权。要验证预算再投资的全生命周期能力率，后续须预注册新增总预算策略版本和成本归属，不可改写本版字段语义。

请求按 `(ledger_ref, id)` 去重：相同记录只计一次；booked→completed/failed 为一个物理请求，终态替代预留；相互冲突终态或分摊变化拒绝。未知费用保留 `null`，同时给已知小计、未知请求和可得的预留上界。预留上界不是实付支出。

| 字段 | 口径 |
| --- | --- |
| `physical_study_cost` | 全部唯一 provider 请求的物理总估费，含失败及 overhead |
| `arms[arm].allocated_cost` | 按预先冻结比例分摊的全组估费；共享学习不重复计物理支出 |
| `study_only_cost` | 单列纯研究评审等预注册 study_only 分摊 |
| `cells[].cost` / `first_success` | 当前 cell 全尝试 / 首成功为止的请求估费 |
| `amortization` | v1 为 null；未假定未来复用次数或摊销分母 |
| `billing_usd` / `non_model_costs` / `total_economic_cost_usd` | v1 为 null；未接入账单、人工/工具/机器/维护成本，不得声称完整经济成本已计量 |

attempt 的请求必须全部归属它所在 arm；overhead 的生成、学习、修复、认证、验证、维护、恢复和研究评审按 `overhead_allocations` 预注册守恒权重。未声明分类、遗漏账目、重复归属或 orphan 请求拒绝。必须记录包含失败的全学习谱系；“共享”不能成为删除其支出的理由。工具收费、人工修订、耗时和部署维护仍需独立收集，本版模型费用核算不能代替这些证据。

## 免费本地验证与后处理

```sh
python3 scripts/measure-efficiency-rsi.py --study .local/study/plan.json
python3 scripts/measure-efficiency-rsi.py \
  --study .local/study/plan.json \
  --observations .local/study/observations.json \
  --registry .local/study/registry.json \
  --evidence-root .local/study/evidence
python3 -m pytest tests/test_efficiency_rsi_measurement.py -q
```

使用已安装 requirements 的项目 Python 环境；CLI 只读本地 JSON/证据文件并向 stdout 输出 JSON，不调用模型、不运行工具、不发布能力。原始导出和证据保存在私有 `.local/`；合成测试只检验协议和计算，不能替代真实 Agent 验收。
