# RSI 数据边界盘点与首版契约

基线为 GitHub main 5d73a4b。下表是源码入口盘点。正式服务器的私有数据存量、日志保留期限、外部 MCP 自身留存及生产配置需独立审计。

| 边界 | 入口与当前数据 | 首版处理 |
| --- | --- | --- |
| Web 与桌面 | dsh_web_tasks.ts、geneloop_task_trace.ts 记录原生任务、工具事件、续接和对照。桌面复用服务端接口 | 在结算后生成账号内隔离样本 |
| CLI 与独立研究 | run-scenario.py、harness_runtime.py 保存 agent-events.jsonl。独立实验脚本也读取私有日志 | 提供显式单文件导入，复用同一投影器 |
| MCP 与代码 | MCP 结果、PTC 子派发、原生命令、后台任务及上传衍生内容可能携带正文和凭证 | 只接收登记工具与原生调用/结果；其他工具只留固定原因 |
| 账户学习 | harless_paper_learning.ts、harless_ppt_learning.ts 与 learn-web-*-tasks.py 可读私有任务、账本和交付 | 本轮旁路验证契约，后续迁移消费者及其证据锁 |
| 研究学习 | dsh_trace_rsi_learning.ts、dsh_revision_rsi_learning.ts、continuous_motif_learning.py、capability_script_learning.py、capability_construction_history.py、scenarios 下独立入口 | 后续逐消费者准入，特别检查 Builder/反思发给模型的历史 |
| 导出与发布 | export-online-motif-manifest.py、export-operation-library.py、export-efficiency-rsi-registry.py、export-capability-construction-library.mjs，场景发布器与科研实验产物 | 后续检查回执、脚本常量、描述、证据索引和研究共享权限 |
| 展示、诊断与运维 | harless_public_output.ts、下载/预览、原生 journal、worker 日志、预算代理、服务日志 | 展示投影与学习契约分别管理；预算账本保留权威记录 |

复用现有 Python jsonschema 和 DSH 轨迹提取、来源核验逻辑。结构字段直接白名单投影，首版没有自由文本字段。Presidio 留作有明确文本需求时的自托管检测器。OpenTelemetry Redaction 可用于后续运维出口，云 DLP 对比只使用合成数据。

首版仅为隔离诊断。Web 需要 mock Provider、显式环境开关和指定 Python。离线导入需要显式授权标志，只导入操作员选定的文件。两端调用同一个离线投影器。采集结果没有账号 ID、任务 ID、源路径、原始哈希、提示词、参数值、正文或时间戳。边使用样本内的节点序号，未知工具只记固定拒绝码。该结构样本依然是账号私有数据。现有生产学习器迁移、正式用户授权、撤回、共享准入与历史回填分别后续实施。

## 隔离验证

在仓库根目录运行：

```sh
python -m pytest -q tests/test_rsi_learning_trace.py
node --test --test-name-pattern='RSI privacy' tests/test_dsh_web_tasks.mjs
```

离线导入显式提供终态和当前任务的零基事件行起点。Web 使用当前任务的 `trace_start_index`。测试使用合成原生事件和实际 Web 任务结算钩子，验证相同轨迹投影一致，模型请求为 0。

```sh
python -m src.adapters.rsi_learning_trace --authorized --input .local/example/events.jsonl --scene paper-proofreading --status completed --start 0
```

Web 仅在 `provider_mode=mock` 且 `SSS_RSI_PRIVACY_DIAGNOSTIC=1` 时运行。通过 `SSS_PYTHON` 或任务策略的 `learning_python` 指向安装仓库 Python 依赖的解释器。结果保存至任务私有目录的 `rsi-learning-trace.json`，拒绝只留下固定标志。诊断数据不提供模型、计费和质量评估。

首版改动触及既有运行时证书锁定的 Web 文件。生产上线前需按现有兼容验证与发布流程处理，不能直接部署这个诊断分支或跳过版本锁。
