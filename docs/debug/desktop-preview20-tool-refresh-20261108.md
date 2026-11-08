# preview.20：按六场景实现清理工具与三平台包体计量

## 范围与结论

2026-11-08，基于[逐场景交叉核对](desktop-scene-scope-review-20261108.md)更新桌面工具。核对基线 `origin/main=1d1e16f4bde7f980127a53ead305e0e5d8b08b86`，本地分支 `codex/desktop-local-runtime`；功能提交 `dfceea73`、`4f238283`，后续追加构建守卫、缓存排除和本记录。三份新候选版本均为 `0.3.0-preview.20`。旧 preview.19 安装器、工具源、用户安装实例和账号数据保留；没有改正式服务、Motif 或隐私内核。

本轮更新的是已确认的产品范围，不把上游 Skill 的所有可选脚本都当作产品功能。六场景仍在；PPT 仅制作、编辑和核验。没有新增论文 TeX 编译、自动投稿、视频 ASR 或独立语音服务器。

## 实际增删与适配

- **删除新分发中的语音扩展**：不再生成 speech 包，不分发 Torch、Whisper、stable-ts、edge-tts。仅清理 edge-tts 独占的传递依赖；保留仍被其他根依赖使用的包及不能据元数据断言无用的可选绘图组件。不清空旧缓存或旧安装。
- **替换完整 Office**：三平台使用固定的官方 `@deepseek-ai/libreoffice-kit@0.2.3` native Kit，复用桌面宿主，不再捆绑重复 WASM／Node。Windows 源 Office 从约 830.5 MB 降至 215.4 MB，压缩分包约 49.9 MB。DOCX／PPTX／XLSX 转 PDF、模板图片和字体仍检查；独立 RTF 导入按已确认范围拒绝，模板内嵌矢量图不以删扩展名方式裁掉。构建回退需显式 `GENELOOP_DESKTOP_OFFICE_ENGINE=libreoffice`。
- **共享运行文件**：Python Playwright 使用可信的桌面 Node 宿主，删除独立 driver Node；仍保留 driver JS、许可及与 Remotion 共享的 Chromium。构建准备浏览器时也绑定当前 Node，不依赖用户全局安装。
- **补齐制作入口**：新工具集带 `skills/geneloop-ppt/SKILL.md`，保持锁定 PPT Master 引擎、源材料／模板／字体／页面预览与可编辑 PPTX。旧七包不得给新运行时冒充当前工具集。
- **清理生成物并保留真实运行依赖**：不分发机器相关 `__pycache__`、`.pyc/.pyo` 和一般测试夹具；保留 NumPy 2 正常导入必需的 `numpy/_core/tests/_natype.py`。Python 包按实际依赖关系清理，不能仅凭目录名 `tests` 删除。
- **其他场景按原实现保留**：Data 的 NumPy／Pandas／SciPy／Statsmodels／绘图／报告；Paper 静态核验与审校 PDF；Files 的中英文 OCR、确认／整理／恢复；Chat 的 DSH 公共工具；Video 的 FFmpeg／Remotion／浏览器／音轨和给定文字字幕。

`stage-desktop-tools.mjs` 支持独立输出目录和浏览器缓存根；原默认入口不变。`python-tool-profile.py` 在构建时验证依赖版本与闭包。小包与完整离线构建均检查当前范围；缺少 GeneLoop Skill、必要 NumPy 文件、默认 Office Kit，或混入 speech／重复 Playwright Node 时拒绝构建。

## 最终实测大小

下表单位 MB=1,000,000 字节、GB=1,000,000,000 字节，均来自最终安装器和压缩资产的实际长度。安装器本身不包含六个外置工具包；“合计”是安装器加全部工具下载量。工具展开量不包含应用本体，也不是完整安装耗时。

| 平台 | 安装器 MB | 六工具包 MB | 合计 MB | 工具展开 GB | 工具文件数 | 对比 preview.19 工具下载减少 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Windows x64 | 267.906048 | 322.160334 | 590.066382 | 1.431327174 | 25,666 | 66.89% |
| macOS Apple Silicon | 230.173120 | 257.111435 | 487.284555 | 1.202509823 | 26,220 | 63.53% |
| macOS Intel | 240.517369 | 299.435134 | 539.952503 | 1.227972448 | 26,219 | 63.58% |

旧版三平台工具下载分别为 972,928,702／704,970,088／822,284,521 字节，展开分别为 5,926,334,762／3,024,521,824／3,314,884,424 字节。保留旧固定清单，不改写历史数字。

最终 toolset ID：

- Windows：`e7667b8fc863e4efb820cf440ee087e7cd464295545509e0610e957349a8191f`
- Apple Silicon：`e7501f7addace900aadcab91fc9719b43d434e7b2db99bcdc393aabeb786fdc6`
- Intel：`6fec674c7143bd4dc0dabc16ae60d41903ee70bb952f3aba2c66a8a1f96b5dde`

安装器 SHA-256：

- Windows：`10bd77666aea7b2a59d8ee9a4dcc5040a556c3031c443a1be22fbf93876accc3`
- Apple Silicon：`08350bd4a53c26a126ed835a4cbd5ec65dbd903e910c1f6cb52d4f980a928056`
- Intel：`892fdcc39976925e81765e4fc2bb7417b52bb5bf2f0a7650cbc90bb7bb84ed64`

## 简单验证、失败与边界

- Windows 最终小包内真实 Electron 宿主从本机分包完整恢复 6 包／25,666 文件，逐文件 SHA 匹配；导入／解压／校验 82.691 秒。**不包含基础安装和下载，不能写成覆盖安装用时。**
- Windows 恢复后的核心 MCP 检查通过：Data 输入核对、Paper 取证／审校 PDF、Files 副本、Management 确认／执行／恢复、来源变化与外部硬链接拒绝、受限代码和动态 Gateway。对应目录计数为 Paper20／General4／Data17／Files13／PPT21／Management27／Workspace2／Revision4／Gateway5；不是同等数量的真实模型任务。
- 三种原生环境的可选依赖检查通过，包含实际 NumPy／SciPy／Statsmodels 回归计算、旧 Office 文档转换、Pandoc、SVG 光栅回退、共享 Chromium 实际截图、分词缓存、FFmpeg 音频滤镜、PPT 无语音依赖、私有 Provider 凭证分离。
- 三平台实际 PPT 模板修改／PPTX／PDF 交付通过，含保留模板原件、字体校准、嵌入图片与备注。桌面编译及原 14 项检查通过。
- **保留负面证据**：首批候选错误裁掉 NumPy `_natype.py`，导致 SciPy／Statsmodels 导入和 Data Provider 失败；未采用该批计量或产物作为最终交付。恢复此文件、增加实际统计导入与回归检查后，重新生成 Windows 工具与安装器，并重跑两种 Mac 构建。另修复删库后残留空 namespace 目录、测试生成缓存回流压缩包的问题。
- 没有为包体修改再跑六场景模型效果：本轮真实模型请求 0。此前全仓 `npm test` 被本机 Anaconda Pillow `_imaging` DLL 收集错误阻断，不能报告全仓通过。本轮不以重复付费测试代替依赖检查。

Mac 最终 [run 42405018864](https://github.com/Asilences/GeneLoop-Desktop-Build/actions/runs/42405018864) 使用构建源码 `7cd6d5e00b1e6eaa44722783348c950f91102c66`，对应本地功能提交 `4f238283`；Apple Silicon／Intel 均成功。前一 run `42402429960` 的候选保留为 NumPy 误裁诊断。Mac 仅公开标准免费 runner，没有启用付费 runner；历史额度账本与失败记录保留。

## 本地交付与接手

私有交付根：`.local/desktop-releases/0.3.0-preview.20/`，各平台目录放安装器和 `tools/`，总目录含 `delivery-manifest.json`、`SHA256SUMS.txt` 和使用说明。构建记录在桌面工作区 `.local/desktop-tool-refresh-20261108/`；旧版和失败日志保留。新六包未发布公开下载源，清单 `baseUrl=null`，试用须在工具准备页“从本机导入”对应 `tools` 目录，不能套用旧七包 URL。

Mac 仅按已有授权临时中转安装器及工具产物，取回校验后删除两轮全部远端产物；Actions 恢复原关闭，默认分支和安全允许列表不变。没有发布安装包 Release，没有更新正式仓库分支／PR或服务；必要源码仅同步构建镜像。

下一步可用本地候选进行用户试用。Mac 未 Apple 签名／公证、未人工安装 UAT；本轮未重测完整系统安装／覆盖耗时，不能由压缩大小推断实际安装加速。新的在线工具下载发布与正式账号模型网关仍分别记录，不把本地工具检查当正式部署。
