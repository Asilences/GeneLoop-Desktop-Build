# Desktop preview.12 工具适配记录

- 目标：补齐 Windows/macOS 六场景的本机工具覆盖，复用 DSH Agent 与现有场景代码；不改网页布局、不切换正式服务、不上传安装包。
- 代码：基于 `codex/desktop-local-runtime` 的 `7e45a835`；工具清单在 `apps/desktop/runtime/local-scenes.mjs`。Python 统计核心从 Web server 提取到 `scenarios/data_analysis/evidence.py`，Web 仍导入同一实现；论文复用 `paper_static_checks.py`。固定模块仅处理宿主从授权目录复制的快照，不接受用户 Python/shell 程序。
- 范围：共用文档来源固定与分页；XLSX/JSON/CSV 等显式表格统计及相关；文件 ZIP 副本整理；多文件论文静态核验；普通 PPT 文本框副本编辑及 PDF；Mac 时间线裁剪拼接使用本机 Remotion。来源变化拒绝、公式拒绝/CSV 文字转义、归档路径守卫保留。旧网关按工具协议兼容，不暴露其不认识的新工具。
- Windows 无模型验证：桌面定向 12 项通过；真实 Python 文档/表格/静态检查/ZIP 工具通过；PPT 字段模板及普通模板修改、PDF、原件不变通过；Remotion 实际渲染/完整解码及片段裁剪拼接通过。全部使用临时合成文件，真实模型请求 0，不作为科研效果或稳定成本证据。
- Mac：macOS 15 ARM64/Intel 单轮原生及包内检查均通过，包括普通模板修改、表格/文档/静态核验/归档、时间线裁剪拼接，以及原 DSH Agent 启动/读写/取消/关闭；全部无模型。CI head 为 `1b5d5c9465e9945464784fe5a8ac0055bee68f1f`，私有回执 `.local/preview12-macos-verification.json`。零上传产物，结束后关闭 Actions；持续沿用原免费额度台账与上限，不开启额外付费。
- 本地应用：Windows `apps/desktop/release/win-unpacked` 的包内检查通过，ASAR SHA-256 为 `2ced45287b5b412e6a923fc89208498ea272f3bf5b903a5f0aa644916489dee0`；固定 Python 源文件与本轮源码摘要相同，证据 `.local/preview12-windows-package.json`。仅生成应用目录，没有替换 preview.11 安装包或日常安装。Mac 本轮也只构建 `.app`，无最终 DMG/ZIP 安装体验验收。
- 全量回归：仅运行一次 `npm test`，Python 2190 通过/68 失败/272 跳过/30 错误，停在已有失败组，Node 全量未自动执行。与前轮日志比对无新增失败名称；不宣称全量通过。日志 `.local/npm-test-preview12-tools.log`、`.local/preview12-regression-comparison.json`。未为测试变绿删除原检查。
- 边界：未重复六场景真实模型试验；Mac 人工界面、签名公证及全部科研工作流等价未验收。旧 Motif 认证不自动适用于新工具/schema。CSV 转义和旧网关兼容是在 Mac CI 固定提交后追加，定向 Windows 复验与该轮 Mac 结果分开记录。主安装包与工具包分拆下载暂未实现。
- 回退：保留 `7e45a835`、preview.11 本地安装包及更早冻结版本；新增输出文件独立保存，预算累计账本不清零。正式网页与用户工作区原件未修改。
