# GeneLoop 的 ppt-master 场景

2026-11-11 新候选增加`build_ppt`与`patch_ppt`，只吸收dsh-ppt锁定执行模块，共享原权限、预览和交付，不安装上游完整插件/Skill。SVG及已有PPTX路线保留；JSON源稿不回收Office手工修改。纯JS依赖由根目录`npm ci`安装，开发隔离环境也可在`third_party/dsh-ppt`运行`npm ci --ignore-scripts`。桌面可选打包入口`apps/desktop/scripts/stage-ppt-deck.mjs`，宿主提供目录授权、主题、字体、Office及发布函数；本模块不增加常驻服务或模型调用。完整状态及未验证项见[本轮记录](../../docs/experiments/ppt-native-deck-engine-20261111.md)。

2026-11-10当前本地候选PPT152/Paper154提供`edit_ppt_native`处理原生文本、字号、对齐小修改，`prepare_ppt_asset`准备本地图片；复杂重排沿原流程。当前完整PPTX/PDF/逐页PNG按版本交付，成功发布结束本轮，未执行的工具文本不能当改页完成。RSI学习和内部可选Judge各自后台运行，不阻塞前台；备注默认可选。零模型原轨迹及Office回放、完整回归和平台边界见[当前记录](../../docs/experiments/ppt-stable-delivery-audit-20261110.md)，以下为历史说明。未改前端或正式部署，未PR。

2026-11-09当前隔离PPT145支持先功能试用后验证：原稿保真与设计差异可保留作诊断，已独立观察的写页/改页结构可以进入probation。两个真实轨迹学得的连续程序已在一份独立留出任务执行并交付，不按任意Skill文字生成流程；本例请求与估费下降，范围和分账见[结果](../../docs/experiments/ppt-practical-learning-20261109.md)。以下旧版本段落保留作历史。

当前隔离适配PPT142/Paper144另维护`skill-sources.json`及`skill_sources/`：外部MIT来源先审阅，再自主重写为短设计/编辑参考，与现有工具共用；不安装第二套Agent。`read_ppt_design(guide=true)`按需返回参考，Python发现使用同一登记。参考本身不可执行，学习、认证和后继采用各自记录。两份参考已在真实业务模拟任务被读取；三卡片程序经实际认证反馈纠正、正常学习器登记为认证试用，原失败保留，尚未证明独立后继采用或降费，见[本轮报告](../../docs/experiments/ppt-external-skill-learning-20261108.md)。以下保留早期集成说明；当前接口和状态以该报告及场景交接为准。

网页版 PPT 使用与桌面共用的内置制作资源。来源为 [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master)，MIT，Copyright (c) 2025–2026 Hugo He。许可证、第三方声明和来源信息随包保存。

Web 场景准备时自动验证并展开仓库随附的制作包。MCP 和 Bash 以 `/opt/geneloop/ppt-master` 作为既有只读路径。Python 依赖在隔离运行环境安装，账号网关的 `rendererRoot`、`fontRoot` 继续提供给命令沙箱。源附件只读，输出按会话隔离。部署时用 `scripts/prepare-release-scenes.py` 重建快照。旧独立安装器和整包锁已从源码移除。

两种模式使用同一模型、提示、技能、普通环境准备和工具集合。模型读取入口，官方 attribution guard 成功后读取 routing，再自行按选定路由规划、编写 SVG、核对来源、检查、修复和导出。用户明确委托自主设计时使用上游 explicit delegation 分支；否则保留确认门禁。既有公共 Bash、搜索、网页读取和后台任务继续可用。

`read_skill_entry` 合并读取官方入口、运行归属检查和读取路由，并列出当前上传件，这是普通脚本优化。最初的固定技能句柄候选因“常量不能证明参数流”被编译器拒绝，没有发布。

当前 v2 从真实完整制作轨迹学习两条来源准备续接：`pin_source → convert_source`、`convert_source → read_converted_source`。模型选择并绑定上传 PDF 后，官方转换器在会话私有派生目录生成 Markdown/素材；读取前重新核验上传许可、原件 SHA 和全部派生文件，返回完整文本。转换包装同样提供给 Baseline，不生成任何幻灯片。原 `read_source_page` 仍可由模型显式调用。

候选图、参数边和独立认证来自现有 witnessed-edge 编译器，不手写制作 DAG，不训练模型权重。当前在线准入只接受两个节点的闭合边；完整挖掘结果保留，三节点候选不因离线可挖掘就扩大在线权限。Bash、模板选择、科研判断、页面生成与修复不自动续接。输入变化、权限撤销、跨会话句柄和派生文件变化均拒绝。旧 v1 首页读取库保留。

来源转换的最小依赖见本目录 `requirements.txt`，用同一隔离 Python 安装；完整技能路线的其他依赖仍按上游要求配置。服务商返回 `max-tokens` 时，通过 Harness 原生 steering 继续同一任务，保留任务、费用与取消语义；不改输出容量，不把截断答复当成交付。该恢复为双方共有能力，不能计作 Motif 跳过。

额外 HTTP 预览服务在该命令沙箱中不可持续，按上游允许的运行环境分支关闭；保留全部真实文件渲染、检查和下载预览。会话独立的 `/tmp` 在命令间保留转换器和检查器的中间文件，不能读取其他会话或宿主临时目录。两侧共用这些普通环境优化，不把它们计为 Motif 学习收益。

```sh
python scripts/learn-ppt-master-motif.py --dataset .local/experiment/dataset.json --out .local/experiment/compiled --publish motif-libraries/ppt-master-v3
```

数据集恰好两个独立训练决定、一个独立认证决定，使用真实 GeneLoop Baseline 的原始事件、实际完整工具 schema、任务身份和逐请求费用账本。最终评测不参与编译。公开库只保存匿名证据摘要与版本锁；原始来源、轨迹、凭证和成品留在私有 `.local/`。

仅在实际拦截请求且返回值与版本核验成功后，才记 `verified_skips`。它不等同于最终成品合格或总费用下降；两侧完整用量、缓存命中/未命中、输出、重试、时间与质量需要独立比较。旧库 `ppt-web-v2-r13` 不在新工具表上执行。
