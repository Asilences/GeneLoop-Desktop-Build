# GeneLoop PPT integrated policy v2

GeneLoop管理制作与恢复流程。PPT Master 6.6.0提供固定版本的设计资源、原生对象与导出模块。详细参考按当前操作读取。

- 新稿可由纯自然语言发起。read_ppt_design返回主题卡或单个组件契约，start_ppt创建项目。用户提供模板时沿其设计和原生PPTX路线处理。
- 内容规划完成后prepare_ppt校准当前角色的常规与粗体字体。使用返回测量表。主题参数已包含中文字体回退、可读字号和配色。
- 适用的认证组件由create_ppt_page生成并安装。parameters和parameters_file二选一。project使用完整项目路径，page为SVG文件名。修订传expected_page_sha256。宿主核对版本、安装及字号角色，模型提供内容与备注。
- Generate交付使用finalize_ppt(project)。宿主生成清单、执行官方格式检查、导出原生可编辑PPTX并渲染Office PDF/PNG。相同文件和环境复用结果。
- 用read_image检查Office页面。明确可见缺陷、具体错误或新反馈触发对应页修订。warning按当前画面评估。字体校准、DPI与字符框诊断由宿主完成。
- 同一缺陷缺乏进展时切换有效方法或回退普通制作。常规工具恢复沿当前任务执行授权推进。内容歧义与影响用户原件的操作按产品权限处理。
- 独立LLM评审在后台按配置执行，与学习费用单列。结果绑定成品版本，科学事实需有实际原文证据。用户反馈进入后续学习材料。
- 最终输出来自当前版本回执。保留来源、许可证、版本、审计与失败记录。
