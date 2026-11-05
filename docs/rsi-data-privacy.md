# RSI 数据边界盘点与首版契约

本轮集成基线为 GitHub main d1863342，继续使用原脱敏分支。下表是源码入口盘点。正式服务器的私有数据存量、日志保留期限、外部 MCP 自身留存及生产配置需独立审计。

| 边界 | 入口与当前数据 | 首版处理 |
| --- | --- | --- |
| Web 与桌面 | dsh_web_tasks.ts、geneloop_task_trace.ts 记录原生任务、工具事件、续接和对照。桌面复用服务端接口 | 在结算后生成账号内隔离样本 |
| CLI 与独立研究 | run-scenario.py、harness_runtime.py 保存 agent-events.jsonl。独立实验脚本也读取私有日志 | 提供显式单文件导入，复用同一投影器 |
| MCP 与代码 | MCP 结果、PTC 子派发、原生命令、后台任务及上传衍生内容可能携带正文和凭证 | 只接收登记工具与原生调用/结果；其他工具只留固定原因 |
| 账户学习 | harless_paper_learning.ts、harless_ppt_learning.ts 与 learn-web-*-tasks.py 可读私有任务、账本和交付 | Paper/PPT 账户学习的结构编译使用同一投影。私有任务资格、质量和费用仍由原证据验证 |
| 研究学习 | dsh_trace_rsi_learning.ts、dsh_revision_rsi_learning.ts、continuous_motif_learning.py、capability_script_learning.py、capability_construction_history.py、scenarios 下独立入口 | 后续逐消费者准入，特别检查 Builder/反思发给模型的历史 |
| 导出与发布 | export-online-motif-manifest.py、export-operation-library.py、export-efficiency-rsi-registry.py、export-capability-construction-library.mjs，场景发布器与科研实验产物 | 后续检查回执、脚本常量、描述、证据索引和研究共享权限 |
| 展示、诊断与运维 | harless_public_output.ts、下载/预览、原生 journal、worker 日志、预算代理、服务日志 | 展示投影与学习契约分别管理；预算账本保留权威记录 |

复用现有 Python jsonschema 和 DSH 轨迹提取、来源核验逻辑。v2 结构字段直接白名单投影。隔离 Web 和离线入口可显式选择 v3，额外生成经过本地 Presidio 和 Gitleaks 处理的任务指令。

独立 Web 采集诊断需要 mock Provider、显式环境开关和指定 Python。已有账户学习在其原来的权限和调度范围内通过同一个 Python 投影器处理入选证据。离线导入需要显式授权标志，只导入操作员选定的文件。v2 采集结果没有账号 ID、任务 ID、源路径、原始哈希、提示词、参数值、正文或时间戳。边使用样本内的节点序号，未知工具只记固定拒绝码。样本依然是账号私有数据。正式用户授权、撤回和共享准入分别后续实施。

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

### v3 任务语义诊断

v3 的 `task_intent` 来自指定任务事件段内第一条原生用户消息的文字部分，输入限 2048 字符。模型回答、工具参数和结果、附件本体、插件注入的附件文字以及后续对话均在此字段之外。Presidio 同时处理英文和中文实体，并通过其模式识别器处理常见文件引用和带标签的凭证。Gitleaks 在独立空目录从标准输入扫描处理前后的文字，命中凭证或任一步失败均拒绝整份语义样本。扫描报告不落盘。v3 仍是受限学习数据，任务指令可能含有未发表研究或可关联线索，正式学习和跨账号共享需要独立授权与准入规则。

在装有仓库基础依赖的隔离解释器中安装 `requirements-rsi-privacy.txt`。清单固定中英文 spaCy 模型的发布版本和 SHA256。使用 [Gitleaks 8.30.0](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.0)，安装前核对发布校验表。运行时从已安装模型加载，邮件识别复用 Presidio 的模式并跳过远程域名后缀查询。

```sh
umask 077
export SSS_RSI_GITLEAKS=/absolute/path/to/gitleaks
export SSS_PYTHON=/absolute/path/to/isolated/python
"$SSS_PYTHON" -m pip install -r requirements-rsi-privacy.txt
"$SSS_PYTHON" -m pytest -q tests/test_rsi_learning_trace.py
node --test --test-name-pattern='RSI privacy' tests/test_dsh_web_tasks.mjs
"$SSS_PYTHON" -m src.adapters.rsi_learning_trace --authorized --include-task-intent \
  --input .local/example/events.jsonl --scene paper-proofreading --status completed --start 0
```

隔离 Web 额外设置 `SSS_RSI_PRIVACY_SEMANTIC=1`。Web 与离线导入调用相同投影器和本地工具。Paper/PPT 现有结构编译仍读取 v2 样本，正式账号学习尚未启用语义字段。

## 默认私有与可选共享

对应 Issue [141](https://github.com/jingyio/GeneLoop/issues/141)、[142](https://github.com/jingyio/GeneLoop/issues/142)、[143](https://github.com/jingyio/GeneLoop/issues/143) 和 [144](https://github.com/jingyio/GeneLoop/issues/144)。

轨迹共享、源码共享和可选遥测默认关闭。现有账号内学习独立运行。正常 Agent 的模型请求、用户选择的附件上传和 MCP 访问沿用任务权限与认证。

| 出网目的 | 数据与入口 | 准入 |
| --- | --- | --- |
| 当前任务与账号 | 桌面 `apiPurpose` 登记的账号、会话、任务、附件、交付与事件 API；任务服务器的模型与 MCP 请求 | 按现有登录、任务和操作确认执行 |
| 跨用户演化共享 | `POST /api/harless/rsi-sharing`；仅限完成任务生成的 `tool_flow` | 服务端配置接收端，并逐对象预览和确认 |
| 源码、原始轨迹与可选遥测 | 未登记的共享、分析、崩溃上传 API | 默认拒绝；未知桌面网络出口同样拒绝 |
| 用户打开网页 | 用户点击外部链接后交系统浏览器 | 复用现有链接校验；独立于自动共享 |

`apps/desktop/src/privacy.ts` 为桌面 HTTP 与 WebSocket 提供出网白名单，`LocalFrontendHost` 在转发前再次校验。桌面只记录按目的计数，不记录请求正文、Cookie 或 URL 参数。共享服务的私有 `rsi-sharing-audit.jsonl` 仅记固定事件和时间，异常响应只给固定错误码及说明。

共享对象采用 `geneloop.rsi-shared-object/v1`，恰含 `format/kind/trace`。其中 `trace` 必须通过原 v2 JSON Schema 和结构编译入口的绑定校验。v3 任务语义、源码和附件不在首版共享白名单内。客户端只提交服务端已拥有的任务 ID；不能提交共享正文或任意文件路径。未知字段、嵌套敏感字段、来源不属于当前账号、失败任务、异常图或脱敏失败均拒绝。

接口使用以下动作。

- `GET` 返回默认隐私策略、共享是否可用和接收地址。
- `POST {action:"preview",task_id}` 从当前账号原始证据调用公共 Python 投影，返回完整 `payload`、UTF-8 字节数、SHA256 和十分钟有效的预览 ID。
- `POST {action:"send",preview_id,sha256,consent:true}` 只发送已冻结的预览字节，接收地址由服务端配置决定。重定向、Cookie 转发和自动重传均关闭。
- `POST {action:"cancel",preview_id}` 使未发送预览失效。已开始的请求会中止，并保留可能已接收的未知状态；本机及账号内学习原件保留。

预览与同意只在当前进程内有效，重启后需要重新预览。每个预览只允许一次发送尝试。网络中断后保留未知回执，接收端通过 `X-GeneLoop-Sharing-Id` 核对；界面重新打开时不恢复勾选。桌面设置的“数据与隐私”页可逐任务生成预览、保存本地副本、确认上传或取消。

独立测试接收端只监听 `127.0.0.1`，使用合成数据。真实配置由私有环境变量 `GENELOOP_RSI_SHARING_ENDPOINT` 经 `scripts/harness-web.py` 写入有效策略；默认不设置。真实模式仅接受不含用户名、密码、查询和 fragment 的 HTTPS 接收地址，开发 mock 模式才允许显式回环 HTTP。通用接收服务的认证、持久回执及实际团队共享发布须另行验收。

桌面诊断复现。

```sh
GENELOOP_PRIVACY_DIAGNOSTIC=1 SSS_PYTHON=/absolute/path/to/python npm --prefix apps/desktop run smoke:renderer
node --test tests/test_rsi_sharing.mjs tests/test_desktop_frontend.mjs tests/test_desktop_shell.mjs
```

工程诊断覆盖真实 Electron 进程、公共 Python 投影、私有 HTTP 接收端、预览字节、取消、异常和重启。Issue 143 的完整产品验收还依赖 DESK-01/04 的真实 Coding 与 macOS 链路，须按各自真实证据完成后再判定。

## 账户学习与证书兼容

- 新的 Paper/PPT 账户学习轮次采用 `geneloop.rsi-learning-trace/v2`，并把学习结构写入 `learning-trace.json`，用现有独立任务和留出认证流程编译。原任务和费用记录继续在宿主私有目录校验。用于去重的问句摘要及任务身份另存于私有身份清单，编译轮次没有原始事件、请求正文或答案副本。
- 投影在去除参数值前校验精确参数形状和版本化工具契约。旧 v1 诊断样本缺少参数形状保证，须从授权原始证据重新投影后才能编译。已见证的绑定进入编译器时使用样本内标识。无法确认是否与目标句柄相关的失败调用视为屏障，因此个别原本允许穿越无关失败的候选现在会被排除。
- 仓库注册的旧库使用 `config/rsi-privacy-code-compat.json` 中的文件路径、原证书 SHA256 和当前 SHA256 精确匹配。在线守卫收到当前摘要并继续逐文件核验。原证书、库文件和其他校验条件继续适用。账户私有证书按原摘要严格核验，代码版本改变时回退并重新认证。
- 历史手工研究编译入口保留原始回放模式，新的账户学习入口固定传入投影模式。上线仍须走独立候选与正式服务版本验证。
