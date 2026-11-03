# Capability Frontier 研究入口

本目录验证已有材料是否帮助模型构造新增跨文件/版本关系。它是离线研究适配器：复用公共控制器、Script 编译/沙箱、TS Capability Runtime、Store 与独立计量器，不接管聊天或正式服务。

2026-11-03 上午续：真实检查点的信息消融已首次观察到模型自主使用完整 C 构造 D；四对条件费用与质量独立保留，不称新盲测或完整效率反馈已闭合。新增显式构造意图与受限调用语法，从初始池的新项目对照另行报告，见[上午记录](../../../docs/experiments/recursive-construction-20261103.md)。下段79请求为此前夜间条件。

当前观察：C 可在新 Mamba 留出复用；最后条件的 D 自主构造未选 C/J，完整 Python 也能得到合格 D。第一条件有 J 复用，但仍未调用完整 C。宿主强制 C→D 组合诊断通过，但不计自主研究成功或效率收益。三种冻结条件分别保留，79 次真实请求估费 USD0.340150572。

当前目标、冻结条件与原始失败见 [推进协议](../../../docs/capability-frontier-protocol-v1.md)、[实验记录](../../../docs/experiments/capability-frontier-20261103.md)。输入及运行结果只放忽略的 `.local/`；私有论文、原始轨迹和凭证不得提交。

## 入口与顺序

在已配置服务器的项目检出中加载 `source .local/remote-env.sh`，使用 `node scripts/project.mjs python` 调用模块，避免依赖系统 Python 版本。

1. `prepare_inputs` 生成真实项目只读副本及受控版本；`freeze` 在模型请求前固定任务、评价器和预算。原文件不修改。新实验必须给出 `--experiment-id` 与带时区的未来 `--deadline-utc`，不继承本轮日期；每次使用新目录。
2. `source_phase --request <配置>` 生成并原生认证底层程序。`prepare_C` 固定实际解析输出与独立输入，`run --request <配置>` 使用公共控制器构造 C。
3. `prepare_D --base <私有实验根> --output <新目录> --c-plan <C-plan> --c-run <C-run> --code-commit <SHA>` 冻结研究。`--v2 --final-manifest <新留出清单>` 创建三组各两格；`--task-file`、`--study-name` 新建条件，不覆盖旧配置。第三条件还传入全部 `--prior-journal`，核验六美元研究估费上界。
4. 按 `ordered-requests.json` 顺序执行 `run --request <cell/request.json>`，每格一次完整获取回合。**全部构造结束之后**才执行 `finalize_D --directory <study> --base <实验根>`；最终结果不得送回本轮模型修复。全部报告与请求归属封账后，已发布根的独立失败接回原 `CapabilityFeedback` 撤回机制，供未来 Builder 过滤；原发布证据不删除，环境错误记为未知、不推测叶节点责任。`final-feedback.json` 保存本次回写，已撤回根不能仅凭一个成功事实恢复。
5. `replay_program --request <重放配置>` 可用保存的原程序零模型定位认证、包装及质量失败。它不冒充新自主构造；所有输出使用新目录。

`run` 请求包含 `plan`/`protocol` 文件引用、`cell`、`budget_usd`、`journal`、Unix `deadline`，可附正式 `study` 的计划引用、独立 journal 和 episode ID。底层计划遵循 `schemas/capability-improvement-v1.schema.json`。每个引用均为 `{path,sha256}`，使用前校验原字节。

设置本次服务器上的 `FRONTIER_INPUTS`、`FRONTIER_FREEZE`、`FRONTIER_EXPERIMENT_ID`、`FRONTIER_DEADLINE_UTC` 后，冻结命令为：

```sh
node scripts/project.mjs python -m scenarios.paper_proofreading.frontier.freeze \
  --inputs "$FRONTIER_INPUTS" --output "$FRONTIER_FREEZE" \
  --experiment-id "$FRONTIER_EXPERIMENT_ID" --deadline-utc "$FRONTIER_DEADLINE_UTC"
```

`prepare_C`、`prepare_D` 都支持 `--protocol "$FRONTIER_FREEZE/protocol.json"`，直接读取其任务引用和截止时间；缺省优先读取历史 `frozen-v1/protocol-server.json`，否则使用标准 `protocol.json`，不需要手工改名。新 C 的 Capability owner 默认为实验 ID；复用旧 Store 时通过 freezer 的 `--owner` 或 prepare_C 的 `--owner` 指定旧命名空间，不改变模型账号或原账本。D 仍沿用已有 C 的 owner。原冻结配置保持原样，过期后不能改旧截止时间继续跑，必须新建条件。

`run` 在费用与 owner 登记前核对请求截止时间和冻结协议；正式 study 还核对精确预算、任务、种子与实际初始能力池。初次构造前再核对一次可见池，之后本回合新学到的材料按原协议登记与计费。改请求文件不能绕过原 study 的预算或隐藏 C 的条件。`freeze`/`prepare_*` 不调用模型；`run`/`source_phase` 会按研究预算调用真实 API。

## 模型需要决定什么

- 组合：选择可见能力、当前输入与前序结果的关系，以及输出。宿主编码固定 owner、版本引用、契约和节点结构。
- 程序：提供算法 source；mode 有固定默认值，结构化关系程序应选 `json`，读取当前文件的完整算法选 `paths`。description 可由宿主补缺省值。
- 定义 `run(value)` 时，默认采用 `function_v1`。宿主保留函数、导入和常量，忽略脚本主控/输出入口，注入真实输入并序列化返回对象。`json` 接收结构化值；`paths` 接收按文件 stem 命名的当前授权路径字典。显式 `script_v1` 保留原脚本接口。
- 完整文件程序经认证后，只有输入角色精确对应固定任务字段、输出类型静态兼容时，宿主才机械生成一步候选；部分材料仍由模型决定如何组合。该编码不提供最终算法、不授予认证或绕过独立验证。

原始回答、元数据补全、忽略的入口位置和实际执行源码分别保存。`source_equivalent` 证明的是实际生成执行模块与参数化模块在两份输入上的源等价性；不是任意输入的语义证明。

材料学习后，公共控制器另外保留 `material_continuation`：上一缺口、程序用途/源码摘要、获取证据与新增根，并在新池中重建别名；不能用旧 snapshot 的 repair 或旧别名继续执行。它帮助后继构造知道“刚补齐了什么”，不强制选择 C，不含最终留出反馈。此前只有零模型检查，上午的四对真实检查点消融已观察到行为与费用差异；范围和反例见[上午记录](../../../docs/experiments/recursive-construction-20261103.md)。

上午新增同答接口：`{program,composition:{steps,output}}` 中模型自行组织全部调用与数据流，新材料只用 `use:"$program"` 占位；已有 alias 在学习前解析为精确版本。也可用 `composition_source` 写静态 `def build(value)`，以 `capability.cN(...)` 调用已有能力、`program(...)` 调用新材料，再返回字段/对象/数组。该语法只编译为现有 IR，不执行编排 Python；新增计算放在原 program.source 中认证。只有明确给出组合意图，宿主才机械解析新程序引用；未给意图仍保留原完整程序包装。失败repair保留精确选择并按当前目录显示，不能复用旧alias。

新多项目条件可重复传入 `--final-manifest <manifest>`，清单含唯一 `id` 与三条 `{version,file,sha256}`；旧无id清单仍为mamba。`--budget-usd <有限金额>` 覆盖本次各格研究预算，`--research-limit-usd <有限金额>` 冻结含既往用量的研究估费上界，缺省保留旧值，不改变平台额度或旧结果。

## 费用与结论

平台费用/请求额度仍为 null，沿用原账本。研究回合有限预算在 booking 前按最坏预留判断；所有内部失败、学习、修复和恢复归属同一个事先注册的 episode。C 获取成本单列，不能只用条件 D 成本差宣称系统回本。

最终验收保留全部预登记格，包括无候选、未知费用和执行失败。Direct、Flat 与 Hierarchical 的差异是初始能力词汇；均可编写普通 Python。J 和完整 C 的精确依赖、实际调用分别报告。无模型诊断、源码认证、独立质量与研究效果不得混用。

## 免费验证与范围

`npm test` 检查一般回归；Linux 加 `RUN_SCRIPT_CAPABILITY_SANDBOX=1` 可运行 `tests/test_frontier_function.py` 与相关 Script 原生检查。模型行为验收仍必须使用真实 DeepSeek。

本轮独立评价器只处理可达字面 LaTeX 引用、活动书目与版本关系，不做宏展开、TeX 编译或文献事实审查。多个版本对不是多个独立项目。原生执行仅在当前 Linux 沙箱验收，Windows 不支持该执行路径；旧库、旧证书及正式 Runtime 保留。中断不会自动重发未知请求或退款，需核对私有 journal 与原累计账本。
