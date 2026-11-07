# preview.19 双架构 Mac 分包交付（准备中）

本轮目标是 Apple Silicon / Intel 的小 DMG、完整工具分包下载，以及 Windows / 两种 Mac 各六个简单真实模型任务。沿用独立桌面界面、DSH Agent、六场景 MCP 和 preview.18 下载器，不修改 Motif、隐私核心或正式服务。安装包只取回本地；工具包可以公开发布。Mac DMG 沿用户既有授权临时经过 Actions，取回后删除，不发布安装包 Release。

## 已实现

- 应用版本 `0.3.0-preview.19`；Windows 固定工具源仍是 preview.18 已验证的七包工具集，不重复上传或删减工具。
- `.github/workflows/desktop-macos-delivery.yml` 合并 `phase=build|real` 两阶段，公开仓库且固定 `macos-15` ARM64 / `macos-15-intel` x64 标准 runner；不提供私有／大型 runner 参数，单 job 60 分钟。
- 构建阶段从锁定原生依赖生成七包，目录保留全部工具文件及 Mac 内部相对链接。DMG 只含桌面与运行时，固定工具下载地址；发布脚本只允许清单中的七个 `.7z`，逐包 SHA 与 GitHub digest 相符后公开，不上传 DMG 到 Release。
- 使用实际打包 Electron，检查全新目录公开下载、解压、权限／链接及逐文件 SHA；全部七包准备后生成回执。再核对 DMG 可挂载、Applications 链接和应用 ASAR，临时中转限定 DMG、SHA 和必要清单／回执。
- 真实任务入口 `apps/desktop/scripts/check-real-six-scenes.mjs` 使用实际包内 Agent、当前完整工具集合及合成原件。Chat 算术、Files 实际读取与报告、Data 分组汇总、Paper 静态引用、PPT 已有模板局部修订及 PDF、Video 一秒真实 Remotion。记录计量响应、用量、工具调用、原件 SHA、产物 SHA；没有真实凭据即失败，不用模拟结果冒充。

## 已验证与当前限制

- 桌面专项 14/14 通过。受限临时目录曾导致设置文件 rename `EPERM`；在普通原生权限下原检查通过，保留前次失败，未删除有效检查。
- 新工作流完成 YAML 结构检查，发布／下载／真实任务脚本完成语法检查。这不等于 Mac 原生执行。
- Windows 实际候选可加载包内 Agent、PPT 依赖、工具目录和固定下载源；回执位于私有 `.local/mac19-delivery/windows-package-probe.json`。本地安装器 `.local/desktop-preview19-online/GeneLoop-Desktop-0.3.0-preview.19-x64-Setup.exe` 已生成，269,434,368 字节，SHA-256 `57fb23c489e4eeb65e05fb60862452aa41a691ef95fd0cd5df11c20c4b7f81d8`，应用源码 `53c5111896b63ca876569f95fc86bcf63a79f9f4`，sourceDirty=false。
- 安装器实际 ZIP 载荷隔离解压 13.419 秒，128 文件／798,217,023 字节逐文件 SHA 与打包原文件一致；没有执行系统安装。这是载荷解压时间，不是完整安装／覆盖安装耗时。安装器和回执均未上传。
- Mac 尚未启动：构建仓库 Actions 关闭。自动审批拒绝了启动脚本涉及的设置操作；已去掉默认分支名称和允许列表的修改，正在请求用户明确授权“仅登记一个手动工作流文件并临时启用，结束恢复关闭”。不能绕过审批通过其他进程启动。
- 真实模型验收尚未运行：此前一次性 Key 未保存，构建仓库未配置临时测试 Key。已请求用户选择本机安全输入或自行配置临时 Secret；不得扫描私有配置发现凭据。Key 不写源码、日志、安装包或产物，临时 Secret 验收后删除。
- 本轮新增 Mac 计算与模型费用均为 0；没有启动构建。已有免费额度账本保留，不清零。公开标准 runner 计算免费，仍需控制临时产物大小／期限并取回删除。
- 源码已同步构建仓库独立分支 `codex/desktop-macos-delivery-20261107`；尚未产生 preview.19 Mac DMG、Mac 工具 Release 或六场景真实任务通过结论。正式网关、Apple 签名／公证和真人 Mac 安装体验未验收。

## 接续

1. 用户确认后，保持构建仓库默认分支名称和 Actions 安全允许列表不变，只登记本手动工作流并临时启用；dispatch 独立分支的 build 阶段。记录源 SHA、run ID、两架构产物和工具 Release。
2. 用户安全提供临时测试凭据后，先验证实际模型可用，再进行 Windows 与两架构 Mac 各六个小任务；失败保留记录，只修复确切阻断后复验。模型 Flash / Off，不额外限制输入、输出或重置累计账本。
3. 取回 DMG 并验证 SHA；写入两种 Mac 的 `tool-releases.json` 精确绑定；删除本轮临时 Actions 产物与 Secret，空闲时恢复 Actions 原关闭状态，补齐交接和用户本地路径。

简单任务只能证明这些路径真实可执行，不能外推所有工具、复杂任务质量或人工 Mac UAT 全部通过。
