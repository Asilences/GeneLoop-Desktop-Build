# preview.27 三种 Motif 卡片与独立详情窗

## 当前行为

鱼缸、A结构演化、B能力分布均保留，收起偏好独立保存。三卡的右上角斜箭头打开居中详情窗，可放大/还原；右侧工作区栏仍绑定当前任务。原工作区、对话、权限和本机执行路径不变。

大鱼缸只按实际能力生成节点；悬浮、键盘聚焦和点击显示所选资料，支持搜索和每页48项。A/B共用当前来源的总数、四种认证状态和逐项资料，真实内部结构只读取已有工具流。未知数量显示未知，不冒充0；有数据但为空才显示0。

当前v1/v2投影没有结构层级或Motif组合谱系，实际视图单列未分层。详情可切换独立的8项层级示例，明确标记非工作区结果；只连接示例明确列出的5条组合边，不把所有Motif串联。认证、复用次数、工具数和环境依赖不用于推导等级或组合边。示例不写回账户。关闭详情时释放窗口和观察器；账号失效时清理证据与示例状态。

## 源码与复现

- 分支`codex/desktop-local-runtime`；界面源码`822c07501ddc7e261bbc44bb12911d9f3ffa4731`，仅本地提交。
- 界面：`apps/desktop/ui/desktop/motif-library.js`、`motif-comparison.js`和`fractal.css`；静态资源路由`apps/desktop/src/frontend.ts`。旧`motif-hierarchy.js`已移除。
- Windows公共构建入口：在`apps/desktop`运行`npm run dist`；正常完整离线工具分发保持原样。本次复用已核验工具及压缩条目，只更新宿主EXE和`app.asar`。
- 图形和字体来源保持`apps/desktop/brand/PROVENANCE.md`。保留同版本Windows Shell G图标修复、简洁安装器及“正在检查安装位置”提示。

## 验证与边界

- `npm run check`：14项通过。初次受保护Temp的原子改名失败，换工作区Temp后通过；不改产品设置逻辑。
- `npm run smoke:renderer`：最终24组隔离界面诊断通过，控制台错误0，真实模型请求0。覆盖三卡独立收起、居中详情、节点交互、放大/还原、A/B同源计数、示例隔离、任务右栏不被替代以及认证失效关闭详情。
- 中间一轮旧的`dialog`选择器命中已关闭但尚未移除的详情窗，导致取消删除诊断超时；最终限定`[open]`并确保替换详情时移除旧窗后全程通过。失败记录保留，不计入最终通过。
- 包内22项界面资源与当前源码逐摘要一致；旧模块不存在。宿主ASAR完整性记录正确。25,826工具文件、共1,432,913,211字节的逐文件SHA名册与原版相同，Runtime摘要相同；25,949条未变压缩条目保留，仅两项宿主文件更新。
- 最终安装器四状态及布局检查通过。本轮没有实际覆盖安装、重测耗时或真实模型任务。截图使用隔离协议夹具；它们不代表用户账号数据或真实RSI效果。

## 本地交付

- 文件：`H:/DeepSeekHarness/.local/desktop-releases/0.3.0-preview.27/windows/GeneLoop-Desktop-0.3.0-preview.27-x64-Setup.exe`
- 大小：766,719,488字节（约731.2MiB）。SHA256：`321120cddc3e6379d28ec39082d2e98dd318ee193820ce28daf459543c3afc23`。
- 同目录的`delivery-manifest.json`、`SHA256SUMS.txt`、校验回执及`预览/`给出实际产物和截图；最新界面诊断位于桌面工作区`apps/desktop/.local/validation/renderer-62a28243-089d-4ed1-96ba-f7a1802d5f2e`。
- 同名旧preview.27 EXE已被本次替代，旧记录摘要仅属历史。preview.24冻结tag及原三平台包、preview.26 Windows包仍保留。
- 未推送源码、未上传安装包、未合并main或部署。Mac本轮暂不构建。

下一步由用户本地安装试用，确认三种详情入口和Windows应用栏图标；当前层级示例不能外推为后端已有分层。
