# 工作区中的 Motif 能力与演化

本模块在 `codex/motif-library-ui` 独立开发，不合入或覆盖 `codex/desktop-local-runtime` 的 Windows/Mac 工具迁移。基于 main `d1863342`，保留现有桌面视觉、会话、草稿与工作区行为。

## 页面组织

- 工作区首页包含「运行、能力组合、评估、演化、版本」。运行页保留最近对话、继续任务及新会话入口；其余页面只显示本工作区的证据。
- 全局「Motif 库」按账号列出宿主已绑定的工作区，切换后浏览能力、认证状态、范围和证据。与工作区共用详情组件。
- 左下 Evolution 摘要随当前工作区变化，采用参考图的玻璃培养皿、立体球体和分栏统计。球体对应实际能力，最多绘制18个；数字仍为实际统计。颜色表示认证状态，不代表能力等级或收益。收起时保留两项数字；漂浮动画遵守系统减少动态效果设置。
- 展示端不授予执行权；快照中的「已认证」与当前电脑的可用性分开。当前可用性固定标记待核验，等待 Runtime 提供精确兼容检查。

目前协议只提供环境、依赖锁、读写约束和 match/invoke/fallback 事件。未提供 Motif 组合、学习/发布事件或历史版本时，明确说明待接入；不生成假连线、进度条或版本记录。

卡片视觉参考用户设想图，并调研了 [Magic UI](https://github.com/magicuidesign/magicui) 的粒子组件方向和 [GlassKit](https://github.com/JUNGHERZ/GlassKit) 的玻璃卡片方向。最终为本项目原生 SVG/CSS 绘制，没有复制其组件源码或新增 React、WebGL、动画库依赖。玻璃反光与水纹是光学装饰，不表示能力之间的结构关系。

## 后端接入

`scripts/harless_motif_view.ts` 通过现有账号网关提供 `GET /api/harless/motif-library`。已有登录 Cookie 决定账号；可用 `workspaceId` 参数缩小范围，不能指定文件路径。没有配置时返回空目录。正式服务仍需维护者按统一发布入口部署，本分支不改变运行服务。

宿主的私有网关配置（统一启动计划 `gateway_config` 指向的 JSON）可增加以下配置，路径指向原导出器生成的**脱敏展示快照**，不指向原始轨迹或凭证：

```json
{
  "motifEvidence": {
    "sources": [{
      "accountId": "example-account-id",
      "workspaceId": "example-workspace-id",
      "executionLocation": "cloud",
      "path": "/private/exports/coding-evidence.json"
    }]
  }
}
```

`accountId` 必须是账号稳定 ID。每账号、工作区一份当前快照；路径是宿主预先配置的物理绝对路径，拒绝链接、非普通文件、硬链接和超过4MiB的文件。客户端没有写入、注册或执行接口。配置中的执行位置只说明证据来源，不改变会话执行位置。

返回 `geneloop-motif-catalog-v1` 包装，含目录内容摘要 `revision`、工作区 ID、来源执行位置、读取状态、兼容性状态及原协议 `evidence`。不可读取的条目标记 `unavailable`，不泄露物理路径。当前仅接 Coding v1；其他场景需由负责方提供兼容、版本化展示导出。

前端仅在已登录工作区可见时，每10秒读取一次；导出内容变化时更新页面，页面重新可见时立即读取。失败时保留旧证据并标示错误；退出或重新登录会清空内存与正在读取的请求。此版是快照自动更新，不声称逐事件流式推送。

## 同伴协议与证据来源

协议、原消费逻辑和公开真实脱敏样例取自同伴在 Issue #150 的两条交付：

- [公开样例](https://github.com/jingyio/GeneLoop/issues/150#issuecomment-6674873020)
- [Schema 和 TypeScript 消费者](https://github.com/jingyio/GeneLoop/issues/150#issuecomment-6674898704)

`config/motif-evidence-v1.schema.json` 保留原 v1 协议；`src/adapters/motif_evidence_projection.ts` 复用消费逻辑，增加重复事件拒绝和统计投影。前后端共用投影；浏览器使用构建时生成的校验器，保持现有 CSP，不开启动态代码执行。

公开样例是历史宿主证据的展示联调，不是当前账号数据，也不是本轮新增真实任务。手动导入仅驻留内存，不会上传或绑定工作区。单项无法归因的费用和完整耗时保持「未知」；任务估费与单项费用分开，没有同质量配对基线时不计算节省。

## 本机开发

```powershell
npm ci
npm --prefix apps/desktop ci
npm --prefix apps/desktop run build
npm --prefix apps/desktop run check:motif
npm --prefix apps/desktop run check
npm --prefix apps/desktop run smoke:renderer
```

最后一项在回环协议服务中调用实际只读路由，验证工作区五视图、全局目录、样例标识以及浅深色页面。它不启动模型任务；原始回执和截图在 `apps/desktop/.local/validation/renderer-*`，不提交。完整回归状态见本模块交接。
