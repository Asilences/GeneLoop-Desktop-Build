# 桌面精简 Office Kit 接入候选

- 日期：2026-11-08；分支 `codex/desktop-local-runtime`，基于 `bd518a11`。
- 用户范围：核对官方 DSH 的精简 Kit 并采用；允许取消独立 RTF、EMF、WMF 导入，保留 PPT 模板内部的矢量图片。六场景及其他工具不裁剪，安装包不上传。
- 状态：构建源码已接入；Windows 原生引擎与现有 PPT Master 链路已验证。**preview.19 三份安装器、公开工具包和正式服务均未变更；本轮没有新安装器。Mac 新 Kit 仍待 ARM64／Intel 原生验证。**

## 实现与边界

采用官方 [`@deepseek-ai/libreoffice-kit@0.2.3`](https://github.com/deepseek-ai/dsh-libreoffice-kit)，独立 `apps/desktop/office-kit/package-lock.json` 固定公共 npm 包与完整性摘要。构建时 `npm ci --ignore-scripts`，只分发目标平台 native 包；不携带重复 WASM 引擎，不为 Office 再复制一份 Node。第三方许可与包内说明保留。

`stage-office-kit.mjs` 在原 `libreoffice/` 工具位置生成适配器。Windows 使用 `program/soffice.com`，Mac 使用 `Contents/MacOS/soffice`；宿主通过 `GENELOOP_OFFICE_NODE` 提供自己的可信 Electron／Node 路径。沿用现有 Python PPT 校验、原生子进程管理、来源摘要及交付流程，没有新建 Agent 循环，也不向服务器转交文档渲染。

`tools:stage` 和 Mac 构建默认准备 Kit。显式构建回退可设置 `GENELOOP_DESKTOP_OFFICE_ENGINE=libreoffice`，继续使用原 `GENELOOP_DESKTOP_LIBREOFFICE_ROOT`；旧完整分发原样保留。直接 `tools:office` 替换已存在的完整 Office 时，将旧目录保留在工具目录之外；不覆盖已存在的 Kit 或回退目录。

独立 RTF 明确拒绝，提示另存 DOCX／TXT。独立 EMF／WMF 不成为上传读取入口；锁定 PPT Master 提取到模板内部的图片时，通过专用内部标记把原始图片封装成最小 PPTX，再由官方 native 引擎渲染 PNG。这样保留模板图形，避免携带完整桌面 Office 只为旧格式兼容。没有更改上游 Skill 字节锁或给未知图片伪造成功。

适配器仅兼容本项目已用的单文件转换参数，不声称复现 LibreOffice 的全部命令、宏、GUI 或 Microsoft Office 排版。其他 Skill／自由命令的新参数需明确适配，不能从本轮几个成功样本外推为全部选项兼容。

## 本轮验证

Windows x64，Node 24.19.0；实际桌面 Electron 45.2.1／Node 24.22.1；Kit 0.2.3 native。使用合成输入，无用户资料、无模型请求、无新费用、未启动 Mac Actions。

- 通过实际 `soffice.com` 转换 DOCX／PPTX／XLSX 为 PDF：约 3.010／2.423／2.105 秒，均一页；输入 SHA 保持。Excel `SUM(B2:B3)` 输出 5。
- PDF 文字层含中文、PPT 原副标题保留；实际 PNG 查看确认中文、配图完整。DOCX 提示缺少其声明的 Courier 字体，保留该提示，不声称任意字体完全一致。
- 自行生成的 EMF 与 WMF 经内嵌路径输出非空 PNG，实际查看确认蓝色图形与 EMF 文字存在。独立 RTF 返回明确错误。
- 锁定 Skill 的 ODT→DOCX→Markdown 源材料流程与 RTF 明确拒绝复验通过；初始合成 ODT 因缺少标准 manifest 被正确拒绝，补齐夹具后成功，没有放宽引擎校验。
- 既有 `check-native-ppt.mjs` 使用本轮渲染器及当前 sourceRoot 通过：填充模板、普通模板改写、原件保持、官方字体校准、位图嵌入、备注解析、PPTX／PDF 交付。此为真实原生工具诊断，不是模型质量评测。
- 实际已打包的 Electron 宿主通过适配器调用 Kit，成功生成 PPTX 的 PDF，native backend，无缺失字体。不是只验证开发用 Node。
- 桌面 TypeScript 及 14 项前端／宿主检查通过；初次使用受限临时目录发生 rename EPERM，改用本轮工作区临时目录后通过。
- 执行了 `npm test`，Anaconda Python 的 Pillow `_imaging` DLL 在收集 5 个现有测试模块时初始化失败，整仓测试未通过／未进入 Node 阶段；没有删除相关检查或据此报告全仓通过。直接原生工具检查在受限进程中曾遇到 `CreatePipe failed: 5`，在已授权的本机执行环境复验通过。

最短 PPT 回归：先通过 `npm run tools:office -- <新的工具构建目录>` 准备引擎，再在 `apps/desktop` 下设置 `GENELOOP_NATIVE_RUNTIME` 为当前 `runtime`、`GENELOOP_NATIVE_SOURCE_ROOT` 为当前仓库，`GENELOOP_NATIVE_SOFFICE` 为新适配器的绝对路径，运行 `node scripts/check-native-ppt.mjs`。Python、Skill 等其余工具继续来自原完整 `desktop-tools-bundle`。

## Windows 实测体积

| 项目 | preview.19 完整 Office | 本轮 native Kit |
| --- | ---: | ---: |
| 工具文件 | 9,127 | 1,731 |
| 解压后字节 | 830,503,188 | 215,374,417 |
| 7z 压缩字节 | 204,583,750 | 49,859,846 |

旧值来自已交付的 Windows 工具目录清单；新值来自实际 staging 和 7-Zip 26.02、LZMA2 64MiB、mx=7 压缩。分别约减少 74.1% 和 75.6%。这不是整个安装包体积，也不是首次安装／下载／覆盖安装耗时。新 7z SHA256：`cf9914409c0df9c3eb5f63d20456f3216ada3b10b21bc5609e6dd3a37787b8f2`。

私有合成输入、生成器、原生回执、PDF／PNG、初次失败及整仓日志位于 `.local/office-kit-compat-20261108/`。未修改用户已安装的应用、账号或文件。

## 下一步

Mac 两种架构运行同一工具回归后，才能把新 Kit 放入新一轮三个平台交付。新工具集摘要变化，不能沿用 preview.19 的公开下载地址冒充新版本；发布工具包与制作安装器须分别记录。旧 preview.19 安装器及对应七包继续作为回退。
