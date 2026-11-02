# Source Capability 首个真实闭环

实验 ID：`efficiency-rsi-source-loop-20261102`。日期：2026-11-02。范围是 Linux 私有实验入口，不是生产网站发布。

## 结果与边界

已完成一次 **真实模型提出 Compose → 编译 → 新 TS Runtime 实际渲染 → 独立媒体检查 → 不可变版本保存 → 新任务加载并执行**。不是人工预写组合，也没有把候选先改成 certified 再验证。

| 阶段 | 实际发生 | 结果 |
|---|---|---|
| 构造 | 原 Harness / DeepSeek Flash 从四个已认证 Source 程序中选择剪辑与画中画，生成两步组合 | 1 次真实请求，首次提案编译通过 |
| 验证 | 两叶分别在专属工作目录和容器真实渲染 | 两份视频；23 项独立机械检查通过 |
| 保存 | Store 内部实际调用验证执行与固定独立检查器，保存全部证据后 CAS 更新 | 只晋级通过检查的组合根，旧叶与旧版本保留 |
| 后继消费 | 新 task、不同工作目录与参数，从 Store 重新加载组合 | 两份新视频；23 项检查通过 |
| 最终代码复验 | 收尾固定镜像 ID、父进程退出清理后，再调用已发布组合 | 两份视频；23 项检查通过，未新增模型请求 |
| 原生取消 | 实际观察到专属容器启动后取消 | interrupted；后继叶未派发；容器消失；3 次文件摘要检查在 2 秒窗口内稳定 |

组合 ID：`cap_2cdad2c72ff1e6ae9aad0dfa`。本地实验发布摘要：`1b63e988010e35599b6560b849844219310304090c62d3923a52581ebd7f1ca9`。

以上证明这个窄场景的机制闭环和后继调用可工作。六份视频不是六个独立研究样本。两叶输出被聚合为组合结果，未验证跨叶媒体再加工、C 再构造 D、连续多代改善或失败基线上的能力解锁。未做普通脚本/缓存/无组合的成本对照，**没有效率提升结论**。

## 任务、质量与成本

任务要求构造可复用双视频交付：输入 `edit` 和 `inset` 分别描述当前剪辑与画中画，输出按顺序包含两份视频执行结果。模型获得全部四项原生能力目录、固定引用和协议，自己选择步骤及数据绑定。宿主提供输入输出契约，不提供 steps/output 解法。验证与后继参数分别冻结，素材时段及选择发生改变；首轮检验不是独立任务族统计实验。

`verify_capability_outputs.py` 不导入候选代码。它从实际产物重新 ffprobe、完整解码，核对尺寸、fps、帧数及视频摘要，并与原始媒体的指定来源帧比较，包括画中画区域；阈值为像素 MAE ≤16。检查器源码及具体任务标准进入发布摘要。图中文字、审美、剪辑质量及人评未覆盖；后继技术通过不等于一般视频质量合格。

实际请求 3212：`deepseek-flash`，出站 `thinking.type=disabled`（off），`max_tokens=393216`。累计费用/请求无额外上限，沿原 Remotion 账本从 3211 累加至 3212，未清零。新增模型代理估费 **USD 0.00552810**；累计预约记账 **USD 2.648152476**。供应商账单、机器渲染、开发与人工成本未知，不记为零。历史三笔未知费用继续保留。

实际请求HTTP200：冷输入13659 token、缓存命中0、输出1192、总14851；上游4.605秒，提案阶段6.824秒。Runtime根调用耗时：验证105.329秒、后继109.809秒、最终代码复验110.336秒，均包含其子调用，不再叠加子耗时；这些数值不含独立媒体检查和人工复核，完整端到端耗时未单独采集。

排除新增请求后的原账本字节 SHA-256 仍为 `f507b1118f048d2542bcd43b514a07bc9677c454fe0188cbf61945cf722dbe13`，与上轮收尾一致。模型原始请求、用量和事件保留在私有目录；本轮未调用有已知预算口径问题的效率测量器生成报告。

执行价值只记录后继实际调用及资源用量，尚未测对照收益；创造价值只记录模型构造请求、所用原语固定引用、候选和后继消费关系，尚未估计创造收益或自动制定归档策略。

## 工程入口与保护范围

- `source_capability_runtime.ts`：从原生检查通过的 Source 库导出精确输出契约，固定库字节、镜像 ID、任务输入和调用权限，复用 `createCapabilityRuntime` 与共同 RSI admission。
- `capability_worker.py`：每叶独立工作目录、容器名称和 nonce，调用既有 `render_program`；返回与父子调用、程序/证书、源码及视频一致的完成回执。源码实例化不冒充执行。
- `run_capability_loop.py`：复用原 Harness 生成提案、编译，先登记 attempt，保留失败与显式修复谱系。没有另造 Agent 循环；模型无工具或写 Store/验证器的能力。
- `capability_store.ts`：可信宿主回调实际验证，候选只通过精确 validation grant 执行，正常路径拒绝未认证候选。`capability_publication_v1` 明确为本地实验协议，不冒用旧 reuse_form 发布。
- `complete-source-capability-loop.mjs`：实际验证、独立检查、保存、重新加载并执行不同后继任务；任一步失败均保留失败结果，不自动改认证。

manifest、registry、Store 与独立检查器必须由可信宿主控制，不能放进模型可写或候选容器挂载的目录。哈希不是对抗同用户文件系统写权限的认证手段。Store 中断可能留下发布锁，需要确认无活动发布后处理，不自动抢锁。

取消验收覆盖正常 AbortSignal 路径和一个有界稳定窗口；不代表任意 SIGKILL/宿主崩溃或外部副作用都可回滚。父进程退出 watchdog 已实现，但此次没有额外做断电/硬杀实验。

## 复现与有效配置

先在服务器既有项目加载私有 `.local/remote-env.sh`，使用项目 Python/Node 和已经配置的凭证。保持既有累计账本。所有输入、模型原始答复、执行数据与产物放受保护 `.local/`；不要用公开仓库路径保存原始记录。

```sh
node --experimental-strip-types scripts/run-source-capability.mjs \
  --catalog --library "$LIBRARY" --owner "$OWNER" > "$PRIVATE/catalog.json"

node scripts/project.mjs python scenarios/remotion_edit/structured/run_capability_loop.py \
  --task "$TASK" --catalog "$CATALOG" --snapshot "$SNAPSHOT" \
  --output "$NEW_ATTEMPT" --ledger-root "$EXISTING_LEDGER_ROOT" --call-model

node --experimental-strip-types scripts/complete-source-capability-loop.mjs "$PRIVATE_PLAN"
```

首个命令生成目录及 construction snapshot；第二个不带 `--call-model` 仅预览。`NEW_ATTEMPT` 须为当前代码根目录 `.local/` 下的新目录。独立计划指定 owner、candidate、store、expected_latest，以及验证/后继的 manifest、args、specification 和新 output 目录。两个 manifest 的 task ID 和 workspace 必须不同。CLI 不能作为不可信网络请求直接开放。

本轮代码从本地 `2302f1f` 加未提交补丁同步到服务器私有隔离目录；最终提交见 Git。有效环境 Linux / Node22.23.3 / Python3.10.21 / DSH0.1.5-rc.3；原生镜像固定 `sha256:e06ec743f87104c7956683fdbb4cf2f0fbd3f067e9357027656589dbdf13b658`。实际配置、代码摘要、题面/库/输入/检查标准摘要、所有 trace 和账本核验见私有 `.local/efficiency-rsi-loop-20261102/`；首轮与最终代码复验分别保存，未覆盖首轮证据。

## 失败、兼容与下一步

第一次 CLI 启动因输出不在候选代码根目录 `.local/` 下而拒绝，尚未调用模型；改用正确私有目录后成功，原失败日志保留。全量回归首次发现17项 Paper/PPT 代码锁失败：共享 Remotion 启动器新增容器归属字段触发了正确的旧锁拒绝。

已用既有兼容重导出流程生成 **Paper v41 / PPT v38** 并更新开发配置。旧 v40/v37 全部18文件摘要不变；新旧 IR、manifest、task、schema、source evidence 字节相同。唯一原代码锁变化为共享启动器，额外锁定审阅脚本；没有认证新 Capability 内核或重新训练。兼容专项95 Python/4 Node通过，最终统一与全量结果见[当前交接](../handoffs/efficiency-rsi.md)。未切换正式服务、账号或累计账本。

下一步将这条已验证的实验入口接入一个实际用户任务入口，保留显式权限和逐能力迁移；补通用错误恢复与输入证据更新。多代构造、第二后端、双价值选择策略和丰富成本实验后补。已有F1/F2/F4/F5测量器问题、F8深谱系限制仍未宣称关闭。
