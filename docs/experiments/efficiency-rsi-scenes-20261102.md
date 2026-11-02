# Capability 跨场景机制与真实执行回放

- 实验ID：`efficiency-rsi-scenes-20261102`；2026-11-02，Codex。
- 目标：移除机会发现/提案/反馈/发布流程对Source目录的依赖，用第二种输出类型验证同一机制，保护已有真实视频执行能力。用户希望通用机制，不要求小数据量证明普遍效果。
- 代码：基于7463596继续；最终本地提交见Git。未推送、未开PR、未部署。私有`.local/efficiency-rsi-scenes-20261102/`保留原始日志、公开代码归档、运行摘要和两端文件摘要。

## 改动与瓶颈

公共Python模块负责发现、Harness提案、反馈和控制；可信场景适配器只负责记录解释、验证配置冻结与发布桥接。公共TS生命周期负责真实执行、严格Store发布、重新加载与不同输入后继检查。Source旧入口保持兼容；`rsi:improve`允许宿主固定代码摘要的适配器，模型不能选择它。

同时修复上一轮QA新增evidence_binding与Store严格顶层字段校验不兼容的问题：场景保留绑定文件，公共发布边界明确分离传输字段和质量verdict，未知字段仍拒绝。模型明确报告缺原语/契约不兼容/证据不足时保存缺口及成本并停止修复；同一证据/能力池暂缓，新认证目录出现后可重新尝试。场景自行声明可修复的质量失败，公共核心不再枚举Source错误码。

仍未实现自动把缺口交给既有学习器，也没有任意MCP工具到Capability叶后端的映射。当前叶类别仍为Source Program/Artifact Motif。接口可扩展不等于每个场景无需适配或必然有收益。

## 两条验证路径

**非视频场景为工程诊断。** `examples/capability-scenes/counts`使用真实固定Python程序处理JSON分组计数，另一个程序独立复算；两条普通执行记录经共同发现器生成机会，诊断提案编译后通过共同Store发布/后继执行并进入反馈。场景权限、认证种子和提案是合成夹具，不代表自然用户任务、真实Artifact认证、模型抽象能力或降本效果。禁止把diagnosticHost接生产会话。

**视频为历史候选的新执行。** 在Linux独立代码/工作区/Store内，重放首轮真实模型生成的候选，原始历史日志和Store保持。实际执行验证与不同输入后继复用，各2次原生叶执行、各23项机械检查通过，QA均含evidence_binding；通过新的公共生命周期发布并重新加载。publication摘要为`47e5ec80ff53b3cf5801a8a67dde753701bb93833ea2c10a8da272acdfbaefb4`。本地summary为`.local/efficiency-rsi-scenes-20261102/source-replay-summary.json`，服务器在同实验目录的`code/.local/source-cycle-replay/`保存全部回执、视频、检查和新Store。新增模型调用0，不重写累计账本。不是新模型提案或真实C→D证据。

代码分为实际重放时的`code`和最终错误分类调整后的`code-final`；原运行目录不覆盖。运行时、公共发布生命周期、Source发布脚本和机械检查器在两版本保持一致；最后适配错误分类改动由定向回归覆盖，具体差异见私有`code-verification.json`。

## 检查、配置与负面结果

- `npm run rsi:efficiency:check`：本地179 Python、91 Node通过；Linux最终同一套检查通过。涵盖旧提案回归、跨场景真实子进程链路、QA传输/发布边界、后继失败保留已提交状态、独立输入/任务约束、适配代码变化拒绝、负面观测保留、缺材料暂缓及目录变化重启、场景失败修复分类。
- Linux `npm run smoke`：18项portfolio及SDK初始化通过，模型请求0。
- 最终本地全量：1780 Python通过/236跳过，Node1486通过/1失败/17跳过。使用解析到真实路径的TMPDIR。唯一失败继续为`tests/test_model_transport_gateway.mjs`上传typed413的`write ECONNRESET`；本轮未修改这条路径，保留失败，不称全量通过。
- 统一入口`npm run rsi:improve -- --help`可运行。核心源码通过两端SHA256核对；版本与完整日志见私有code-verification/targeted-final/full-test-final记录。
- 原模型调用、原视频数据及原账本均不改写；新测试库不影响正式库。所有本轮模型/API费用为0；CPU/渲染/人工成本未测，不能报告总成本下降。
- 质量范围仅机械视频检查、独立计数结果与工程守卫；人工审美/科研质量未评审。真实模型对新defer协议及通用适配的行为仍待验证。

## 下一步

1. 接“具体构造缺口→已有学习器→原生认证→能力目录→原机会再试”；复用现有Source/Artifact/Motif学习，不重写Agent循环。
2. 扩真实任务完成记录入口及原生工具适配，仍先走隔离机制，不直接接管聊天。
3. 匹配任务质量/来源/契约范围后，再积累执行成本、构造贡献和失败成本；持续收益、真实C→D与普遍有效性保持pending。

接入协议与最短命令见[跨场景接口](../capability-scenes-v1.md)。
