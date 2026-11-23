# preview.25 分形品牌适配

- 基线：preview.24，`437cddbc081b926621f406af776ed8ad11ebcd40`；本地注释标签 `geneloop-desktop-v0.3.0-preview.24-baseline`。源码 ZIP 和 SHA 清单保存在私有 `.local/desktop-freezes/0.3.0-preview.24/`，原 Windows、Apple Silicon、Intel 安装包和验证记录完整保留。标签未推送。
- 设计来源：`codex/fractal-website` / `a5a044c15c99fcdf3c1130036faf4f6de6e932d7`。该分支是静态官网；本轮按其最终设计规范适配桌面，不合并官网站点，不修改网页聊天或 main。
- 改动：分形 G 与大写字标、冷白／墨黑／朱红体系、IBM Plex Sans／Mono 与 Noto Sans SC 随包字体，覆盖登录／加载、对话、工作区、只读 Motif 展示、设置、原生窗口和紧凑 Windows 安装器。深色是同一品牌的桌面延展，非官网已有深色页面。字体保留原 OFL，来源见 `apps/desktop/brand/PROVENANCE.md`。
- 保留：现有菜单、圆角控件、工作区树、草稿、主输入框本机执行、场景及工具资源调度；不引入官网首屏尺寸或动画。Motif／隐私算法、共享同意、网关授权和 DSH 执行器均未改。
- 本地资源：字体只允许固定的 `/desktop/brand/<font>` 名称；CSP 仅增加 `font-src 'self'`，未知文件、跨源字体仍拒绝，无 CDN 或远程网页依赖。
- 已验证：Windows 正常桌面环境 `npm run check` 14/14；`npm run smoke:renderer` 22 项通过、控制台 0 错误，实际 Electron 加载随包字体，深浅登录、设置、窄窗口及左右栏检查通过。受限环境的第一次检查为 13/14，设置临时文件替换 EPERM；正常环境重跑 14/14，不修改安全检查。
- 验证类型：本地协议／渲染诊断，模型请求 0，不是新的六场景真实模型质量验收。没有覆盖用户安装或修改账号。
- 已交付：Windows 完整 EXE `766676480` 字节，SHA256 `067c47c11e07f0618f25ca2c540a612a812cd60e52572db8ed63748641b1c610`；私有交付目录 `.local/desktop-releases/0.3.0-preview.25/windows/`（外层仓库）。应用源码 `104250ab2d4457ff79f636489ff63e63e400786b`，源码与标签均未推送团队分支，安装包未上传。
- 包内核对：实际 ASAR 的新样式、字体及外观模块与源码一致，7 个 Runtime 入口逐 SHA 一致；`25826` 个工具文件、`1432913211` 字节与 preview.24 逐项、逐 SHA 完全相同。工具完整随包，不增加安装后统一准备。三款字体原文件总计 `18445124` 字节，新安装包较冻结版增加 `11394048` 字节。
- 最终安装器 `--check-ui` 通过；轻量诊断与实际同源 C# 窗口的安装／设置／进行中／完成四态渲染通过，均固定540×360。仅执行界面检查，未实际安装、重测安装耗时或改用户账号。结果和截图保存在私有 `.local/preview25-fractal/` 及交付目录的“预览”。
- Mac：自动审批未允许将本轮源码发往公开构建镜像；用户随后明确本轮只交付 Windows，Mac 暂不构建。未同步任何 preview.25 公开源码、启动 Actions 或产生 Mac 费用，原两种 preview.24 DMG 保留。
- 回退：重新检出冻结标签可恢复准确源码；按原官方安装流程使用私有目录保留的 preview.24 安装包。不得为回退清理账号或工具目录。
