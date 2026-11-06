# GeneLoop 公共脱敏模块

本分支以 main `d1863342` 为集成基线。公共脱敏能力不按 Paper/PPT 分支选择，现有场景和新增 MCP 场景共用 `src/adapters/geneloop_privacy.py`。在线 TypeScript 调用固定本地 worker，离线 Python 直接调用同一内核。正式服务没有切换。

## 数据流与入口盘点

| 边界 | 接线与用途 |
| --- | --- |
| Web / 桌面任务 | `dsh_web_tasks.ts`、`dsh_geneloop_tasks.ts` 在任务结算后异步生成 `privacy-learning.json`；真实任务默认尝试准入，mock 须显式诊断开关。桌面列表接收所有完成场景 |
| SDK / CLI / 研究运行 | `harness_runtime.create_harness` 组合 SDK 公开 run/close，先完成原关闭，再对本次原生事件生成账号私有视图。保留原 observer、结果、取消、费用与 journal；派生视图不是执行见证 |
| 离线导入 | `geneloop_learning_trace` 接收选定文件、当前任务起点、终态和有效工具目录，与两个 Web 宿主共用投影器 |
| Paper/PPT 结构学习 | 原 `rsi_learning_trace` v2 只保留登记工具、参数形状与已见证绑定，无正文和身份值。继续交原编译器及留出认证，保留成熟库兼容 |
| 轨迹 / 修订学习 | `dsh_trace_rsi_learning.ts`、`dsh_revision_rsi_learning.ts` 的模型可见结果和错误交公共内核。run/call/packet 使用单宿主随机句柄；已有私有审计保存句柄和原标识摘要，不导出映射 |
| Builder / Evolution | `capability_construction_history.py`、`capability_proposal.py`、`capability_goal_proposal.py`、`capability_evolution_investigation.py` 在历史进入模型前处理，包含初始上下文和工具返回。私有原件与模型实际可见值分别审计 |
| 编译 / 认证 | `continuous_motif_learning.py`、`capability_script_learning.py` 等在账号内核验原字节、执行样例及来源；模型提案走上述边界。脱敏视图不替代原证据，不授予认证或执行权限 |
| 导出 | 公共 operation library 强制 `admit_publication`；online manifest、efficiency registry、construction library 的 `--public` 同样准入。默认私有导出供原认证、账本和宿主桥接，保留原字节，不作为可共享对象 |
| 可选共享 | 两个任务宿主挂载 `harless_rsi_sharing.ts`，只从当前账号完成任务生成类型化 `tool_flow`；不接收客户端正文或任意路径 |
| 正常执行 / 交付 | 原始任务、附件、成品、费用及权限证据按原账号范围保存。公共派生视图用于学习；用户下载自己的文件和正常任务模型/MCP 访问沿用原授权 |

新增场景通过公共宿主或 SDK 工厂运行便继承接线，不需新增场景脱敏器。直接实例化上游 SDK、自定义学习请求或发布器必须使用此模块。外部 MCP 自身留存需其部署方管理；历史私有数据不会自动回填或改写。

## 契约与成熟工具

`learning_view(JSON)` 递归处理字段名和值，也处理工具 stdout 中的 JSON。复用本地 [Microsoft Presidio](https://github.com/microsoft/presidio) 的识别和 Anonymizer，别名使用官方 [custom operator](https://presidio.dataprivacystack.org/tutorial/11_custom_anonymization/) 扩展点；项目补结构字段提示和入口适配。身份映射仅在单次调用内有效，不落盘。固定 Presidio 2.2.365、spaCy 3.8.7 / 中英文模型 3.8.0、[Gitleaks 8.30.0](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.0)，依赖、模型 hash 与来源见 `requirements-rsi-privacy.txt`。

- 姓名、邮箱、电话、证件号、银行账号、住址、私有路径、附件名和账号/会话标识等替换为类型化别名；同一材料中相同实体尽量保持关联，文件类型保留。
- 任务正文、模型回答、工具参数/结果中的语义可进入账号内学习。公式、技术标识、代码、数值和统计要求不整体删除；字段名含身份信息同样处理。
- 凭证字段或 Gitleaks 命中直接拒绝整份材料。扫描处理前后内容及必要的 Unicode 归一化副本；工具缺失、超限或无法可靠处理同样拒绝，不回退原文或原异常。依赖按清单安装，验证时记录实际版本。
- 二进制、图像/音视频本体及相应 base64 不进入视图。当前不宣称识别人脸、声音或图片中的个人信息；未发表研究、商业机密和上下文间接身份没有自动识别保证。
- `admit_publication(JSON)` 要求处理前后相同，否则拒绝。它不改写或重签已认证源码/库字节，也不代替共享授权和对象白名单。

在隔离解释器安装 `requirements-rsi-privacy.txt`，将 `SSS_PYTHON` 指向该解释器，`SSS_RSI_GITLEAKS` 指向核对官方校验表的二进制。运行时不下载模型、不调用外部脱敏 API。所有学习材料仍视为受限数据，不能因通过识别就任意公开。

## 通用离线导入

提供当前任务的零基事件行起点及其冻结的 `effective-config.json`（`allowed_tools` 或 `tools[].name`）。

```sh
"$SSS_PYTHON" -m src.adapters.geneloop_learning_trace --authorized \
  --input .local/example/events.jsonl --catalog .local/example/effective-config.json \
  --scene future-custom-mcp --status completed --start 0
```

私有 v4 视图包含工具结构和脱敏 `content`，不保留原 call ID、时间戳、provider header 或二进制。SDK 输出附私有来源摘要，固定 `execution_witness:false`。无任务起点的旧任务不会猜测起点后共享。旧 v2/v3 仅保留给已有结构编译器和早期诊断，不限定模块覆盖范围。

## 默认私有与可选共享

对应 Issue [141](https://github.com/jingyio/GeneLoop/issues/141)、[142](https://github.com/jingyio/GeneLoop/issues/142)、[143](https://github.com/jingyio/GeneLoop/issues/143)、[144](https://github.com/jingyio/GeneLoop/issues/144)。轨迹共享、源码共享和可选遥测默认关闭；账号内学习不自动触发跨用户上传。

源内容先通过公共隐私准入，再生成 `geneloop.rsi-shared-object/v1` 的 `tool_flow`。v4 严格字段见 `schemas/rsi-shared-tool-flow.schema.json`。场景固定 `generic`，工具用样本内 `tool-0` 等代号，保留顺序、重复关系和结果状态；自定义 MCP 内部名称不上传。正文、语义内容、源码、附件、身份和自由扩展字段不在共享白名单内。流程对象不是可执行 Motif 或质量证书。

`/api/harless/rsi-sharing` 两个宿主共用处理器，先核验账号所有权。未知字段、嵌套敏感字段、失败任务、来源异常及脱敏失败均拒绝。

- `GET` 返回默认策略、共享是否可用及接收地址。
- `POST {action:"preview",task_id}` 返回完整冻结 JSON、字节数、SHA256、接收地址和十分钟预览 ID。
- `POST {action:"send",preview_id,sha256,consent:true}` 仅发送已预览且逐次同意的原字节。
- `POST {action:"cancel",preview_id}` 使未发送预览失效，发送中尽力中止并保留未知接收状态。

预览和同意仅当前进程有效，重启失效；每次只尝试一次，不自动重传、不跟随重定向或转发 Cookie。审计写入失败便拒绝预览或上传，审计只含固定事件与时间。桌面可查看、保存本地副本或取消，重新打开不恢复勾选。HTTP/WebSocket 自动出口继续使用 `apps/desktop/src/privacy.ts` 目的白名单。

私有 `GENELOOP_RSI_SHARING_ENDPOINT` 经两个服务启动入口进入策略；真实模式仅允许无用户信息、查询和 fragment 的 HTTPS，默认不设置。隔离诊断使用仅监听 `127.0.0.1`、随测试退出的接收端。正式接收服务的认证、持久回执和团队共享发布仍需独立验收。

## 验证与版本守卫

```sh
"$SSS_PYTHON" -m pytest -q tests/test_geneloop_privacy.py tests/test_harness_privacy.py tests/test_rsi_learning_trace.py
node --test tests/test_geneloop_privacy.mjs
node --test --test-name-pattern='platform privacy|RSI privacy' tests/test_dsh_web_tasks.mjs
```

服务器独立检出加载 `.local/remote-env.sh`，专项禁外网使用实际 Presidio/Gitleaks；全量按正确解释器、Node 兼容配置、字体及 `TESSDATA_PREFIX` 执行 `npm test`、`npm run smoke`、`npm run motif:check`。当前状态见[工程记录](debug/privacy-platform-20261106.md)，未跑完的检查不记为通过。

注册 Paper/PPT 库继续使用 `config/rsi-privacy-code-compat.json` 精确证书/当前摘要对并逐文件核验。私有旧候选按原守卫回退、重新认证。Windows Electron 真实进程用合成协议验交互；实际 NLP 在服务器验证。Issue 143 的 Mac 真实 Coding 仍依赖 DESK-01/04，不能以合成诊断替代。没有新增模型效果、科研质量或节费结论。
