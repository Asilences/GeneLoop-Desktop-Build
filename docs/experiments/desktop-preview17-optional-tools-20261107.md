# preview.17 可选工具补齐与统一离线检查

- 实验 ID：`desktop-preview17-optional-tools-20261107`。
- 问题：六场景的 MCP 接线已存在，但 Skill 的可选依赖、脚本输出路径、完整媒体工具与私有动态注册仍有差异。先补适配，再做一次简短统一诊断；不重跑复杂场景和成本对照。
- 版本：候选基础 `e137ec97`；统一材料 CLI 转接及依赖锁修复 `de2434bc`。安装提速基线 `b5701bdc` 保留，安装事务／解压器源码未改；只把新增工具目录加入既有 SHA 复用清单。

## 完成范围

补齐 18 项直接 Python 依赖、Pandoc、共享 Chromium、分词缓存；Mac 使用完整静态 FFmpeg，Remotion compositor 仍保留自己的固定依赖。字幕对齐随包携带 stable-ts、CPU Torch 和 Whisper base。语音 NumPy 1.26 与数据分析 NumPy 2.2 隔离。Windows 官方 wheel 记录扩为 117 项，保留版本与 SHA。

锁定 Skill 原文件未修改；原生绑定经过逐文件 SHA 检查，将项目根放入任务私有目录，旧 Office 文档／Office 矢量预览交给 LibreOffice。桌面私有 MCP 沿用网页 Gateway 的注册校验、权限与回执；宿主传递凭证引用和值，值只在内存中使用。没有新增 Agent 循环或模型设置页面。

## 统一诊断结果

| 环境 | 对象与结果 |
| --- | --- |
| Windows x64 | 实际工具目录统一检查 10 组通过；18 个可选模块导入，实际 RTF→Markdown、RST→HTML、SVG→PNG、浏览器截图、离线分词、音频滤镜、CPU 语音权重加载、私有注册及凭证不落盘 |
| Mac ARM64 | 实际 `.app` 内相同 10 组检查通过，源码 `e137ec97` |
| Mac Intel x64 | 实际 `.app` 内相同 10 组检查通过，源码 `e137ec97` |
| 统一材料 CLI | 修复 `source_to_md.py` 嵌套进程转接后，Windows 实际 CLI RTF 转换通过；Mac 两种架构仅追加真实 DOCX→Markdown 入口回归，也通过，不重复构建整套工具 |

Mac [run 42362449444](https://github.com/Asilences/GeneLoop-Desktop-Build/actions/runs/42362449444)，标准公开免费 runner `macos-15` / `macos-15-intel`；产物数量 0，收尾关闭 Actions。未使用私有收费 runner、未上传安装包或 Release。

Mac CLI [run 42364161908](https://github.com/Asilences/GeneLoop-Desktop-Build/actions/runs/42364161908)，源码 `15ba23ae`，两种架构通过，产物 0，收尾关闭 Actions。前一轮精简夹具漏了上游署名文件，触发原始保护退出 78；改为按锁保留完整官方发行后通过，没有修改上游文件或关闭校验。此结果验证追加入口，不追改前一轮 `.app` 的源码版本。

Windows 编译通过。打包遇到旧预览输出中的 EXE 正在占用后，改在全新目录构建，未强退旧实例或覆盖用户安装。Python 裁剪保留既有运行时例外；本次移除 12,515 项测试／缓存文件、250,985,296 字节。没有把构建或解压耗时当作新版本的完整安装耗时。

Windows 完整离线候选 `GeneLoop-Desktop-0.3.0-preview.17-x64-Setup.exe` 已生成，2,047,067,136 字节，SHA256 `55540bfac2a6803698fcec86ace467a22626f6520d5d05c400d39308754974c2`；执行源码对应 `de2434bc`。最终 ASAR 与原生绑定逐文件一致，裁剪后的 NumPy、SciPy、Notebook、SVG、网络与分词库导入通过。此包包含完整语音依赖与离线权重，体积约 2 GB；未覆盖用户安装、未实测此版本完整安装耗时，也未上传。

## 证据与限制

私有记录：`.local/desktop-complete-tools-20261107/` 的构建、统一检查、CLI 检查、Mac 日志和 `mac-verification.json`；本地 Windows 候选输出 `.local/desktop-preview17-complete/`。不提交日志或机器私有路径配置。

- 本轮聊天模型 API 调用 0，费用 0；不据此宣称六场景真实任务效果、字幕实际对齐质量或成本收益。语音检查加载真实随包权重，未做用户音视频对齐任务。
- 第三方图片／语音／联网服务需要用户自己的服务连接和凭证；未发现可用的真实私有 MCP 配置，因此验证注册与凭证隔离，不冒充这些未知服务已验收。
- Windows PowerPoint 原生动画导出仍要求已安装 Microsoft PowerPoint；Mac 使用已有 SVG/Remotion 链路，不把它宣称为相同 Office 自动化接口。
- 未部署正式模型网关、未更新 Motif／隐私核心，也未做 Mac 人工 UAT 或签名公证。下一步可用真实任务试用；出现具体问题时针对失败路径修复，不重复整套诊断。
