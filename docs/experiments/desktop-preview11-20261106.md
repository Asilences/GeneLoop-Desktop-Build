# Desktop preview.11 原生执行验收

- 问题：Windows 是否能用已有 DSH Agent 和云模型完成本机六场景，复杂视频不再依赖 Linux 渲染？macOS 构建入口能否复用同一套工作区/Agent，而只替换原生依赖？
- 任务：六个独立合成小任务；分别为乘法、读文本写报告、CSV 分组、TeX/Bib 引用核验、带字段 PPTX 模板及来源填充、Remotion TSX 叠字视频。没有人工盲评或成本对照，不代表完整科研能力、普遍质量或收益。
- 配置：桌面 `0.3.0-preview.11`，工作树基于 `c803ae15` 加候选改动；DSH `0.1.5-rc.3`，Electron `45.2.1`，其 Node `24.22.1`；Windows x64。工具为 Python 3.12.10、LibreOffice 26.8.2.2、FFmpeg 8.1.2、Remotion 4.0.539 及配套 Chromium 157.0.8080.0。模型 `deepseek-flash`、推理 `off`，任务费用/输出上限 `null`，沿用 V100 原试用账本、不清零；任务授权十分钟。运行时 CLI/工具来自本地打包 ASAR 与 extraResources。
- 结果：chat/files/data/paper/ppt/video 分别 1/3/3/3/5/4 次真实请求，共 19 次。源文件摘要保持不变；实际调用对应本机工具并核对交付。视频调用 `local_video_render` 的 `{source,assets}` 计划，本机交付 MP4/TSX/回执且完整解码，未发生远程渲染进度或上传确认。PPT 交付一套 PPTX/PDF/回执。运行记录 `.local/desktop-preview11-real-1793910776167/summary.json`，账号、配置和原始轨迹不进入 Git。
- 免费诊断：`npm --prefix apps/desktop run check` 12 项通过；`smoke:renderer` 17 项通过。`smoke:native` 检查原生句柄、相对路径、硬链接拒绝和授权关闭。打包 Electron + ASAR 实际运行 `check-native-remotion.mjs`、`check-native-ppt.mjs`、`check-native-process.mjs`，覆盖渲染/完整解码、模板/PDF/源不变、凭证过滤及取消孙进程。结果 `.local/preview11-native-checks.json`。这些诊断不替代上述真实模型试验。
- 失败与处理：DSH Windows ACL 后端不支持受限进程用 libuv 命名管道启动孙进程，也阻断 Chromium Mojo，原方案实际失败。固定编译工具改由 DSH 管理生命周期；Windows 浏览器桥去除 Remotion 的 `--no-sandbox`，使用 Chromium 渲染沙箱。不能把它描述为整个编译进程的文件读取/网络隔离。ASAR 中 esbuild 的执行路径改为相邻实体文件；Office/Chromium 在私有临时目录创建只读目录，清理仅遍历本次目录且不跟随链接。
- 全量回归：`npm test` 的 Python 部分为 132 失败、2125 通过、273 跳过、30 错误，保留 `.local/npm-test-preview11-native.log`。与 preview.10 名单比较，新增三项失败中两项单独复验通过，文献 Agent 的 Windows rename EPERM 仍复现；该模块未在本轮修改。不能据失败总数减少认定无回归，不能宣称全量测试通过。Node 全量日志另保留 `.local/node-test-preview11-native.log`。
- 成本：19 次为本轮这组成功验收的请求增量；累计账本保留了此前失败/调试调用。此记录未核对服务商账单，未据请求数推算人工修订费用或端到端节省。
- Mac 边界：已准备 macOS 15 ARM64、macOS 15 Intel 的 GitHub Actions 原生构建、文件守卫、PPT/PDF、Remotion 和取消测试。Python 便携包与 LibreOffice 下载均固定版本和 SHA-256；Mac 工具尚无运行结果。构建流程没有安装包上传步骤。
- Motif：代码与打包摘要发生变化，旧认证不自动适用于本候选。安装版继续普通 Harness 执行。后续需要在新版本上重新编译/认证，且扩大无字段模板、数据任务、论文核验与视频测试；本记录不支持所有场景迁移完成或成本下降的结论。
