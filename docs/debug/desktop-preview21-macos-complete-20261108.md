# preview.21 Mac 完整离线 DMG 交付记录（2026-11-08）

Apple Silicon 和 Intel 的完整离线 DMG 均已生成、取回校验并保存在本地。与 Windows preview.21 相同，默认随应用提供当前六场景工具；打开 DMG 后拖入 Applications，无需再导入、下载或统一准备六工具包。

| 原生平台 | DMG 字节数 | 随包工具文件 | 核心 / PPT / 视频原生检查秒数 |
| --- | ---: | ---: | ---: |
| Apple Silicon / arm64 | 665,245,008 | 26,220 | 32.654 / 39.090 / 21.179 |
| Intel / x64 | 683,382,427 | 26,219 | 69.222 / 74.099 / 31.614 |

以上秒数是诊断运行时间，**不是 Mac 安装时间**。Windows 75.107 秒为之前本机实际覆盖安装测量，不外推到 Mac。

## 构建、工具与实际路径

- 本地打包源码 `c57e8bd7`；构建镜像源码 `4f687d07cc16ea1f6bf7f043b1c124f49c773484`。[唯一构建 run 42462829088](https://github.com/Asilences/GeneLoop-Desktop-Build/actions/runs/42462829088) 的 `macos-15` arm64 和 `macos-15-intel` x64 两个原生任务均成功。没有使用交叉构建替代目标架构运行。
- 复用 preview.20 已核对的当前六场景工具字节，构建阶段从用户已授权的公开工具源恢复；每个包及成员哈希校验，复制后再逐文件核对。两架构各保留全部文件，无缺项；PPT仍仅制作/编辑，不恢复语音依赖。工具版本和固定来源在 `apps/desktop/complete-tool-inputs/`。
- 工具位于 `GeneLoop Desktop.app/Contents/Resources/geneloop-tools`，完整包不包含 `tool-packs.json`，不会创建首次全量工具准备流程。构建恢复目录已在制作 DMG 前删除，避免依赖构建缓存冒充安装后可用。
- 挂载并校验实际 DMG，确认 Applications 链接；从镜像复制应用到独立路径，卸载镜像后，使用复制后应用内的 Electron、ASAR运行时、Python和工具运行检查。不是只检查打包前源码或工具目录。

## 已验证与边界

- 核心MCP检查通过，包含论文材料/本地引用证据及审校PDF、数据工作流、文件副本与管理确认/执行/恢复、受限代码、动态工具发现和安全拒绝；注册数不等于全部业务任务验收。
- PPT实际模板编辑、字体校准、PPTX/PDF导出、图片/备注与交付检查通过；视频实际Remotion渲染、剪辑/拼接、音轨、抽帧与全片解码检查通过。
- 两架构各17个可选Python依赖导入、NumPy/Pandas/SciPy/Statsmodels实际回归、Office旧文档转换/RTF明确拒绝、Pandoc、SVG栅格化、共享Chromium实际截图、离线tokenizer缓存、FFmpeg音频滤镜及私有Provider隔离诊断通过。
- 本轮模型请求0，不重跑复杂真实模型任务，不外推场景质量、费用收益或用户机器上的安装速度。Mac尚无人工安装/登录/中文输入/系统目录授权UAT，也未Apple签名或公证。
- 本地收集时，转换器会在最终JSON前打印成功提示；保留原始输出，提取最后JSON行并验证诊断类型和实际统计检查，不跳过任何工具检查。

## 本地交付与外部状态

- 三平台交付根 `.local/desktop-releases/0.3.0-preview.21/`；Mac分别在 `macos-arm64/` 和 `macos-x64/`，包含DMG、摘要、使用说明与回执。私有构建/取回/清理证据在桌面工作区 `.local/mac21-complete/`。
- 安装包没有发布Release。授权的公开Actions临时产物已取回、逐SHA核验并删除，本地临时ZIP副本也删除；最终DMG保留。仅六工具分包作为工具源公开发布。
- 仅使用公开标准免费Mac runner，新增计算预留0美元，不授权付费；历史预算账本保留。完成后Actions恢复原关闭，默认分支与安全允许列表不变。正式网关、账号数据、Motif/隐私核心未改。
