# preview.19 三平台分包与真实任务交付

范围：保留独立桌面界面、DSH Agent、六场景 MCP 和全部工具，补齐 Apple Silicon／Intel 小 DMG 与安装后七包工具下载。不改 Motif、隐私核心或正式服务。安装包只留本地；工具包获授权公开发布；Mac 安装包仅临时 Actions 中转后删除。

## 当前结果

Windows x64、Apple Silicon、Intel Mac 三份安装器已校验取回；三种原生环境各六条简单真实任务全部通过。

| 场景 | Windows x64 | Apple Silicon | Intel Mac |
| --- | --- | --- | --- |
| 通用对话 | 通过；1响应／9.745秒 | 通过；1响应／10.637秒 | 通过；1响应／17.158秒 |
| 文件管理 | 通过；3响应／9.15秒 | 通过；3响应／11.399秒 | 通过；3响应／31.036秒 |
| 数据分析 | 通过；5响应／18.083秒 | 通过；5响应／83.037秒 | 通过；6响应／68.23秒 |
| 论文材料核验 | 通过；6响应／27.031秒 | 通过；5响应／99.823秒 | 通过；5响应／40.269秒 |
| PPT 模板修改／PDF | 通过；3响应／85.552秒 | 通过；8响应／38.278秒 | 通过；20响应／225.64秒 |
| 真实 Remotion 视频 | 通过；2响应／21.617秒 | 通过；2响应／31.241秒 | 通过；7响应／137.467秒 |

模型使用 Kouri `https://api.kourichat.com/v1`／`deepseek-v4.1-flash`，逻辑模型 `deepseek-flash`，reasoning Off。Agent 和工具在各自原生机器，模型在云端。合成输入逐项 SHA 保持，真实调用要求实际工具名、报告内容和产物校验；不使用模拟 Provider。原件无变化不等于复杂任务已合格。

PPT 实际改写模板标题、保留副标题，输出 PPTX 和有效 PDF；Video 实际渲染1秒640×360 Remotion MP4，并由 ffprobe 和完整 ffmpeg 解码检查。Files／Data／Paper 检查实际原件与 Markdown 证据。未做复杂科研质量盲评、所有可选工具选项、私有 MCP 或 Motif 重新认证。

## 安装包与源码证据

- Windows：`GeneLoop-Desktop-0.3.0-preview.19-x64-Setup.exe`，269434368字节，SHA-256 `0e09369f50d3904def4a0904d31eccfe11d664b679d7cef6fd8020453f21eb46`；应用源码 `82e228627be3017a30e9403ee60ee15b979746be`。完整128文件／798217410字节载荷逐文件 SHA 核对通过，没有执行系统安装，不声称最终完整安装耗时。
- Mac arm64：`GeneLoop-Desktop-0.3.0-preview.19-macOS-arm64.dmg`，232680020字节，SHA-256 `facc08204ec56a2f736d0884455722dfb06dee92ca4ed90855ec7b92b220d0ac`；run `42382651502`。实际 DMG 已挂载检查、Applications 链接和 ASAR 比对通过；全新目录公开下载77077文件／704970088字节，七包全部准备就绪，用时136.753秒。
- Mac x64：`GeneLoop-Desktop-0.3.0-preview.19-macOS-x64.dmg`，242959579字节，SHA-256 `dfeac2febe6fffd28dd82d7d345d40aaff1277a1a832f688f308d06e0a622608`；run `42382930249`。实际 DMG 已挂载检查、Applications 链接和 ASAR 比对通过；全新目录公开下载74942文件／822284521字节，七包全部准备就绪，用时413.03秒。
- Windows 六场景 run `42377331780`、源码 `014715f5`，20个计量响应。最终交付提示措辞修订仅复验 Files，run `42378247851`、源码 `72c77835`，3响应／8.896秒；Agent 规范化代码 SHA `86ff3dcf54a74d98a1699d1fc97b28155a81c3062d42e95c8ea3cf603604f911` 与最终包一致。Mac 后续仅修订工具分包解压和复用，未重写 Agent 核心。
- 当前源码在构建仓库独立分支 `codex/desktop-macos-delivery-20261107`；正式 origin 桌面 PR／main 合并和正式服务部署不在本轮完成项。前版完整离线包、失败记录和现有用户安装均保留。

## 工具下载与复现

- [Windows 七个工具包](https://github.com/Asilences/GeneLoop-Desktop-Build/releases/tag/desktop-tools-win32-x64-21e5190b5076c9c28586e197)复用 preview.18 工具集，不删减或重复上传。
- [Mac arm64 七个工具包](https://github.com/Asilences/GeneLoop-Desktop-Build/releases/tag/desktop-tools-darwin-arm64-0.3.0-preview.19-42379985997-1)；固定 toolset `ed6725a960419745a462b1ab3da9b81e10d1c9b8dba97aad5a327b6a59e3b7f1`，只公开七个 `.7z`，没有安装包 Release。
- [Mac x64 七个工具包](https://github.com/Asilences/GeneLoop-Desktop-Build/releases/tag/desktop-tools-darwin-x64-0.3.0-preview.19-42379985997-1)；固定 toolset `dbb25dacbe29de212a624c6b7a820d40ac1a54c593e67808032748dd68dacb2b`，只公开七个 `.7z`，没有安装包 Release。
- `.github/workflows/desktop-macos-delivery.yml` 为唯一新增手动工作流；仅公开标准 `macos-15` ARM64／`macos-15-intel` x64／Windows runner。Mac job90分钟上限，复用归档后不重复构建完整工具；单架构归档<900MB，临时存储按现有活跃产物大小控制，及时取回删除。
- `check-packaged-tool-download.mjs` 从实际包内启动 ToolPackStore，在全新目录公开下载、解压、逐文件 SHA／权限／链接校验；`check-real-six-scenes.mjs` 从实际包内 Electron／Agent 发真实模型任务。工具源精确绑定见 `apps/desktop/tool-releases.json`；未匹配摘要不能套用旧工具地址。

## 失败与修复

- 最初误按官方 DeepSeek 地址检测用户的 Kouri Key，HTTP401且未发真实任务；用户确认后切换 Kouri。不扫描服务器私有配置或读取安全输入窗口原始输出。
- 首次本机 Files 生成报告后重复尝试 present，未完成记录保留。Runtime 明确本机产物工具已直接交付，仍继续完成尚未满足要求；Windows 六场景及最终 Files 复验通过。
- Windows run `42377123926` 的 PowerShell 打包参数解析失败，未运行模型任务；改用默认打包目录后通过。
- 原 Mac run `42375666415` 在 gh 发布子命令失败且未保留工具；日志不足以确认具体根因。新 run `42379985997` 先保存工具中转物，再经既有维护者通道逐包核对后发布，避免再次压缩。
- Mac run `42379985997` 原生 Office 解压失败，尚未调用模型。修订按固定清单排除归档中的链接，再自行恢复已验证的内部相对链接，拒绝链接目录下成员，不放宽 7-Zip 安全等级；后续复用同一工具归档进行实际原生验证。
- 桌面专项14/14、真实小归档／哈希拒绝／取消／HTTP续传6组通过。受限临时目录的 settings rename EPERM 留档，正常原生权限复验14/14通过。整仓历史失败见 preview.16，不声称全仓全绿。

## 费用、凭据与清理

所有本轮 Mac／Windows CI 采用公开标准免费计算，原私有免费额度15美元账本及累计记录不清零、不新增付费 runner。模型计量响应和 token 见下表；没有供应商账单，Kouri 实付未知，不能用历史 DeepSeek 费率冒充。计量响应也不等于包括重试的全部 HTTP 请求。平台不另加模型费用／请求／输入输出额度；每条诊断保留540秒取消时限。

| 平台／范围 | 计量响应 | 非缓存输入 token | 缓存读取 token | 输出 token | 总 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| win32 x64／六场景 | 20 | 137891 | 17890 | 4489 | 160270 |
| win32 x64／最终 Files 复验 | 3 | 21282 | 511 | 320 | 22113 |
| darwin arm64／六场景 | 24 | 134222 | 65917 | 5522 | 205661 |
| darwin x64／六场景 | 42 | 271143 | 144741 | 10329 | 426213 |

已核对：临时测试 Secret 副本删除并返回404；本轮临时安装包／任务摘要已取回校验并从 Actions 删除；Actions 恢复原关闭，默认分支和安全允许列表未变。用户原 Kouri Key 未撤销。

## 限制与下一步

Mac 未经 Apple 签名／公证，真人安装 UAT 未完成；公共 Mac 原生运行不等于人工设备体验验收。本轮使用临时测试模型凭据，未部署或验收正式 GeneLoop 账号的本机模型授权网关，线上部署现状须由维护者核对。简单六任务通过不能证明全部工具选项、复杂质量或 Motif 效果。下一步由用户试用三份本地安装器；发现具体失败后按对应原生环境复验。
