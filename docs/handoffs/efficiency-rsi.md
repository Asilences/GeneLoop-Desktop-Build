# 效率 RSI 当前交接

- 更新时间与交接人：2026-11-02，Codex；本会话负责 A（计量正确性），B（Paper 真实闭环）由用户另开分支。
- 目标与本次范围：修复 F1/F2/F4/F5，补请求发出前的归属登记和独立导出；不增加模型构造循环，不接管聊天、不做生产发布。
- 分支 / commit / 工作区：`codex/rsi-real-acceptance-20261102`，基于已合并 PR #121 的 `71e3b7c`；本轮代码以本记录所在提交为准。私人 `reference/` 不跟踪，原库、失败日志、证书和累计账本保留。
- 提交与发布：A为`eba71e6`，B为`5efa221`；均已推送至[PR #122](https://github.com/jingyio/GeneLoop/pull/122)，目标main，未合并/部署。私人`reference/`保留且未提交；CI以PR当前head为准。
- 已完成：`efficiency_rsi_measurement.py` 分离全 cell 预算与首成功成本，保留质量观察和未知费用，十进制计量；registry v2 冻结请求的 owner/cell/category；`efficiency_rsi_registry.py` 用宿主 journal 登记并导出，`CumulativeProposalGate(..., study_registry=...)` 在原 booking 边界接线。接口及版本迁移见[评价协议](../efficiency-rsi-evaluation.md)。
- 已验证：本地完整 `npm test`：1835 Python 通过/237 跳过，1509 Node 通过/19 跳过，0 失败；最后路径预登记调整后本地/Linux定向各 69 项通过。`rsi:efficiency:check` 210 Python + 93 Node 通过；无模型 smoke 通过。它们是诊断回归，不是模型效果验收。旧上传 ECONNRESET 已在 main 中修复，不再列为当前未解决项。
- 本轮实验记录：[计量反例与修复](../experiments/efficiency-rsi-measurement-20261102.md)。未重新计算历史收益，不将新口径追写成旧实验结果；本轮真实模型请求和费用新增均为 0，账单、人工与维护总成本仍未采集。
- 配置与数据：私有 `.local/rsi-real-acceptance-20261102/` 保存修复前复现、A 回归日志及 `code-A` 快照/摘要；不提交原始轨迹。真实累计账本、生产配置均未改。工作区后续出现的 `script_motif_compiler.py` 及对应测试属于并行会话，A不修改、不提交；Linux A快照核验未包含这两份文件的后续改动。

## B 分支接手

**2026-11-03 B 更新：** 已在同一工作区基于 `eba71e6` 完成首个受控真实书目闭环，含显式工程恢复；27 条验证和 29 条后继各 4 项检查通过，新根进入下一 Builder。共 19 次真实请求（含失败），用量估费 USD0.018788928，原账本前缀不变；没有效果对照或 C→D 结论。B修复文件、回归/负面证据与剩余工作见[论文交接](paper-proofreading.md)及[真实记录](../experiments/paper-capability-real-20261102.md)。下列接手步骤按本轮开始前的准备状态保留。

1. 从包含 A 的提交分出或 cherry-pick A 后，先核对代码版本。B 的输入已准备在私有 `inputs-v2/`：同一真实 BibTeX 的 22/24/27/29 条互斥子集及来源哈希，原文件未改；它们不是多论文独立样本。此前已完成任务中只有算术诊断可供 Script 挖掘、候选为零，不能冒充论文历史任务闭环。
2. 真实执行前冻结 study/质量标准，先以全研究唯一 ID 登记 owner（可早于 attempt 目录创建），在实际 provider booking 边界调用绑定。提案网关已有可选接线；独立 Web runner 仍须显式接入，不能从 observations 反造 journal。导出本 study 的完整 booking/provider 请求库存，包含失败和未结算请求；结束时再关闭 cell。若仅做无界任务验收，报告质量结果，不能报告有限预算能力解锁。
3. 服务器隔离位置沿用 `/home/jingyij/jjy/.local/rsi-real-acceptance-20261102/`，运行前加载项目私有 `.local/remote-env.sh`。早先 `code-001` 是旧快照，不可当作 A 最终代码。原累计实验账本继续使用且串行访问；不要复用生产运行实例、重置费用或并行竞争同一账本。

## 既有机制和研究边界

- Source、论文 Script 原生能力/独立检查、材料学习/认证入池、公共构造/修复/反馈与发布生命周期已接线。Source 曾有真实构造与后继执行；Script 的公共闭环目前主要由原生诊断验证。正常 Paper 任务自动结束采集、论文真实历史驱动自主学习/组合仍待 B 验收。见[Source 真实闭环](../experiments/efficiency-rsi-source-loop-20261102.md)、[材料接线](../experiments/efficiency-rsi-materials-20261102.md)、[Script 接线](../experiments/efficiency-rsi-script-20261102.md)。
- 跨代结果保留：C 三次构造失败；D 修复后直接使用原语成功，没有调用 C。验证和后继执行各 4 视频/44 检查通过，不能称 C→D 或持续 RSI 成功；该轮 5 次真实请求估费 USD0.02025325。详见[递归尝试](../experiments/efficiency-rsi-recursive-20261102.md)。后续诊断改进见[离线重放](../experiments/efficiency-rsi-authoring-replay-20261102.md)和[反馈接线](../experiments/efficiency-rsi-feedback-20261102.md)。
- 未完成：真实跨代构造；新增公共机制的增量效率和大规模同质量总成本验证；自动再投资及创造价值因果估计；任意 MCP 适配；F8 深谱系；生产接管、任意中断自动恢复。当前 A 的 journal 与预算 checkpoint 不是跨文件事务，写入失败或中断后须先核对预留/归属，不能自动重建后继续报告。全平台请求完整采集、研究预算在线执行也不由离线测量器提供。
- 接手下一步：A 完成后由 B 做最小真实 Paper 端到端；之后独立开展 C→D 研究实验；生产自动演化启用前补恢复验收。不强求少量任务出现增益。
- 权限与预算：A 没有模型/外部应用调用。真实 DeepSeek 测试持续授权按 AGENTS.md，仍须记录实际模型/模式/上限并沿用原账本；外部应用写入、私人原件修改和实际投稿未授权。
- 回退与风险：撤回 A 回到 `71e3b7c` 可保留既有产品行为，但会重新引入旧计量问题，不能继续使用旧评价器报告公平收益。新 journal/导出留存为证据，不删除、不篡改；没有部署或重启生产。
