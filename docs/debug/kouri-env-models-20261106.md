# Kouri 环境模型配置与真实冒烟

- 范围：新增 `KOURI_EXTRA_MODELS_JSON`，让私有 `.env` 追加模型名称、容量、能力与保守估费。默认模型与地址仍由 `src/adapters/model_api.py` 维护；正式服务需在新私有启动计划和独立预算进程传递相同配置。没有修改或重启运行中的服务。
- 离线验证：Python 模型/预算专项 34/34；Node Harness 模型与推理专项 7/7。`npm test` 本地全量为 2914 通过、261 跳过、94 失败、15 错误；受限沙箱的回环端口 `EPERM` 与旧源码锁导致大量失败。完整输出在 `.local/debug/kouri-env-models/npm-test.log`，不将全量失败解释为该功能已通过。
- 真实冒烟：引用 SkillFlow Healthcare baseline 第 3 题 `harbor_syncpack_28v56` 的首请求 `request-005419.json`（SHA-256 `24570197333c65bde0d25fda1a6f589b3aaff211bb1e57b78476ff9ff3dbfa8c`）。保留原三条消息、工具定义及 `thinking.disabled`；通过集中模型 API 映射发往 `deepseek-v4.1-flash`，诊断输出上限 1024，单次请求代理预留 USD 0.0025443，程序设 USD 0.01 代理预留门槛。密钥仅从项目私有 `.env` 注入，不打印或提交。
- 结果：HTTP 200，响应模型 `deepseek-v4.1-flash`，`finish_reason=tool_calls`，1 个 `mcp__research__execute` 调用且参数为可解析 JSON 对象。上游报告输入 1362、输出 56、总计 1418 token，缓存命中 0；按当前代理费率估算 USD 0.0004758。Kouri 账单实付未知，不能把代理估价当账单。原请求与响应保存在忽略的 `.local/debug/kouri-baseline-smoke/`。
- 边界：这只验证首个模型请求和工具调用格式，没有执行工具、继续对话或运行官方 verifier，不是一次完整 baseline，也不说明该模型在 9 题上的质量或成本。文件、搜索、推理档位和长输出容量仍待验收。

## PR159 / PR160 联合整合

- PR159 已合入 main，合并提交 `5e21c754056f5db8557d7a20869ec02b228b9741`。两个 PR 的五个共同改动文件可自动合并，没有文本冲突。
- 模型迁移会改变 Paper/PPT 注册证书绑定的八个运行文件：网关、Web 启动、原生宿主准备、独立预算服务、能力提案、预算代理、Web 任务与模型推理适配。审阅两侧差异后，仅在既有 `config/rsi-privacy-code-compat.json` 中记录精确旧证书/当前源码摘要对；证书、Motif 程序、工具 schema、历史证据和账本未改。后续其他字节变化仍由原守卫拒绝。
- 联合专项：Python 模型/预算、Paper/PPT 加载与拒绝修改、结构隐私投影 98 通过/11 跳过；跳过项需独立 Presidio/Gitleaks 安装。Node 模型适配与共享同意守卫 13/13，模型选择与隐私结算 Web 场景 4/4。完整回归及 smoke 结果见主线交接。该轮新增真实模型调用 0，正式服务未重启。

- 最终完整回归：本机回环端口获准后的隔离环境运行 `npm test` 退出码 0，Python 3036 通过/272 跳过，Node 1675 通过/25 跳过；`npm run smoke` 退出码 0。日志为 `.local/debug/kouri-env-models/integration-npm-test.log` 与 `integration-smoke.log`。此前受限沙箱的完整失败日志继续保留。
