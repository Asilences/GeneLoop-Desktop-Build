# 本机完整工具适配（preview.17 候选）

preview.21起正常构建恢复完整离线分发：六场景现有工具随应用安装到资源目录，默认不再要求安装后统一准备；`npm run dist`选择完整包，`npm run dist:lite`仅供显式选择小包。工具范围沿用下面的preview.20修订，既有分包与旧安装器保留；Mac需另外原生构建，旧DMG不因源码默认值改变而改变。

preview.20已完成以下最新范围的实际分发更新：三平台六工具包（无speech），精简native Office Kit，共享Playwright Node／Chromium，GeneLoop自有PPT制作Skill；统计、OCR、材料与媒体能力按当前实现保留。依赖导入、实际统计回归及PPT模板／PDF原生检查通过，未重做模型效果／Mac人工安装验收。新包在本地，试用须导入对应工具目录；[大小及验证记录](../../debug/desktop-preview20-tool-refresh-20261108.md)。下面preview.17的语音依赖表和构建说明为历史，不能作为新版本安装要求。

2026-11-08范围修订：桌面PPT仅制作、编辑与核验，不再默认准备语音包或edge-tts，也不提供旁白／演示视频／字幕扩展；下文preview.17为历史适配记录，新构建以[最新范围](../../debug/desktop-ppt-authoring-scope-20261108.md)为准。独立视频剪辑与Remotion保留。

六场景已按当前main、相关PR、实际server／工具函数、桌面接线和构建依赖[交叉核对](../../debug/desktop-scene-scope-review-20261108.md)。Paper不新增LaTeX编译环境；Video保留现有音轨和字幕编辑，不新增ASR；Data保留当前报告实际使用的统计／绘图库；Chat／Files及共享PDF保留明确要求的OCR和公共工具。早期窄能力、单题限制、未验证状态不作为削减当前功能的依据。

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
