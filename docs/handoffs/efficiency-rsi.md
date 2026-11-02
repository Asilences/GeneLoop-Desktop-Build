# 效率驱动 RSI 当前交接

- 更新时间与交接人：2026-11-02，Codex 主集成及 capability_contract / evaluation_protocol / runtime_migration 三个子智能体。
- 目标与本次范围：第一批可审阅基础实现：固定版本能力、外部 Compose 提案编译、实际组合调用和完整尝试评价。效率同时覆盖省费与给定条件下的新能力可达性；完整依赖、责任与验收见[任务表](../efficiency-rsi-plan.md)。首个模型自主学习→构造→独立认证→后继使用的真实里程碑尚未达成。
- 分支 / commit / 工作区：仍在原 SSS 目录 `codex/efficiency-rsi-20261102`；基线 `09b81b2255d1b5aae33c6804acc9eb55b26d7276`。本轮期间外部历史更新把原 `69724cf` 改为该 SHA，前后 tree 均为 `3231d94e1a3ca3dd70a02793fea7e5b1ce812a29`。PR117/118 已合并。本记录随首批源码保存在当前分支本地提交，未推送、未创建PR；私人 reference 仍不跟踪。
- 已完成 T1：`capability_contract.py/.ts` 和 schema；固定 owner/契约/effects/实现/依赖身份与精确闭包快照。旧 Source/Artifact 库逐字节保留；Python 离线映射经固定 Node bridge 复用原生 TS 摘要，避免浮点/Unicode 分歧。生命周期、认证和迁移状态分别保存，状态声明不授执行权。
- 已完成 T2 基础：`efficiency_rsi_measurement.py`、schema、只读 CLI 与[评价协议](../efficiency-rsi-evaluation.md)。独立 registry 绑定所有 cells、attempts、overheads 和物理请求；四格结果、失败重试、未观测、删失、未知费用与共享分摊均保留。预算范围是 attempt_execution，共享构造/认证另计；人工、机器、账单实付及全生命周期再投资尚未接入。
- 已完成 T3 内核：`capability_runtime.ts` 固定依赖和组件版本，逐子调用复用已有 RSI admission；实际回执、父子关系、摘要和耗时完整，权限撤销、版本漂移、错误类型、取消和非法输入均留失败记录。Build-only/Archived 不直接选择，认证组合仍可调用其固定版本。没有改旧 Runtime、原生 Harness 或正式场景入口。
- 已完成 T5 离线部分：`capability_builder.py` 与 `scripts/build-capability.py` 编译外部提案；固定可见能力、检查显式数据流/类型/effects，输出仍为 candidate/build_only。已诊断 Python 编译输出→候选拒绝→可信诊断宿主独立认证→TS 三次实际 Python 子调用；没有模型自主生成、Specialize 或自动发布。
- 已验证：免费统一入口 `npm run rsi:efficiency:check` 最终 79 Python / 61 Node 通过。`rsi:check`、`smoke`、`motif:check` 通过。独立审查发现并修复旧摘要编码不一致及非法输入缺回执两项问题。全部为机制诊断，不能当真实任务质量/效率证据。
- 全量回归：本地补齐 requirements 已声明的 PyMuPDF/defusedxml/reportlab 后，Python 1679 通过/236跳过；Node 1444通过/17跳过/13失败。12项由 macOS /var 与 /private/var 临时目录别名触发，指定真实 TMPDIR 后对应测试39通过/1跳过；上传在途413测试单独复跑通过，保留全量并发 ECONNRESET 失败。Linux同一冻结源码 Python 1893通过/5跳过/18失败；报错涉及旧聊天/Harness连接、服务监视器容量、PDF/OCR工具。未改基线已复现聊天连接、服务监视器、PDF与OCR代表性失败；其余失败完整保留，不称Python全量通过。Linux Node首次1451通过/4跳过/3失败，旧测试误用系统Python3.6；指定项目Python的PATH与SSS_PURE_CODE_PYTHON后，全量1470通过/4跳过/0失败。Linux统一定向79 Python/61 Node及rsi:check/smoke/motif:check均通过。
- 配置与数据：本地日志/代码快照在 `.local/efficiency-rsi-20261102/`；Linux 在服务器项目私有 `.local/efficiency-rsi-20261102-validation/` 新目录验证，未覆盖该机器未提交工作。使用已配置私有环境，正式服务仍由 `GENELOOP_SERVICE_HOME/CONFIG` 定位；本轮未启停服务。`code-snapshot.json` 记录基线、tree和25份改动文件摘要（交接收尾仅补文档，测试源码未变）；Linux Node22.23.3 / Python3.10.21 / DSH0.1.5-rc.3，本地Node22.22.3 / Python3.12.14。原始日志不入Git。
- 未完成与环境问题：真实模型提案/新场景后端/独立认证发布尚未实现。Linux旧Harness/服务测试报监视器容量与连接问题，文档工具另有环境失败；真实pilot前先恢复隔离运行条件，不通过重启正式服务或清除用户任务规避。
- 接手下一步：1. T4把 Source MCP/bridge每次调用绑定任务固定library/object/certificate摘要，接真实完成回执与取消；旧参数兼容。2. 复用原 Harness 建立先登记attempt、独立arm/nonce目录、串行双路运行与完整账本导出的runner。3. T5/T6接真实模型提案、独立质量认证与显式版本化发布，冻结首轮任务和资源条件后在Linux做真实pilot；保留未组合/失败结果，不预写A/B→C→D解法。
- 权限与预算：用户已授权当前工作区开发、子智能体和真实测试；真实模型测试沿原平台授权及累计账本，启动前记录实际模型/reasoning/output和研究资源。当前新增 DeepSeek 实验请求0，无生产发布、外部应用写入或私人原件修改。宿主成本未知。
- 回退与旧工作：`.local/workspace-preservation-20261102/` 保存旧patch、稳定stash引用、55份副本/48份parked及RESTORE说明，4份reference原件留原位。原分支工作不往新main整段覆盖；外部历史更新后的旧commit定位以Git/备份映射复核。删除本批旁路模块及入口即可退出研究开发，不需要迁移或删除旧库。
