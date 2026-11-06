# Desktop preview.13 完整场景工具适配

## 目标与边界

在已有独立桌面、统一工作区和对话输入框上复用原场景工具，替换需要 Linux 的执行底座。DSH 继续负责 Agent、会话、工具调度与子进程生命周期；没有新增 Agent 循环，没有 WSL，也不自动转云端。工具接通不等于科研质量、Motif 认证或任意文档兼容性通过。

## 实现

| 场景 | 本机入口 | 复用与平台替换 |
|---|---|---|
| 通用对话 | 4 项通用 MCP，可按需加载报告、论文和 PPT 工具 | 复用文本创建/精确编辑；固定脚本入口改用 QuickJS WASM，只有已选输入和新文本输出绑定，不把 Node worker 当安全隔离 |
| 文件管理 | 13 项原 MCP | 原文件身份、索引、预览、授权、执行、恢复和报告；整理当前任务副本，确认通过私有桌面 IPC，交付整理 ZIP，原件不变 |
| 数据分析 | 17 项原 MCP | 原 V3 统计设计、计算、复算、选图、图表、模型正文、PDF 和交付；沿用 V1/V2 数值及文档引擎，不手写另一套统计规则 |
| 论文材料核验 | 20 项原 MCP | 原来源/引用证据、arXiv/Crossref、审校草稿和最终版本；本机 PDF 导出复用已有 document_engine，不冒充 Linux 学习渲染器的认证 |
| PPT | 21 项交付 MCP + 5 项官方技能/转换 MCP | 原图件、页计划、可编辑图表/流程图、风格转换、修订、失败草稿修复、Office PDF/PNG 核验；保留基础字段模板和普通模板编辑工具 |
| 视频 | 11 项本机对应入口 | 原生 Remotion/Chromium、完整解码、源码/素材版本、备注；Linux 媒体 shell 改为受限 JSON `probe`/`audio_stats`，真实 PCM 统计，不接受任意 shell |

共 91 项场景入口。原 MCP 的参数 Schema 由服务实际发现，使用 `mcp__native_*` 名称直接注册到 DSH，保留独立工具轨迹。模型网关与宿主共用版本化白名单。`local_workflow_open` 只准备明确选择的来源和加载工具，不新开任务面板。

Windows/Mac 随包提供目标平台 Python wheels、原场景代码、Office、媒体和浏览器；Node 生产依赖放 ASAR。Python 版本守卫需要读取的少量 PPT JS 副本单独落盘，执行前与 ASAR 字节逐一核对。官方技能保持原锁，构建排除 `.env`、`.git`、`.local`。OCR 使用已有 PyMuPDF 原生引擎和固定 Tesseract fast 4.1.0 中英文数据，保留许可证与 SHA-256，不增加运行期下载。

新工具协议为 `toolsetVersion:3`。版本 2 保留 preview.12 工具，未声明版本保留旧工具；服务器源码存在不等于正式公网已部署。这里没有新增账号认证接口或放宽现有计量/授权。

## 当前验证

- Windows：实际 MCP 发现/调用和 80 项 DSH 注册、文本输出、QuickJS 代码执行、文件方案拒绝/确认/ZIP、来源失效、PPT→Office PDF/PNG、官方 PDF→Markdown 转换通过。原生 Remotion 渲染/完整解码、裁剪拼接和真实 PCM RMS 统计通过。桌面编译和已有 12 项定向检查通过。
- Windows：固定中英文语言数据上的实际扫描页 OCR 通过。OCR 是转录，不能代替原图或科研内容审阅。
- 上述为合成材料上的真实工具诊断，无模型请求，不是场景效果/费用验收。私有日志使用 `native-workflows-check.log`、`native-media-full.log`、`native-code-check.log`、`native-ocr-check.log` 和 `native-workflow-desktop-check.log`。
- 本轮打包后验证、Mac 两架构新增工具验证及真实模型完整流程尚待完成，不能沿用 preview.12 的成功记录冒充本轮通过。

## 后续验收与回退

保留 0.2.40、preview.11 和 preview.12 已有源码/产物。正式服务不在本轮直接切换；V100 真实模型验收须使用原账号与累计账本，先通过统一生命周期入口 status/check 确认。Mac 仍仅使用已授权免费额度，安装包和 CI 产物不上传。跨平台 Motif 库须按新工具/渲染/语言数据版本重新认证，不能直接重标旧证书。
