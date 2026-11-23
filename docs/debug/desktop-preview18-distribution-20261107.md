# preview.18 分发体积与安装界面

- 范围：桌面分发与安装体验；保留 preview.17 的六场景、DSH Agent 和完整工具文件。未改服务器、Motif 或隐私核心。最初安装包、工具包均不上传；用户随后明确授权仅发布七个工具包，安装包继续留在本机。
- 原因：preview.17 完整 EXE 为 2,047,067,136 字节，载荷 6,712,732,026 字节／61,806 文件。新增离线字幕对齐包含 CPU Torch 和 Whisper 权重，语音目录约 3.68 GB；旧 ZIP 内约 910 MB。下载包变大不等于业务代码变大。
- 用户调整：大工具改为安装后统一准备。基础应用与工具分别分发，不用删工具缩包；全部工具准备完成后的内容以原 preview.17 已验证工具目录逐文件 SHA-256 为准。首次准备仍有下载、解压和校验耗时，不将其隐去或宣称为整体安装提速。

## 实现

`build-tool-packs.mjs` 将原工具目录无损分成场景材料、Python、Office、浏览器、音视频、格式转换、离线语音七包，固定 7-Zip 26.02／LZMA2，256 MiB 固实块。未知文件未分配会停止构建；分包不裁剪测试之外的新文件，不裁掉运行依赖。`preservation.json` 记录原文件数、包内文件数和完整大小；`tool-packs.json` 记录平台、架构、包／文件摘要及版本。

`GENELOOP_DESKTOP_TOOL_PACKS=1` 开启小包，`GENELOOP_TOOL_PACK_OUTPUT` 指定生成目录；未开启时保留完整离线包构建。原安装事务、安全 ZIP 解压、同盘回退、进程检测与启动权限链保持。工具解码器作为签名／发布载荷的一部分，来源与下载摘要在 `installer-codec-lock.json` 固定；许可随包提供。Windows 解码器 x64，Mac 使用官方通用 7zz；本轮不据 Windows 检查宣称新 Mac 分发已验收。

首次启动及「文件 → 本机工具」打开统一准备页。支持 HTTPS 下载、按字节续传、暂停、失败重试、本机目录导入；完整包摘要匹配后才解压，再核对每个文件和权限，成功后切换到版本目录。当前用户工具保存在应用数据目录，不混进应用覆盖安装事务。模型调用方式不变；工具未就绪会提示，不自动改成云端执行。语音包用于字幕时间轴对齐，普通裁剪、拼接不依赖它。

在线源只接受无凭证 HTTPS 地址。无发布绑定的候选明确说明未配置在线源并提供本机导入，不向不存在的服务请求，也不要求用户填写地址。2026-11-07 用户明确授权“允许，仅发布工具包”后，将对应 Windows 工具集固定在 `tool-releases.json`，构建工具集完整摘要相符时自动写入；构建者仍可通过 `GENELOOP_TOOL_PACK_BASE_URL` 指定自己的发布地址。不将原临时 Actions 中转授权解释成长期发布授权，未获得本轮授权前没有公开这些资产。

## 安装界面

保留原生 WPF 和 NSIS 生命周期，借鉴 [ModernWpf](https://github.com/Kinnara/ModernWpf) 的 Fluent 层次与 [WixSharp](https://github.com/oleg-shilo/wixsharp) 的界面／引擎分离；没有为界面额外引入 .NET 8 或 WebView。左侧为 GeneLoop 的研究节点图，右侧为路径和主操作卡；路径始终可改，自定义设置可折叠，完成后默认勾选打开应用。`--render-ui ready|options|installing|complete <PNG>` 只离屏渲染，`--check-ui` 不安装或提权。

分发参考 [DSH packaging](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/packaging/README.md) 的生产依赖闭包、可选 provider 分离与平台压缩；不是复制 DSH 界面或执行器。原生压缩器版本／来源见 [7-Zip 26.02](https://github.com/ip7z/7zip/releases/tag/26.02)。

## 验证与边界

- 新增分包诊断使用真实 7-Zip 和回环 HTTP：中文与二进制逐字节还原、重启识别、完整 partial 文件恢复、实际暂停／Range 续传、错误摘要拒绝、目录越界拒绝。`node apps/desktop/scripts/check-tool-packs.mjs`，无模型调用。
- 桌面类型编译与 14 项前端／设置检查通过。受限临时目录首轮 EPERM 保留；在实际 Windows 临时目录复验通过。
- 原安装载荷与事务诊断通过。新的 WPF 四种状态已实际离屏渲染；未覆盖用户安装，不用局部解压时间冒充完整覆盖耗时。
- 完整恢复 61,681 文件／5,926,334,762 字节，包合计 972,928,702 字节。隔离目录本机导入、解压、逐文件摘要核验共 187.965 秒；不含网络下载和基础应用安装。语音包为 448,467,729 字节。恢复后同一个 `check-native-extras.py` 的 10 组检查通过，包含 18 项依赖导入、真实文档转换、浏览器截图、媒体滤镜和离线 Whisper 权重加载，模型 API 0。
- 首轮特意使用深目录时触发 Windows MAX_PATH，Python schema 读取失败；将版本路径从 64 位十六进制缩短为 24 位，完整摘要仍在目录清单和完成标记中核对。实际检查使用与应用数据目录长度相当的隔离短目录，不把移动成功当工具通过；原失败记录保留。
- 初始无在线源小包为 269,434,368 字节，SHA-256 `c38730ea27c84d3738c73d5fd63cae7d5197d2bb0276e19a74b339204a861543`，应用源码 `7c812a2d`；完整清单及工具摘要在私有交付回执中。全部分包加应用合计约 1.24 GB，对应旧完整 EXE 约 2.05 GB；不把只比较基础包当作全部下载体积的节省。
- 基础载荷 128 文件／798,216,905 字节；在本机缓存、本地隔离路径下安全解压 5.192 秒，所有文件与预打包目录 SHA 一致，不含提权、旧版清理和注册。过深的诊断目录先被原 Windows 路径守卫拒绝，未放松保护；使用标准长度隔离目录后通过。最终四状态界面、短工具目录与清单均核对为实际包内版本。
- 实际包内 DSH Agent 启动、隔离读写、取消与退出通过：3 次回环协议请求、0 次真实模型请求。这是分发回归，不是模型效果验收。新包留在 `.local/desktop-preview18-small/`，工具分包位于 `.local/desktop-preview18-tool-packs/`；原包保留。
- 未覆盖用户安装，因此没有新版本完整覆盖耗时。未启动 Mac Actions，未重新做模型效果实验。

私有证据：`.local/desktop-installer-compression-ui-20261107/`；原完整候选 `.local/desktop-preview17-complete/` 保留。

## 获授权的工具发布与真实下载

- 公开位置：[Windows x64 工具集](https://github.com/Asilences/GeneLoop-Desktop-Build/releases/tag/desktop-tools-win32-x64-21e5190b5076c9c28586e197)，Release ID `437558935`。先建立草稿，七包全部上传且远端字节／SHA-256 与固定清单相符后才公开。发布后复查恰好七个 `.7z` 资产，没有安装包、应用压缩包或诊断材料；Actions 全程保持关闭。
- 真实 Windows Electron 隔离准备页匿名下载约 21 MB 的场景材料工具包，实际暂停后从 163,139 字节续传，远端返回 HTTP 206，完整包与 13,761 个文件全部校验后就绪。总计 109.443 秒，包含网络、一次中断／续传、解压与校验；不将其外推成全部工具的下载耗时。没有使用测试账号、登录 Cookie 或模型 API。
- 工具二进制与前轮完整恢复相同，不重复下载全部约 973 MB 做形式检查；其余六包的远端完整摘要已逐项核对。无新增模型行为、Mac CI 或正式服务操作。
- 新本地安装器位于 `.local/desktop-preview18-online/`，应用源码 `4aa79a48`，269,434,368 字节，SHA-256 `7053f5d46aa0a9d3ba9c067062ae807990f8ebe40db3c02f6de29ea7d8445660`；原无在线源候选及完整离线候选保留。新载荷已核对固定公开目录与未变的 Runtime／原生文件，完整覆盖安装耗时仍未实测。最终文件摘要见 `.local/desktop-tool-release-20261107/delivery-online-receipt.json`。
