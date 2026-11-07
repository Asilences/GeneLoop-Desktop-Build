# 本机完整工具适配（preview.17 候选）

此轮在 preview.16 的原 MCP、DSH 公共工具和六场景接线上补齐 Skill 可选依赖。场景仍复用上游 Agent；不改锁定版 PPT Master 的文件，不重新认证 Motif。工具能运行、模型能选对工具和实际交付合格分别验收。

| 范围 | Windows / Apple Silicon / Intel Mac 的处理 |
| --- | --- |
| 文档与材料 | 补 Mammoth、Markdownify、EbookLib、nbconvert、nbformat、OpenPyXL；旧 Office 文档用随包 LibreOffice 转为 DOCX，RST/Org/TeX 等源格式使用固定版本 Pandoc |
| 形状与字体 | 补 Skia PathOps、HarfBuzz；SVG 位图回退采用 svglib、ReportLab 和原生 renderPM，不要求用户另装系统 Cairo |
| 页面预览与令牌计算 | Python Playwright 和 Remotion 共享一份匹配版本的 Chromium；o200k_base / cl100k_base 缓存在构建时准备 |
| 音频、视频与字幕 | Windows 继续使用完整 FFmpeg；Mac 公共媒体命令改用可独立迁移的完整静态 FFmpeg，Remotion 保留固定 compositor；随包时间戳对齐组件使用 stable-ts、Whisper base 和 CPU Torch |
| NumPy 兼容 | 数据分析保持 NumPy 2.2；语音组件隔离为 NumPy 1.26。Intel Mac 使用仍提供 Intel wheel 的 Torch 2.2.2，不在用户电脑编译 |
| 项目输出 | Skill 项目根绑定到当前任务私有目录；旧 Office 文档、EMF/WMF 预览绑定到 LibreOffice。绑定前校验原 Skill 文件 SHA，不覆盖原工作区资料 |
| 私有动态工具 | 桌面宿主读取 userData 下 `local-tools/providers.json`；复用网页 Gateway 的注册校验、发现、准备、执行和回执。支持 stdio / streamable-http 及按系统选择命令 |

## 外部条件

- 图片生成、第三方语音、网络取图、网页与在线公式服务仍需要各自的网络、连接或用户凭证。打包 SDK 不代表已配置账号，不把服务商密钥写入场景文件。
- 上游 `powerpoint_video.py` 使用 **Windows 已安装 Microsoft PowerPoint** 的 CreateVideo 自动化。保留其原生动画导出和条件检查，不用静态帧冒充同等动画能力。Mac 使用已有 SVG/Remotion 视频链路，此 Windows 专属脚本不宣称在 Mac 原样可用。
- `update_repo.py`、图标同步等维护脚本不用于修改安装中的锁定 Skill；通过新安装包更新，不在用户机器下载未固定版本的替代依赖。
- 私有 MCP 需要维护者提供当前系统的可执行程序和凭证，未配置的外部服务不能宣称验收通过。模型不能注册命令、授予权限；收费工具需要独立预算适配器。

## 构建和统一检查

构建输入的 Python 3.12 须预装 `native-tools-requirements.txt` 与 `native-tools-constraints.txt` 中的依赖，再 `npm run tools:stage`、`npm run tools:complete`（目录 `apps/desktop`）。Mac `prepare-macos-tools.mjs` 已自动串联依赖安装和准备。Windows 嵌入式 Python 无 pip 时，构建者设置 `GENELOOP_BUILD_PYTHON` 和 `GENELOOP_BUILD_PIP_PATH` 指向构建机工具，以构建语音 wheel；不构成用户安装要求。下载仅发生在构建机，默认使用不再下载 Whisper base、Chromium 或分词数据。

`check-native-extras.py <工具目录>` 是一次离线诊断：导入、实际文档转换、SVG 位图、浏览器截图、音频滤镜、语音权重加载、私有注册与凭证分离。不调用聊天模型，不替代六场景真实效果验收。Mac `complete-tools` 工作流使用两种标准公开免费 runner，不上传安装包或 Actions 产物。

追加 CLI 接缝可用 `cli-only` 仅检查真实 DOCX 转换，不重新构建整套工具。其临时夹具也保留完整锁定发行与上游署名保护。当前结果见[诊断记录](../../experiments/desktop-preview17-optional-tools-20261107.md)。

## 私有 MCP 配置

沿用网页的 `sss-general-tools-v1` 和 `providers` 数组。每个 provider 可选 `platforms.win32`、`platforms.darwin-arm64`、`platforms.darwin-x64` 覆盖命令和参数。stdio 命令使用绝对路径、`${PYTHON}` 或 `${NODE}`；`${SESSION_WORKSPACE}` 指向本轮私有目录。凭证通过 `{ "from_env": "变量名" }` 引用宿主环境，仅经私有 IPC 传递，不写进准备请求、模型提示或任务配置。该文件不随源码或安装包发布。
