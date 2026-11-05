# Desktop preview.11 原生执行验收

- 问题：Windows 是否能用已有 DSH Agent 和云模型完成本机六场景，复杂视频不再依赖 Linux 渲染？macOS 构建入口能否复用同一套工作区/Agent，而只替换原生依赖？
- 任务：六个独立合成小任务；分别为乘法、读文本写报告、CSV 分组、TeX/Bib 引用核验、带字段 PPTX 模板及来源填充、Remotion TSX 叠字视频。没有人工盲评或成本对照，不代表完整科研能力、普遍质量或收益。
- 配置：桌面 `0.3.0-preview.11`，工作树基于 `c803ae15` 加候选改动；DSH `0.1.5-rc.3`，Electron `45.2.1`，其 Node `24.22.1`；Windows x64。工具为 Python 3.12.10、LibreOffice 26.8.2.2、FFmpeg 8.1.2、Remotion 4.0.539 及配套 Chromium 157.0.8080.0。模型 `deepseek-flash`、推理 `off`，任务费用/输出上限 `null`，沿用 V100 原试用账本、不清零；任务授权十分钟。运行时 CLI/工具来自本地打包 ASAR 与 extraResources。
- 结果：chat/files/data/paper/ppt/video 分别 1/3/3/3/5/4 次真实请求，共 19 次。源文件摘要保持不变；实际调用对应本机工具并核对交付。视频调用 `local_video_render` 的 `{source,assets}` 计划，本机交付 MP4/TSX/回执且完整解码，未发生远程渲染进度或上传确认。PPT 交付一套 PPTX/PDF/回执。运行记录 `.local/desktop-preview11-real-1793910776167/summary.json`，账号、配置和原始轨迹不进入 Git。
- 免费诊断：`npm --prefix apps/desktop run check` 12 项通过；`smoke:renderer` 17 项通过。`smoke:native` 检查原生句柄、相对路径、硬链接拒绝和授权关闭。打包 Electron + ASAR 实际运行 `check-native-remotion.mjs`、`check-native-ppt.mjs`、`check-native-process.mjs`，覆盖渲染/完整解码、模板/PDF/源不变、凭证过滤及取消孙进程。结果 `.local/preview11-native-checks.json`。这些诊断不替代上述真实模型试验。
- 失败与处理：DSH Windows ACL 后端不支持受限进程用 libuv 命名管道启动孙进程，也阻断 Chromium Mojo，原方案实际失败。固定编译工具改由 DSH 管理生命周期；Windows 浏览器桥去除 Remotion 的 `--no-sandbox`，使用 Chromium 渲染沙箱。不能把它描述为整个编译进程的文件读取/网络隔离。ASAR 中 esbuild 的执行路径改为相邻实体文件；Office/Chromium 在私有临时目录创建只读目录，清理仅遍历本次目录且不跟随链接。
- 全量回归：`npm test` 的 Python 部分为 132 失败、2125 通过、273 跳过、30 错误，保留 `.local/npm-test-preview11-native.log`。与 preview.10 名单比较，新增三项失败中两项单独复验通过，文献 Agent 的 Windows rename EPERM 仍复现；该模块未在本轮修改。不能据失败总数减少认定无回归，不能宣称全量测试通过。Node 全量日志另保留 `.local/node-test-preview11-native.log`。
- 成本：19 次为本轮这组成功验收的请求增量；累计账本保留了此前失败/调试调用。此记录未核对服务商账单，未据请求数推算人工修订费用或端到端节省。
- Mac 首轮边界：源码 `6ada3a13` 的[首次 CI](https://github.com/jingyio/GeneLoop/actions/runs/42105245995) 两台机器均未启动，GitHub 注释为账号因账单问题被锁定，步骤为空；不能把该状态写为代码测试失败。后续按用户授权在独立私有仓库完成原生复验，见下节。构建流程没有安装包上传步骤。
- 本地安装包：647218688字节，SHA-256 `79648c9fff0f26c4e85f72be0f5f62fb888cc2cdc7392e13929b7a88e88a195c`，内嵌Engine摘要匹配。保留 `.local/desktop-preview11-verified/installer-verification.json`，未上传或覆盖日常安装。
- Motif：代码与打包摘要发生变化，旧认证不自动适用于本候选。安装版继续普通 Harness 执行。后续需要在新版本上重新编译/认证，且扩大无字段模板、数据任务、论文核验与视频测试；本记录不支持所有场景迁移完成或成本下降的结论。

## 2026-11-06 Mac 原生跟进

- 在用户授权的独立私有构建仓库执行 macOS 15 ARM64、macOS 15 Intel；不上传安装包和原始运行材料。构建入口仅手动运行，无关流程关闭；私有任务和额度台账保存在 `.local/private-mac-ci-budget.json`，不进入 Git。
- 首轮发现 ARM64 的 `openat` 创建模式参数被错误声明为固定参数，造成报告无读取权限；修为 libc 可变参数调用。Intel 的目录接口改为匹配 64 位 inode 的 `fdopendir/readdir/rewinddir`，保留路径、链接与关闭授权检查，新增产物 0600、输出目录 0700 的实际权限检查。两种架构原生文件检查已通过。
- 离线依赖准备发现版本标签的仓库根目录不符合原技能锁。改为精确上游提交的可安装技能子目录；本机流式核对 13,016/13,016 文件一致，归档 SHA-256 为 `080565fa68ab0cf4c8f75dbb3e0095a8ddd636298766bea394a9daf21c94de4d`，没有重置或放宽技能锁。
- Mac 渲染失败逐项修复：FFprobe 的裸动态库名称依赖工作目录，构建时重定位媒体工具及相邻 dylib 并 ad-hoc 重签；精简 FFmpeg 不含默认 `wrapped_avframe`，完整解码显式使用 rawvideo/PCM 输出至空设备；Webpack 将 POSIX ASAR 绝对路径误拼到临时网页根目录，使用 `resolve/resolveLoader.preferAbsolute` 优先实体绝对路径。未升级上游 Agent 或另造 Agent 循环。独立 PPT、取消及打包检查即使另一项失败也继续收集，任务仍保留失败结论。
- 最终 Mac 无模型诊断通过：macOS 15 ARM64、Intel 均实际启动 `.app` 内 DSH Agent，从 ASAR 加载插件和依赖，读取/搜索文本、写报告、拒绝越界/硬链接、撤回授权、取消等待并正常退出；每侧仅 3 次回环协议夹具请求，真实模型请求为零。两侧同时通过原生文件权限、凭证过滤及取消孙进程、PPTX/PDF/模板不变、独立及 ASAR Remotion 渲染与完整解码。MP4 均为 1 秒、640×360、12fps；不同架构的编码摘要分别保留。私有摘要 `.local/macos-native-verification-20261106.json` 绑定 CI head `796c96771876673183450da62b07eb78f18df16a` 和两份 job 日志，不进入 Git。
- 打包边界：最终轮使用 `app` 模式完成包内检查；前一轮双架构 DMG/ZIP 已实际构建，但不能把旧候选压缩包称为最终修复版安装验收。没有上传任何 Actions 产物或安装包，收尾关闭私有仓库 Actions。尚未完成 Mac 真实模型六场景、人审界面、Apple Developer 签名及公证。Mac 的渲染器写入限制也不代表全面读取/网络隔离。
- Windows 跟进：桌面 12 项、原生文件、视频 5 项（另 1 项 Linux 探针跳过）、新临时 ASAR 的真实渲染/完整解码、安装布局 DSH Agent 探针均通过。包内证据 `.local/mac-fix-win-asar-Cj48ZE/result.json` 位于 `apps/desktop/`；Agent 日志 `.local/probe-macos-followup-windows-20261106.log`。最终另加强伪装图片作为内联加载器的拒绝诊断，Windows 原生检查通过；Mac CI 运行的是此前入口脚本拒绝用例。此测试改动没有改变已验证的生产运行时。
- 全量回归仍未通过：最终 `npm test` Python 段为 2190 通过、68 失败、272 跳过、30 错误；Node 按项目 Python/UTF-8 环境另运行为 1545 通过、23 失败、63 跳过，共 1631 项。Python 无新增失败名称；Node 相比旧日志新增的文献 Agent 用例因 Windows `rename EPERM` 失败，单独复验通过，不据此消除整轮失败。保留 `.local/npm-test-macos-final-20261106.log`、`.local/node-test-macos-final-20261106.log`、`.local/macos-final-failure-comparison.json`、`.local/macos-final-literature-rerun.log`。首次直接 Node 检查遗漏 UTF-8 环境的日志另存，不作为有效对照。
