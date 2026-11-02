# Capability Frontier 研究入口

本目录验证已有材料是否帮助模型构造新增跨文件/版本关系。它是离线研究适配器：复用公共控制器、Script 编译/沙箱、TS Capability Runtime、Store 与独立计量器，不接管聊天或正式服务。

当前观察：C 可在新 Mamba 留出复用；最后条件的 D 自主构造未选 C/J，完整 Python 也能得到合格 D。第一条件有 J 复用，但仍未调用完整 C。宿主强制 C→D 组合诊断通过，但不计自主研究成功或效率收益。三种冻结条件分别保留，79 次真实请求估费 USD0.340150572。

当前目标、冻结条件与原始失败见 [推进协议](../../../docs/capability-frontier-protocol-v1.md)、[实验记录](../../../docs/experiments/capability-frontier-20261103.md)。输入及运行结果只放忽略的 `.local/`；私有论文、原始轨迹和凭证不得提交。

## 入口与顺序

在已配置服务器的项目检出中加载 `source .local/remote-env.sh`，使用 `node scripts/project.mjs python` 调用模块，避免依赖系统 Python 版本。

1. `prepare_inputs` 生成真实项目只读副本及受控版本；`freeze` 在模型请求前固定任务、评价器和预算。原文件不修改。
2. `source_phase --request <配置>` 生成并原生认证底层程序。`prepare_C` 固定实际解析输出与独立输入，`run --request <配置>` 使用公共控制器构造 C。
3. `prepare_D --base <私有实验根> --output <新目录> --c-plan <C-plan> --c-run <C-run> --code-commit <SHA>` 冻结研究。`--v2 --final-manifest <新留出清单>` 创建三组各两格；`--task-file`、`--study-name` 新建条件，不覆盖旧配置。第三条件还传入全部 `--prior-journal`，核验六美元研究估费上界。
4. 按 `ordered-requests.json` 顺序执行 `run --request <cell/request.json>`，每格一次完整获取回合。**全部构造结束之后**才执行 `finalize_D --directory <study> --base <实验根>`；最终结果不得送回本轮模型修复。全部报告与请求归属封账后，已发布根的独立失败接回原 `CapabilityFeedback` 撤回机制，供未来 Builder 过滤；原发布证据不删除，环境错误记为未知、不推测叶节点责任。`final-feedback.json` 保存本次回写，已撤回根不能仅凭一个成功事实恢复。
5. `replay_program --request <重放配置>` 可用保存的原程序零模型定位认证、包装及质量失败。它不冒充新自主构造；所有输出使用新目录。

`run` 请求包含 `plan`/`protocol` 文件引用、`cell`、`budget_usd`、`journal`、Unix `deadline`，可附正式 `study` 的计划引用、独立 journal 和 episode ID。底层计划遵循 `schemas/capability-improvement-v1.schema.json`。每个引用均为 `{path,sha256}`，使用前校验原字节。

## 模型需要决定什么

- 组合：选择可见能力、当前输入与前序结果的关系，以及输出。宿主编码固定 owner、版本引用、契约和节点结构。
- 程序：提供算法 source；mode 有固定默认值，结构化关系程序应选 `json`，读取当前文件的完整算法选 `paths`。description 可由宿主补缺省值。
- 定义 `run(value)` 时，默认采用 `function_v1`。宿主保留函数、导入和常量，忽略脚本主控/输出入口，注入真实输入并序列化返回对象。`json` 接收结构化值；`paths` 接收按文件 stem 命名的当前授权路径字典。显式 `script_v1` 保留原脚本接口。
- 完整文件程序经认证后，只有输入角色精确对应固定任务字段、输出类型静态兼容时，宿主才机械生成一步候选；部分材料仍由模型决定如何组合。该编码不提供最终算法、不授予认证或绕过独立验证。

原始回答、元数据补全、忽略的入口位置和实际执行源码分别保存。`source_equivalent` 证明的是实际生成执行模块与参数化模块在两份输入上的源等价性；不是任意输入的语义证明。

## 费用与结论

平台费用/请求额度仍为 null，沿用原账本。研究回合有限预算在 booking 前按最坏预留判断；所有内部失败、学习、修复和恢复归属同一个事先注册的 episode。C 获取成本单列，不能只用条件 D 成本差宣称系统回本。

最终验收保留全部预登记格，包括无候选、未知费用和执行失败。Direct、Flat 与 Hierarchical 的差异是初始能力词汇；均可编写普通 Python。J 和完整 C 的精确依赖、实际调用分别报告。无模型诊断、源码认证、独立质量与研究效果不得混用。

## 免费验证与范围

`npm test` 检查一般回归；Linux 加 `RUN_SCRIPT_CAPABILITY_SANDBOX=1` 可运行 `tests/test_frontier_function.py` 与相关 Script 原生检查。模型行为验收仍必须使用真实 DeepSeek。

本轮独立评价器只处理可达字面 LaTeX 引用、活动书目与版本关系，不做宏展开、TeX 编译或文献事实审查。多个版本对不是多个独立项目。原生执行仅在当前 Linux 沙箱验收，Windows 不支持该执行路径；旧库、旧证书及正式 Runtime 保留。中断不会自动重发未知请求或退款，需核对私有 journal 与原累计账本。
