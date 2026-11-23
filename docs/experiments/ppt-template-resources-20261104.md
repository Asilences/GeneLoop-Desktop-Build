# 通用PPT模板资源与GeneLoop吸收方案

2026-11-04。用户要求将PPT Agent拓展到普通用户的自然语言需求，覆盖商务、教学、产品、活动和个人展示。外部Skill先审计内部限制，改造成GeneLoop适配版，再合入统一制作流程。PPT Master也纳入吸收范围，模板、设计资料、组件和导出器按模块管理。

本轮已核对公开许可，保存三个仓库的固定版本快照，提取128条主题索引并下载16份首批主题原文。资源位于原开发工作区`.local/evaluations/ppt-general-template-resources-20261104/`。运行时已接入中性默认主题、16套SlideSpeak设计规范、slide-maker的editorial/soft/journal和Presenton General，共21套主题参数，见`scenarios/ppt_master/themes.json`。来源、原文件摘要、许可与改造记录保存在场景`third_party/`目录。其余资源继续保留为候选。

## 已实施与验证边界

`read_ppt_design`按用途返回简短主题卡，指定主题后返回配色、字号和页型规范。`start_ppt`创建带版本标记的通用项目，保留用户模板与原PPTX路线。两份入口合并为一份GeneLoop精简协议，底层继续使用固定版本PPT Master模块。

21是当前主题参数条目数。128条索引、slide-maker的30套程序和Presenton模板尚未全部导入。此次精选适配配色、字号、图文几何和常用页面角色，未复刻所有上游母版、图片资产及复杂组件。`compose_ppt_page`已提供封面、章节、要点、双栏、图文、条形图和结尾七类原生可编辑SVG页型，采用实际字体测量与容量拒绝。

21主题共49页已完成真实Office导出，49页PDF/PPTX对应、PNG解码和同版本检查复用均通过，新增模型请求0。已查看五张全页总览和代表原图，未发现可见缺字、严重重叠或低对比。诊断内容简短且布局朴素，这些检查仅证明此批基本页型可用，不能推出真实长内容、任意公式和复杂母版均已验收。首轮输入PNG的CRC错误正确被拒绝，失败材料保留。导入模板属于工程资产建设，学得组件与采用条件由后续RSI真实任务分别验证。完整清单见[本轮验收](ppt-general-completion-20261104.md)。

## Codex Presentations的吸收边界

已审阅本机`presentations/26.1103.10131`的插件manifest、设计和模板继承说明。manifest标注MIT，但尚未核实相同版本的公开源码地址及完整依赖许可。其`@oai/artifact-tool`、Spaces与连接器分别依赖相应运行环境，许可和部署能力须逐项确认。

已将继承用户模板的母版与尺寸、优先原位修改、按内容选择布局、保持原生数据对象、依据实际渲染定位问题等方法，自行重写为`design-conventions.md`，由`read_ppt_design(guide=true)`按需提供，并记录所审阅材料的版本和摘要。当前未复制该Skill正文、专用运行库或平台资产。默认Spaces、强制插图后端与平台路由由GeneLoop现有运行协议取代。官方文档将Skill描述为指导MCP工具协作的工作流，底层服务的许可须分别核验。[官方Skill说明](https://developers.openai.com/plugins/concepts/skills)

## 通用资源优先级

| 优先级 | 材料与用途 | 许可及接入工作 | 来源 |
| --- | --- | --- | --- |
| 1 | SlideSpeak的128套设计规范，覆盖商务、路演、咨询、营销、产品、作品集、教育、活动、财务九类 | MIT。提取配色、字体角色、页面结构与适用条件，转换为本地主题契约。字体和示例文案单独适配 | [presentation-design-prompts](https://github.com/SlideSpeak/presentation-design-prompts) |
| 1 | slide-maker的30套样式及七种页面函数，包含封面、章节、图文、要点、引用、数据与结尾 | MIT。优先提取可编辑组件与设计参数，完成依赖审计和独立渲染认证后供统一Runtime调用 | [slides_maker](https://github.com/addsumtech/slides_maker) |
| 2 | Presenton的商务、通用、路演和创意模板，含Momentum、Executive、General等 | Apache-2.0。仓库内模板代码需做数据契约和导出适配，官方在线模板逐项核对资产范围 | [Presenton](https://github.com/presenton/presenton) |
| 2 | SlidesCarnival的商务、教学、营销、个人展示等成品模板 | 官方模板条款为CC BY 4.0。逐套保留署名与素材来源，通过PPTX母版复用接入 | [SlidesCarnival](https://www.slidescarnival.com/) |
| 3 | LibreOffice Impress模板集合，覆盖企业、简约和教学背景 | 仓库工具MIT，模板按子目录分别授权。通过OTP/ODP转换为PPTX后验证字体、母版和可编辑性 | [Impress Templates](https://github.com/dohliam/libreoffice-impress-templates) |

SlideSpeak固定版本为`aba875b3cd64e9505fc995aabe7a52985f1a1a7e`，slide-maker为`f7316d1c399235823e78b01b6d547897f6dcdbc4`，Presenton为`bf5179fc712c4e5d225511f46960478f80879da7`。前两者的目录、许可和相关源文件已保存SHA。Presenton的`templates/README.md`不存在，已保留404记录，其模板文件仍待逐项审查。

## 用户场景与首批材料

| 场景 | 主题原文或候选样式 | 内容组织重点 |
| --- | --- | --- |
| 工作汇报、周报、季度复盘 | Atlas、QBR、Boardroom | 目标、进展、问题、下一步、数据 |
| 商业计划、路演 | Runway、Demo Day | 问题、方案、用户、商业模式、计划 |
| 产品介绍、技术分享 | Bento、Wireframe | 场景、功能、演示、架构、收益 |
| 品牌、市场推广 | Brand Guidelines | 定位、受众、卖点、活动与渠道 |
| 教学、培训、科普 | Lesson Plan、Trailhead | 学习目标、解释、案例、练习、总结 |
| 个人介绍、作品集、旅行分享 | Lookbook、Scrapbook | 人物、经历、照片、故事与成果 |
| 活动策划、年会、阶段回顾 | Quiz Night、Wrapped | 流程、亮点、参与和回顾 |
| 财务、经营与预算 | Annual Report、Ledger | 指标、变化原因、预算与预测条件 |

表中16份主题原文已取回，保存在私有准备目录。128是上游设计规范条目数，30是上游模板样式数。实际进入当前Agent目录的数量由后续接入与验收记录给出。

## Skill限制审计与合并策略

slide-maker固定版本的`SKILL.md`共3141行。已查到以下影响GeneLoop的规则，改造时逐项迁移。

| 原始规则 | GeneLoop适配处理 |
| --- | --- |
| 第14、26–28、156行要求独立critic同意，用户才能选择跳过 | 机械质量检查由宿主执行，视觉检查绑定成品版本。独立LLM评审后台运行，其费用单列。明确缺陷触发修复，主观建议进入反馈材料 |
| 第166–168、251行将checkpoint设为用户确认的硬停止点 | 已给出目标、受众和用途时直接制作，采用合理默认并在结果中记录关键假设。缺少决定任务含义的信息时集中询问 |
| 第46行等要求signature move和额外风格证明 | 作为创意型任务的可选设计能力，由用户风格和用途决定 |
| 第225行要求每份稿读取checkpoint文档 | 将固定字段与校验编译进宿主，设计参考按需检索 |
| 第236–242行要求指定DeckKit构建及其整套检查证据 | 吸收可独立认证的页面函数，依赖通过适配器接统一制作和交付协议 |
| 上游完整流程同时含访谈、设计、构建、评审与交付 | GeneLoop拥有一份任务状态与恢复策略，各上游贡献设计资产和执行模块 |

SlideSpeak的Boardroom原文包含24px标题、六格固定进度条、`Source: team analysis · Northwind`示例来源，并要求先询问主题。适配时按实际画布与可读性换算字号，进度条来自真实章节数，来源绑定用户材料，已明确的主题直接使用。字体按中文覆盖和实际环境校准，艺术风格要求转为可选样式参数。

PPT Master锁定6.6.0中已有14类styles、7类layouts和21类brands。styles已覆盖商务复盘、方案提案、产品发布、融资路演、教学与科普。当前宿主`design-profiles.json`只提供一个academic默认profile，通用接入需要新增中性默认值及用途选择。品牌目录涉及logo与身份表达，普通任务优先使用中性主题。

统一方案由一个GeneLoop制作协议连接内容规划、主题与组件选择、页面制作、共同交付和多轮改页。PPT Master的模板、原生对象与导出模块可以内置，保留来源、版本锁、许可证和回归证据。Skill入口作为精简的兼容说明，宿主负责固定操作和执行权限。

## 科研专项补充候选

| 资源 | 实际材料 / 许可 | 对当前Agent的价值与限制 |
| --- | --- | --- |
| [wzpan/BeamerStyleSlides](https://github.com/wzpan/BeamerStyleSlides) | Beamer风格PowerPoint/Keynote成品，MIT；[LICENSE](https://github.com/wzpan/BeamerStyleSlides/blob/master/LICENSE) | 科研专项候选。已有Madrid、Boadilla、CambridgeUS等主题。可先选3套样式，复用母版和内容页。仓库用Git LFS，须实际取回PPTX并检查字体、比例和Office兼容性 |
| [M1n-n9/academic-ppt-master](https://github.com/M1n-n9/academic-ppt-master) | 科研SVG模板、Academic Paper/Defense、blue/graphite预设，MIT；[LICENSE](https://github.com/M1n-n9/academic-ppt-master/blob/main/LICENSE) | 适配现有SVG制作路径较直接；这是此前关注过的候选，不是新发现。主要吸收结果、方法、讨论等页型，避免完整叠加第二套Skill流程；先比对已有资产去重 |
| [yctrrr/academic-ppt-template](https://github.com/yctrrr/academic-ppt-template) | 6页可编辑参考稿和PptxGenJS组件，MIT；[LICENSE](https://github.com/yctrrr/academic-ppt-template/blob/main/LICENSE) | 原生图表、箭头及统一字体/颜色约束值得借鉴。它是小型新候选，不能称成熟大库；生成后接共同验收，不能同时额外跑一套无限校准流程 |
| [SlidesCarnival](https://www.slidescarnival.com/) | 可编辑PowerPoint/Google Slides模板；[官方条款](https://www.slidescarnival.com/terms-of-use/)声明CC BY 4.0 | 成熟成品资源；属于开放许可设计资产而非代码框架。挑简约、研究、答辩模板；保留署名与素材各自来源。对外资源链接指向模板页面，不把下载文件链接当推广链接；逐套检查附带素材许可 |
| [PptxGenJS](https://github.com/gitbrent/PptxGenJS) | MIT代码及[demos](https://gitbrent.github.io/PptxGenJS/demos/) | 更适合补充原生可编辑表格、数据图和流程组件，不是成品模板库。项目早期已有此路径，不能把引入同库称新引擎突破 |

## 暂不直接纳入默认库

- [SciFig模板](https://github.com/scifig-ai/scientific-poster-and-presentation-templates)：154份中144份为海报、10份为幻灯片；提供科研会议/组会/答辩结构。其[自定义许可](https://github.com/scifig-ai/scientific-poster-and-presentation-templates/blob/main/LICENSE)允许科研教学个人使用，但限制以其他品牌重新分发模板；不能因GitHub公开就按MIT打包进我们的库。可提供上游资源入口，产品内再分发须另核授权。
- [ai-ppt-template/free-ppt-template](https://github.com/ai-ppt-template/free-ppt-template)：[许可](https://github.com/ai-ppt-template/free-ppt-template/blob/main/LICENSE)为CC BY 4.0，目录和README数量不一致，不以宣传总量作验收。README说明用图像模型整页生成再封装PPTX；不能据扩展名推定元素可编辑，且可能继续强化用户不喜欢的AI感。仅作候选视觉参考，先解包验证可编辑性，不批量导入。

## 最小接入方案

1. 首批采用表中八类场景的16份设计材料，编译成GeneLoop主题参数。并行筛选slide-maker七类页面组件和Presenton通用页型。每类至少检查一份内容页与一份数据或图文页。
2. 模板版本清单记录来源URL/commit、许可证与署名、文件SHA、母版、尺寸、字体、颜色角色、页面用途、文字容量、图表/公式能力。外部字体、logo和图片单独记录，不假定顶层许可涵盖所有品牌权利。
3. 现有路由支持PPTX母版复用和SVG参数化，统一交付保持文字、图表与形状可编辑。通用页型覆盖图文、对比、时间线、流程、指标、表格、图表、人物、报价、日程与结尾。
4. 一次离线校准+实际Office渲染，测试中文、公式、长标题与超容量；通过后才给宿主选择。任务只看到少量能力卡/预览和契约，按需读取，不读取完整模板目录。
5. 模板导入是工程资产建设；RSI另行学习真实采用条件、容量失败与有效修复。记录selected/executed/in_final_delivery/quality/cost，避免把试用次数当收益。

自然语言任务可直接给出主题、受众、用途、风格和大致长度。产品流程应支持纯文字需求，附件用于补充材料。企业实际营收、真实客户案例等事实需要用户资料或可靠来源，示例数据明确标注。科研证据核对按任务启用，通用质量维度使用内容准确、视觉、可用性和需求符合度。

验收先覆盖纯文字生成、附件改编、用户模板和局部修订四类入口，再检查每种主题的字体、长文本、图片与表格容量。预期节省来自复用布局、样式和构建程序，实际费用由后续独立任务统计。
