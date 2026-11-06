# GeneLoop Desktop

0.3.0-preview.13 沿用独立桌面前端，提供 Windows x64、macOS ARM64 和 Intel 预览包。窗口、页面、组件、样式和交互状态由 `apps/desktop/` 实现，参考 GeneLoop 网页的视觉与场景。绑定本机文件夹的新会话由本机 DSH Agent 和工具执行，模型联网调用云端；原云端工作区仍由服务器执行。早期 0.2.0 只提供服务器执行入口。

## 本机工作区 Windows / macOS 预览

侧栏「新建工作区」提供本机和云端两种类型。「文件 → 打开本机文件夹」可直接打开已有工作区或将目录添加为本机工作区。工作区右键和三点菜单的「编辑工作区」可添加、更换或解除本机文件夹。两种入口共用工作区首页、侧栏和对话输入框。绑定按服务器和账号保存在本机，绑定后的新会话从主输入框发送时由本机 Agent 和工具执行。旧云端会话仍显示「云端」并在原服务器执行。本机新会话默认使用通用对话。六个场景共用本机 Agent 路由。缺少媒体依赖时，视频在发送前提示并暂停发送。登录后如工作区接口仍在加载或不可用，可在加载页点「打开本机文件夹」。

本机 Agent 以只读方式访问原始文件，只能在所选文件夹的 `GeneLoop 输出/` 下新建交付物。输出目录在首次写入时创建，旧版已生成的报告保留在原位置。解除绑定和移除本机工作区仅修改应用记录。侧栏「工作区视图」保存分组、排序和归档筛选偏好。

本机对话记录保存在桌面应用数据目录，同一工作区下可重新打开并继续对话。每轮重新检查目录权限并申请本机任务的模型授权。

Windows 和 Mac 本机预览均接通以下六个场景。工具及 Agent 包内检查已通过；完整真实模型效果、新 Motif 认证及 Mac 人工安装体验仍待验收，详见[本轮工程记录](../../debug/desktop-preview13-full-tools-20261106.md)。

- **通用对话**运行本机 Agent，按需读取所选目录和加载场景工具。固定脚本入口使用受限 QuickJS WASM，不开放任意宿主代码执行。
- **文件管理**复用原索引、方案预览、确认、执行和恢复工具；整理任务副本，交付 ZIP，原文件不移动或删除。
- **数据分析**复用原 V3 统计设计、计算、复算、图表、PDF 和交付工具；保留轻量表格统计入口。
- **论文材料核验**复用来源和引用证据、arXiv/Crossref、审校草稿及最终版本工具；扫描页可调用随包中英文 OCR，转录不能替代原图审阅。
- **演示文稿**提供模板、源材料转换、原生图表和流程图、修订、失败草稿修复以及 Office PDF/PNG 检查；交付可编辑 PPTX。Mac 随包中文字体通过私有 Fontconfig 供 headless Office 使用。视觉质量需要人工审阅。
- **视频编辑**使用本机 FFmpeg、FFprobe、Remotion 4.0.539 与 Chromium。简单时间线输出 720p/30fps 带音轨 MP4；复杂合成在本机编译 TSX 并渲染，最多 1080p/60fps、90 秒。素材按 SHA-256 核验，交付前完整解码。服务器渲染保留为明确上传确认后的独立能力，不作为本机失败时的自动回退。

未随包分发工具的开发版可将便携版 `ffmpeg.exe` 和 `ffprobe.exe` 放进桌面数据目录的 `local-tools/ffmpeg/`。开发版也可在启动前设置 `GENELOOP_FFMPEG_DIRECTORY` 为可信安装的 `bin` 绝对路径。工作区内容无法更改工具选择。此轮在本机验收环境准备了 Windows x64 FFmpeg 8.1.2 Essentials。验收命令 `npm --prefix apps/desktop run smoke:local-workspace` 需要设置上述目录。 [Windows FFmpeg 分发与校验摘要](https://www.gyan.dev/ffmpeg/builds/)

混合视频要求隔离网关启用 `desktopLocalModel.videoRendering: true`。渲染器可使用既有的 `memberSceneDeployment.videoRenderer` 容器，或通过 `desktopLocalModel.videoSandbox` 配置绝对路径 `rootfs`、`runtimeRoot` 和镜像内部的 Chromium `browser`。后者需要 Linux 用户及挂载命名空间、bubblewrap、可信只读系统镜像和锁定的 Remotion 4.0.539 依赖。桌面显示目标服务器和每份素材，用户确认后才发送快照。沙箱无外网，工作目录只读，临时文件占用有上限。桌面收回 MP4 后校验摘要和完整解码，再保存 MP4、TSX 和回执。素材最多 8 个，合计 16 MiB。

在同一对话中发送下一轮时，本机 Harness 续接同一目录和场景的会话上下文。「新会话」开启独立上下文。换用不同场景请另开会话。旧版本保存的任务可在对应工作区查看。

首次真实验收使用独立服务器启动计划和试用账号。候选账号网关配置中加入 `"desktopLocalModel": {"accountIds": ["<隔离试用账号 ID>"]}`。保持原有预算代理、累计账本、服务入口和模型密钥。启用配置后，仅已登录且在名单中的账号能取得十分钟任务凭证，单账号同时一个本机任务。桌面使用该凭证调用 `deepseek-flash`，服务端在既有预算控制登记、绑定并结算。切断连接、撤销或超时后关闭模型转发。任务描述和必要文件片段发给云端模型。客户端不会收到供应商密钥。

开发构建先执行 `npm --prefix apps/desktop run runtime:stage`，然后使用现有 dev 入口。Windows x64 的 `pack` 和 `dist` 将锁定的 Harness 运行时封入 `resources/geneloop-runtime.asar`，Windows 原生模块和外部工具保存在相邻的 `.asar.unpacked` 目录。桌面界面仍来自本仓库。用 `npm --prefix apps/desktop run smoke:local-workspace` 运行回环诊断，或运行 `node apps/desktop/scripts/probe-local-runtime.mjs --installed "<安装目录>"` 验证实际安装中的 Agent 和文件工具。真实云端模型验收使用隔离服务和试用账号，并核对预算账本、产物、取消与重复提交。

## Windows PPT 导出开发入口

`scenarios/ppt_master/windows_delivery.py` 处理宿主批准的、已完成的静态 Generate 项目。读取 `spec_lock.md`、`svg_output/*.svg` 和逐页同名 `notes/*.md`。它在独立临时目录执行 ppt-master 6.6.0 的校验和导出，再调用既有的 LibreOffice 交付验收。通过后一次发布 PPTX、PDF、逐页 PNG 和含 SHA-256 的回执。输入项目保持原位。

开发环境使用已有的锁定 ppt-master 安装、Windows LibreOffice `soffice.com` 和安装了 PPT 场景依赖的 Python。输出路径必须是位于已有目录下的新目录。

开发版可通过绝对路径环境变量 `GENELOOP_PPT_PYTHON`、`GENELOOP_PPT_MASTER_ROOT`、`GENELOOP_PPT_SOFFICE` 将同一导出器接入本机对话。PPT Agent 提供规格、静态 SVG 和逐页备注，交付可编辑 PPTX、PDF 和验收回执。转换进程使用 Windows Job 随任务取消。Windows 预览包可随包安装 Python、锁定的 ppt-master、LibreOffice 与 FFmpeg。构建前分别设置 `GENELOOP_DESKTOP_PYTHON_ROOT`、`GENELOOP_PPT_MASTER_ROOT`、`GENELOOP_DESKTOP_LIBREOFFICE_ROOT` 和 `GENELOOP_FFMPEG_DIRECTORY` 指向经核对的工具，再运行 `npm --prefix apps/desktop run tools:stage` 与 `npm run desktop:build`。工具文件夹和安装包保存在本机。

```powershell
python -m scenarios.ppt_master.windows_delivery --project <项目> --output <新输出目录> --ppt-master <锁定工具目录> --soffice <soffice.com路径>
```

PPTX 模板工作流读取含 `{{FIELD}}` 文字字段的页面，只修改副本对应的文字段。母版、布局、主题和其余 ZIP 部件按原字节保留。PPTX 和 PDF 按页核对文字并保存源文件摘要。PDF、PPTX 按页读取，DOCX、文本和 CSV/TSV 按段提取。未标记的任意模板改版和源图表、图像提取不在此入口。静态 SVG 导出限 ASCII 页文件名、自包含形状与文本、1–30 页。

## 使用与基线

- 默认连接 `https://geneloop.ai/`，使用同一个服务器账号、工作区和会话。桌面与浏览器分别保存登录Cookie，不复制服务器密钥或私有部署配置。
- Chat、PPT、论文校对、数据分析、文件管理、视频编辑从服务器目录读取；服务器不可用的场景保持不可用。界面入口齐全不等于六个场景均已通过真实任务验收。
- 场景选择按本轮发送序列化为服务器公开的斜杠命令，成功后回到Chat；模型选择保存成功后才提交消息，不截断正文。
- 选中文件只上传副本；服务器产物通过同一账号认证预览/下载。写操作请求需要明确确认，客户端不自动允许。关闭客户端不取消服务器任务；停止由显式操作发往服务器。
- Windows关闭窗口隐藏到托盘；应用菜单或托盘的“退出”结束应用。保留32px应用/编辑菜单和主题联动，没有顶部黑色状态条。`Ctrl+,` 修改连接，`Ctrl+R` 重连；重连读取状态，不自动重发。
- 设置包含主题、已归档、最近删除、账户与安全。清空最近删除先核对列表并明确确认；服务器继续负责归属、修订版本和忙碌状态校验。
- 本次没有修改用户安装、正式服务、账号资料或累计账本。安装包未签名，没有自动更新；目前只构建与诊断Windows x64。

用户指定的旧基线为 **0.1.5顶部黑条修复版**，标签 `geneloop-desktop-v0.1.5-baseline`、分支 `codex/geneloop-desktop-baseline`，commit `15af73e`。它仍打包整套网页客户端，仅作回退/对照。本次在 `codex/geneloop-desktop-independent-ui` 单独开发，冻结工作区不改动。

## 代码与接口

- `src/main.ts`、`workspace.ts`：桌面窗口、菜单、托盘、下载、生命周期；退出时先释放子视图和连接，再销毁窗口。
- `ui/desktop/index.html`、`desktop.css`：桌面自己的布局和视觉。
- `ui/desktop/api.js`：公开JSON RPC和WebSocket mux传输；`conversation.js`：日志/流式状态；`composer.js`：逐轮场景与附件序列化。
- `ui/desktop/app.js`、`components.js`、`comparison.js`、`panels.js`：桌面会话、场景选项、安全Markdown、双路结果、交付、问题和设置。没有复制网页组件实现，也没有另造Agent循环。
- `src/frontend.ts`：本地资源白名单，仅 `/api/` 转发至服务器；不获取整站HTML、boot JSON、插件脚本或未知UI。生产依赖为空，Electron自带运行时即可启动。
- `scripts/prepare-assets.mjs`：只复用透明品牌SVG并生成图标；manifest记录代码版本、是否未提交、独立资源摘要和公共场景目录。

保留原服务HTTPS origin、HttpOnly Cookie、原生WebSocket和来源校验。Electron的 `protocol.handle` 不携带普通请求Origin时，只按Chromium可信 `initiatorOrigin` 恢复同源Origin；跨源、不透明源、伪造头或无来源写请求被拒绝。不关闭Web安全/证书验证。

工作区无Node和窗口控制桥；外观preload只观察颜色，主进程校验当前同源主frame与hex颜色值。连接页面的窗口IPC只对安装包内主frame开放。安装器保留准确exe名查询，不按目录前缀匹配，也不强制结束用户进程。

## 开发和诊断

```powershell
npm --prefix apps/desktop ci
npm --prefix apps/desktop run dev
npm --prefix apps/desktop run check
npm --prefix apps/desktop run smoke:account
npm --prefix apps/desktop run smoke:renderer
npm --prefix apps/desktop run smoke -- --public
npm --prefix apps/desktop run dist -- --config.electronDist=node_modules/electron/dist
npm --prefix apps/desktop run smoke:packaged
```

`check` 验证传输与权限边界、日志投影和逐轮发送。`smoke:account` 使用原网关和本机临时合成账号，验证独立表单、密码拒绝、Cookie、刷新和退出；该夹具不启动Agent工作空间。`smoke:renderer` 使用确定性协议夹具验证双路结果、权限确认、人类问答、场景/模型保存顺序、文件预览及设置，不作为模型行为验收。`smoke` 启动原项目隔离mock Host，验证原生工作区/会话/RPC、上传与重连，**不发送模型任务**；`--public` 只读检查正式站未登录账号状态。

`smoke:packaged` 检查ASAR不含网页/生产Node依赖，再把整个应用复制到祖先无node_modules的临时目录运行；只读取公开未登录账号状态，不执行安装/卸载。诊断数据、截图和失败保存在 `apps/desktop/.local/validation/`，不提交。

上述测试均不证明真实模型效果。正式账号、六场景真实交付、评分/归档/清空/改密等服务器持久操作仍需隔离账号验收；不通过读取用户密码、复制浏览器Cookie或模拟回复补齐。本机Agent/工具执行属于下一阶段，模型仍可通过网络调用云服务。

当前版本与证据见[桌面交接](../../handoffs/desktop.md)和[独立前端记录](../../debug/geneloop-desktop-independent-20261103.md)。

## macOS 构建候选与 Windows 本机 Remotion

本机工具构建另需 `GENELOOP_DESKTOP_BROWSER` 指向 Remotion `ensureBrowser()` 准备的配套浏览器。纯 JS 封入运行时 ASAR，原生 compositor、esbuild、FFmpeg、Office、Python 和浏览器保留实体文件。包内 `manifest.json` 记录平台、架构、浏览器摘要和 ppt-master 锁。Windows 本机复杂渲染使用 Chromium 渲染沙箱，固定工具进程由 DSH 管理取消，不能将其称为全面文件/网络隔离。

Mac 在目标平台原生执行 `node scripts/prepare-macos-tools.mjs`（工作目录 `apps/desktop`），再运行 `npm run dist`。它获取固定版本与校验和的便携 Python/LibreOffice，验证锁定 ppt-master，并准备配套 Chromium 和 Remotion 原生组件；输出 ARM64 或 x64 的 DMG/ZIP。`.github/workflows/desktop-native.yml` 在两类 Mac 构建机上运行原生文件、PPT/PDF、实际 Remotion、取消及 ASAR 检查；没有安装包上传步骤。2026-11-06 两种架构的原生与包内检查均已通过；最终复验采用 `.app` 模式，前一轮候选的 DMG/ZIP 构建成功不替代最终版本的安装验收。尚未完成 Apple Developer 签名、公证、人工界面与 Mac 真实模型场景验收。六个 Windows 合成小任务的真实模型证据见 [preview.11 记录](experiments/desktop-preview11-20261106.md)。

ppt-master 构建来源固定为上游提交 `440557b8dc7c7257b69c04a0b014d5c50a78e6cb` 的 `skills/ppt-master/` 子目录，逐字节保持既有 13,016 文件锁；仓库根目录和同名版本标签不能替代该安装来源。Mac 的 FFmpeg/FFprobe 及相邻动态库在构建时重定位为 `@loader_path` 并恢复 ad-hoc 签名，避免依赖当前工作目录。系统动态库路径保留。该签名不是 Apple Developer 签名或公证。

Mac 包内的 Agent 启动与工具探针使用 `node scripts/probe-local-runtime.mjs --installed "<GeneLoop Desktop.app 路径>"`，Windows 使用同一入口并传入安装目录。探针启动真实 DSH SDK、读取/搜索文本、写报告、拒绝越界访问、取消等待及正常关闭；模型响应来自回环协议夹具，真实模型请求为零。手动 Mac CI 可选择 `app` 模式，只生成 `.app` 并执行包内检查；`installers` 模式继续生成 DMG/ZIP，两种模式都不上传安装包。

## preview.13 原场景 MCP 工具

在 preview.12 基础上复用原 MCP 工具目录和校验，接入统计报告、引用证据与审校 PDF、文件预览/确认/恢复、PPT 模板与源材料、Office 交付/恢复以及原生 Remotion。通用代码改用 QuickJS WASM，固定中英文 OCR 数据随包提供。全部仍由 DSH Agent 和工具生命周期管理，实际执行不要求 WSL。源文件进入明确授权的任务快照，结果回到工作区「GeneLoop 输出」。

文件整理目前作用于副本并交付 ZIP，工作区原件不被移动或删除；模型的长时上下文与本轮临时 MCP 句柄也需区分，跨任务重开时重新固定来源。原工具 Schema 已接入不等于所有文档质量、平台认证或真实模型验收通过。当前证据见[完整工具适配记录](../../debug/desktop-preview13-full-tools-20261106.md)。

## preview.12 跨平台场景工具

| 场景 | 本轮补齐能力 |
| --- | --- |
| 通用对话 | 与其他五场景共用来源固定及 PDF、PPTX、DOCX、XLSX、JSON、TeX/BibTeX、文本分页读取 |
| 文件管理 | 根据明确来源版本与目标目录名称，将文件副本整理为 ZIP，并交付来源回执；保留原件 |
| 数据分析 | CSV/TSV、XLSX、JSON、PDF/DOCX/文本显式表格的选择、统计、Pearson 相关和 CSV 副本导出；复用网页 DatasetEvidence |
| 论文材料核验 | 多文件 LaTeX input/include、缺失/重复引用键、重复 label 与浮动位置静态检查；复用原 paper_static_checks，不执行任意 TeX |
| 演示文稿 | 读取普通 PPTX 文本框 ID/文字摘要，修改副本，不要求预加 {{FIELD}}；保留未改部件、位置、母版主题，交付 PPTX/PDF |
| 视频编辑 | Windows 沿用原生 FFmpeg 时间线；Mac 将同一片段计划交给随包 Remotion 裁剪拼接，复杂合成仍在本机 |

依赖复用现有 Python、Office 和媒体包，没有再引入一套 Agent 执行器或新增 Python 库。新增 CSV/ZIP 产物仍经原生目录句柄发布，只允许生成的文件名由界面打开。CSV 对公式样文字进行显式转义，含公式的工作簿不作为统计观察值使用。

`node scripts/check-native-scenes.mjs` 是新增工具的无模型定向检查；可用 `GENELOOP_NATIVE_RUNTIME` / `GENELOOP_NATIVE_TOOLS` 指向实际应用包。与实际模型行为、人审质量、网页全工具等价及 Motif 重新认证分别验收。普通模板编辑使用原文本首段样式，不承诺复杂逐字富文本完全保真。

资源包拆分尚未实施。当前仍为离线工具随包分发；用户讨论的主应用与按需下载工具包属于后续交付方式，六场景入口和技能不需要改成外部插件。正式网关须同步本轮源码才能声明新版工具协议；旧网关保持原能力，不擅自发布正式服务。
