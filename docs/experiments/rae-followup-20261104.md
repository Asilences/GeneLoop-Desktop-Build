# RAE 连续研发：真实图闭包与未完成门禁

## 范围与基线

本轮从 `b2329664` 开始，计划提交为 `fcd0e762`，分支 `codex/rae-stage1-real-20261104`。此前已验证远程 main 为 `5d73a4b9`；本轮 Git 凭证不可用，不能声称再次核对了最新远程 main。未合并、未部署、未切换生产服务。

按原规格 T0–T8，再按补充规格 Gate 0–4 顺序执行。真实 Builder 自应用未观察到之前，不把第二阶段反馈学习策略列为完成。

## 问题、实现与真实证据

### 真实调用图进入原学习器

原投影拒绝嵌套输入，真实 Script 组合的子调用没有独立根回执。新增投影从原 native stdout 恢复每节点输入、输出，核对原 SHA、版本、父子调用和显式参数来源。学习期的可逆 JSON 槽位映射恢复为原 schema/绑定，不改变 Runtime IR。

完整 `C,C,report` 模式仍被原编译器拒绝。保留完整观察，同时提供同一 trace 内受支持的不重复连续窗口，不增加独立任务支持数。原 miner 自动找到 `C→report`，没有手工选择学习区域，生成 10 条参数传递、11 个外部输入的局部候选。

训练用两组真实历史输入，留出一组；独立发布/后继用另两组历史输入。后两组以前用于原根能力验收，因此只称**本次局部学习候选的独立历史输入**，不称全系统未见的前瞻数据。

隔离 Linux `local-candidate-acceptance-002` 完成原 Script Runtime、冻结 Frontier oracle、原 Store 发布及已发布候选的 followup 调用，两个质量检查均通过。总耗时 29.8008 秒，其中恢复局部输入的原完整根执行为 8.7011 和 8.4004 秒；这些额外执行全部保留，不从成本中扣除。模型请求 0，总经济成本未知，不能宣称效率提升。

候选最初返回末步完整结果；验证入口只机械继承原认证根的纯末步输出路径以匹配原任务输出，保存前后候选身份与来源。它没有编写新的报告算法。公开入口：`scripts/validate-recursive-paper-candidate.py`，默认 preview，`--execute` 才运行，输出必须为新 `.local` 目录。

原失败 `local-candidate-acceptance-001` 保留：验收准备器取错了另一轮报告库，原版本守卫返回 `script_capability_leaf_changed`，0 dispatch。修正为原执行 trace 所固定 manifest 的 6 个库，没有改守卫、旧库或证书。

### 新模型真实构造

薄研究入口 `examples/capability-scenes/run-rae-real-acceptance.py` 复用原 FrontierAdapter、FrontierGate、Controller、原生认证和冻结质量检查。原任务明确允许组合或完整实现，没有指定 D 算法，也不强制 C。

| 运行 | 实际配置与结果 | 请求 | 模型费用（代理计量 USD） |
| --- | --- | ---: | ---: |
| `stage1-model-001` | 旧计划缺 `source_primary`，三份回答均在构造语法校验失败，无 Runtime | 3 | 0.006985032 |
| `stage1-model-002` | 明确使用已有 `source_primary_v1`，原生材料学习后通过发布及后继检查；完整程序实现，C 调用 0 | 8 | 0.040176468 |
| 合计 | 包含失败、修复及材料获取，不只计算最终成功请求 | 11 | 0.047161500 |

实际模型 `deepseek-flash`，`reasoning_effort=off`，输出上限 393216；本批研究额度 3 USD，沿用原累计账本和请求编号。各次尝试与材料获取完整保存。`max_repairs=2` 是固定材料池内的修复段；原控制器在认证材料增加后允许续构，**不是总请求数为 3**。45 分钟仅限制新请求准入。没有把平台累计预算改为 3 USD。

费用来自真实用量的既有代理计量，未与供应商账单核对。CPU、开发、维护及人工质量修订成本未货币化，总经济成本保持 `null`。冻结 oracle 只验收本任务定义的结构化结果，未声称人工盲审或一般论文审查质量。

### Builder 自应用缺口

审计纠正：原 `BuilderConstructionSession` 只有测试驱动创建，真实 Controller/Frontier 未注入。测试的宿主编译器证书明确属于诊断；现有 Script/Artifact 后端不允许直接导入宿主编译器，不能把测试证书改名后用于研究运行。

本轮改接真实已有的 `prepare_program_cases`：模型冻结能力前缀 → 原 Runtime 生成 helper 的训练输入。显式开启后记录 `role=builder`；经原 Store 认证的学习组合只有在符号展开与当前原前缀参数关系一致时才能承担该工作，验收、权限、预算不变。没有可用前缀或候选时保留原路径。

新模型运行全部选择完整 `program`，没有此类前缀。故该次业务成功不构成 Builder 自应用，更不构成反馈学习策略。不会为了制造前缀改写原轨迹、强迫使用 C 或反复采样挑成功。

## 验证与当前门禁

独立审计发现并修复输入列表重排造成虚假独立支持的问题。最终检查：

| 检查 | 结果与环境 |
| --- | --- |
| Python 全量 | macOS：2301 通过、241 跳过 |
| Node 全量 | macOS：1587 通过、21 跳过；测试文件并发 2，使用项目 Python |
| RAE 专项 | Linux：102 Python、35 Node 通过，完整 Runtime/Store 证据私有保存 |
| 最后适配与原生沙箱 | Linux：66 通过，显式 `RUN_SCRIPT_CAPABILITY_SANDBOX=1`；包含原公共 acquisition 与 helper 准备链 |
| smoke / Motif / RSI / efficiency | 均通过，RSI Node 43、efficiency Node 95；无新增模型请求 |
| build continuation / diff | 生成物一致性与 diff 格式检查通过 |

全量按 `npm test` 的 Python、生成物检查、Node 三部分执行；仅 Node 文件并发限制为 2，未删测试。测试通过不代表研究门禁通过。未运行远程 GitHub CI 或 Windows。

保留初轮环境失败：本地沙箱不允许测试端口，直接启动 Node 未继承项目 Python，造成依赖缺失；修正测试权限/环境后重跑。Python 全量另发现 3 项默认关闭兼容回归：多传 `builder_learning=None` 打破旧适配接口。改为仅两级研究开关均开启才传新参数，旧断言不变，并新增 3 项显式开关转发检查；之后全量通过。

- **Implemented**：真实 Script 组合投影、类型映射、研究验收入口；Builder 前缀接线通过独立审计与回归。
- **Wiring Verified**：已有 RAE 诊断；本轮独立历史候选已通过原 Runtime/Store/质量检查。
- **Autonomous Observed**：新模型自由构造并交付成功；尚未观察新模型递归复用或 Builder 自应用。
- **Measured Net Benefit**：无。本轮无匹配成本对照，不否定此前其他实验的复用收益。
- **Research Pending**：真实构造轨迹中产生可学习边界并在后继 Builder 使用；Gate 1/2 不计完成。

## 复现与私有证据

代码与输入均在隔离研究目录运行，未修改服务器原检出或服务。代码归档 SHA `4edd76744c18da60d629c46054c860587504726447244a090967bf98372dfc62` 对应 `fcd0e762`，后续补丁由各运行 `effective/frozen.code_sha256` 固定；无 Git 的归档不冒充祖先目录 HEAD。

原始证据位于两端私有 `.local/rae-followup-20261104/`，模型失败离线重放位于本地 `.local/rae-stage1-source-audit-20261105/`。原私有数据、模型回答和执行日志不入 Git。来源、任务、库、代码摘要、请求用量与 frozen verifier 在对应 `frozen.json`、manifest、result 和 Runtime receipt 中关联。

最短入口：

```sh
npm run rsi:rae:check
node scripts/project.mjs python examples/capability-scenes/run-rae-real-acceptance.py --source-plan ORIGINAL_PLAN --output .local/NEW_PREVIEW --budget-usd 3
node scripts/project.mjs python scripts/validate-recursive-paper-candidate.py --manifest MANIFEST --output .local/NEW_PREVIEW
```

需要显式 `--call-model` / `--execute` 才执行。模型只在已配置 Linux 服务器、沿原账本调用。关闭研究配置即保留原生产行为；回退不删除旧库、旧证据或累计账本。远程认证恢复前 PR/CI 状态保持未完成，不用本地测试替代远程结论。
