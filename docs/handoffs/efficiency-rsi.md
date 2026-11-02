# 效率驱动 RSI 当前交接

- 更新时间与交接人：2026-11-02，Codex及 capability_contract / evaluation_protocol / runtime_migration 子智能体。
- 目标与本次范围：落地优先。本轮完成Source视频场景的真实Compose提案→新Runtime执行→独立验收→不可变发布→不同任务/参数后继消费；丰富对照、第二后端和多代研究后补。
- 分支 / commit / 工作区：原SSS目录 `codex/efficiency-rsi-20261102`，本轮从本地 `2302f1f` 继续。当前结果随本轮本地提交保存，未推送、未开PR、未部署。私人 `reference/` 保留且不跟踪，旧工作备份仍在 `.local/workspace-preservation-20261102/`。
- 已完成：`source_capability_runtime.ts`及CLI/worker用原生Source渲染器实际执行；精确输出契约、任务库/输入/镜像固定、父子回执、独立叶工作区及nonce容器清理。`capability_runtime.ts`新增可信精确validation grant，候选验证时仍为candidate，正常路径不能执行未认证候选。
- 已完成：`run_capability_loop.py`复用原Harness生成/编译真实提案，登记全部attempt与请求、保留失败及显式修复关系。`capability_store.ts`在发布函数内部实际执行并独立验证，绑定输入/trace/产物/检查器；owner私有库、不可变版本、CAS指针，失败不晋级。`complete-source-capability-loop.mjs`强制不同任务/工作区重新加载并消费已发布版本。
- 真实验收：实验 `efficiency-rsi-source-loop-20261102`；模型自主选择两项旧程序生成组合 `cap_2cdad2c72ff1e6ae9aad0dfa`。验证任务与后继任务各实际渲染2视频，各23项独立媒体检查通过；发布摘要 `1b63e988010e35599b6560b849844219310304090c62d3923a52581ebd7f1ca9`。收尾代码再次消费产生2视频、23项通过。实际容器启动后取消，interrupted/无后继派发/容器消失/2秒目录摘要稳定6项检查通过。
- 质量与研究边界：检查尺寸/fps/帧数/完整解码/指定原始来源像素，未做人评、文字审美或全视频语义验收。不是六个独立研究样本；没有无组合成本对照、C构造D或多代持续RSI证据。执行/创造价值保存原始调用、构造引用和后继关系，尚无价值估计或自动再投资策略。
- 权限与费用：用户持续授权真实测试；原DeepSeek Flash、off、实际max_tokens393216，费用/请求无额外上限。仅新增请求3212，代理估费USD0.00552810；累计请求3211→3212，预约记账USD2.648152476。旧账本前缀SHA仍为f507b1118f048d2542bcd43b514a07bc9677c454fe0188cbf61945cf722dbe13。账单、机器、人工作业费用未知，历史未知费用不改写。无外部应用写入、私人原件修改或生产切换。
- 配置与数据：服务器既有私有项目加载remote-env后在 `.local/efficiency-rsi-loop-20261102/code/` 验证，未覆盖其工作区。Linux Node22.23.3/Python3.10.21/DSH0.1.5-rc.3；固定镜像、任务/库/输入/validator摘要及复现命令见[实验记录](../experiments/efficiency-rsi-source-loop-20261102.md)。同名本地私有目录保存代码清单、全量日志和 `delivery/` 视频/验证/trace；原始模型请求仍仅私有保存。
- 旧能力保护：共享Remotion server可选容器归属分支首次触发17项旧产品code-lock拒绝。现用审阅式兼容重导出生成Paper v41/PPT v38、更新开发配置；旧v40/v37全部18文件不变，新旧IR/manifest/task/schema/source evidence逐字节一致。95 Python/4 Node兼容专项通过；不代表新Capability内核已获生产认证。正式服务未切换。
- 已验证：最终本地与Linux统一 `npm run rsi:efficiency:check` 均113 Python/85 Node通过，Linux smoke18题通过；两端37份本批源码/测试/兼容产物SHA一致。最终全量 `TMPDIR=/private/tmp npm test`：Python1714通过/236跳过；Node1480通过/17跳过/1失败（原有大上传typed413的ECONNRESET，前轮当前与未改基线同样复现）。不称全量全绿。Linux本轮只跑统一定向及smoke，不声称Linux全量通过。
- 失败保留：首次提案CLI因输出不在候选根.local下而拒绝，零模型请求，修路径后成功；17项旧锁失败及兼容修复日志保留。首轮、最终代码复验、取消任务分别保存，不覆盖为同一次运行。
- 未完成与阻塞：新入口尚未接生产账户/聊天路由；Artifact、Specialize、输入更新的自动重新验证、任意进程/宿主崩溃恢复、多代构造和完整价值策略未完成。F1/F2/F4/F5评价器口径及F8深谱系限制仍保留，未拿该测量器报告收益。旧Linux18项历史全量失败并未在本轮全部排除，不能声称Linux全量通过。
- 接手下一步：1. 将单个已授权用户任务接到现有聊天/Harness入口，给出能力预览/失效回退与可审阅产物；验收仍用真实调用。2. 对当前Source闭环补输入证据更新、失败后的明确恢复与Store锁交接；模型仍不能改验证器或账本。3. 先形成实际任务收益观察，再补C构造D、第二后端和丰富研究实验，避免用测试数代替进展。
- 回退与风险：撤回本轮代码及开发config指针即可退出新实验路径；若撤回共享server须同步退回Paper v40/PPT v37代码锁，不能新旧混配。保留全部旧库、Store版本、累计账本和原始证据。真实生产发布仍走统一service入口，当前没有执行发布。
