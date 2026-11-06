# 工作区 Motif 展示联调

日期：2026-11-06。基线 main `d1863342`，独立分支 `codex/motif-library-ui`。

## 问题与实现

用户要求将能力组合、评估、演化和版本融入工作区首页，并保留全局库及左下摘要。实现与范围见[产品说明](../product/desktop/motif-workspace.md)和[交接](../handoffs/motif-visualization.md)。本轮未修改原 Windows/Mac 工具迁移工作树，未构建或上传安装包、未部署服务。

前后端消费 #150 公开的 `coding-motif-evidence-v1` Schema、消费者与真实脱敏样例。样例只用于明确标识的预览和隔离联调；实际账号目录需要宿主绑定导出。没有新 Store、Agent 循环或执行授权接口。当前只有依赖条件、实际 match/invoke/fallback 和当前版本；其他关系、学习/发布、历史与收益数据未提供。

## 代码锁兼容

网关增加三处接线后，原 Paper v84 / PPT v82 的严格代码锁按预期拒绝新网关。没有放宽加载器、改写旧证书或增加通配允许名单。

`scripts/reexport-motif-view-compat.py` 复用现有 `reexport-native-capabilities-compat.py` 的精确差异审阅、不可变原件校验、暂存准入与最终源码复查，为 Paper v85 / PPT v83 生成兼容版本。两侧唯一旧代码差异必须是 `scripts/harless_gateway.mjs`；额外锁定只读适配器、共享投影、Schema 和重导出脚本。原 IR、online manifest、task、完整工具 Schema 和来源证据字节不变；旧版保留。本次零训练、零原始轨迹重放、零模型请求，不作质量或收益晋级。

```powershell
python scripts/reexport-motif-view-compat.py --preview --validation-record docs/debug/motif-workspace-20261106.md
# 仅在发布目录尚不存在且源码已冻结时首次生成：
python scripts/reexport-motif-view-compat.py --write --update-registry --validation-record docs/debug/motif-workspace-20261106.md
```

命令不能覆盖已存在版本。回退时应整体回退本分支的网关、展示模块和 registry 选择；不能只将旧库指向新网关。与 PR #159 集成时须重新核对其精确兼容摘要及展示 GET 路径的网络用途白名单，不能泛化放行所有 API。

## 验证记录

Windows / Node 24.19.0 / Python 3.11.7。当前工程检查不调用模型，不等同于本机执行效果或新版本认证实测。

- 桌面构建、12项桌面检查、4项 Motif/实际网关检查通过。
- Electron 回环页面15组检查通过，控制台错误为0；五视图、全局库、导出更新、账号失效清理、工作区摘要与浅深色已验。深色标题继承黑色的问题在截图审阅中发现并修复。
- 最终截图和回执：`apps/desktop/.local/validation/renderer-ba3bbd45-698c-4dc1-b615-5f531818948e/`；定向检查日志：`.local/debug/motif-library-ui/`。截图采集先请求一次合成帧，再等待绘制，避免将切页前画面误当作当前页。
- 全量 `npm test` 的 Python 阶段：2892通过、272跳过、77失败、30错误。随后显式执行全量 Node 阶段：1602通过、63跳过、22失败。原始结果保存，不称全量通过。失败包括 Windows 符号链接权限、缺失 reportlab/OCR 环境、fixture/状态断言及上述代码锁差异；未经同环境基线对照，不将其全部归为历史问题。
- 兼容修复后，`tests/test_harless_paper_product_bundle.py`、`test_harless_rsi_bundle.py`、`test_motif_view_compat.py`共53项通过；Motif路由加既有网关32项通过，原受代码锁影响的Paper挂载1项通过。原全量日志不覆盖。`build-continuation-policy.mjs --check`通过。代码锁失效、负向检查和既有语义回退测试保留。
- `npm run motif:check`未通过：原标准样例在Windows退出临时目录时出现WinError145（目录非空），没有改动其生命周期来求绿，也不将部分运行算作通过。日志为`motif-example-final.log`。

原始全量日志为 `.local/debug/motif-library-ui/npm-test.log`、`node-test.log`、`status.json`；最终定向复测在`compat-tests-final.log`、`gateway-final.log`、`paper-node-final.log`、`desktop-check-final.log`和`renderer-capture.log`。受限环境首次兼容导出的暂存目录保存在同目录`failed-compat-stage-restricted`，正常权限复测成功；提交前的临时候选也在同目录私有保留。无真实模型请求、供应商费用或 Mac CI 消耗。

## 尚需集成

正式宿主部署及账号导出绑定、本机 Runtime 的活证据桥、其他场景展示协议仍未接通。#150 同伴正式源码尚需集成共享协议，当前按其公开交付消费。真实同质量配对任务、历史版本、学习和发布事件须由来源提供后再呈现；页面不生成替代事实。

## 左下摘要视觉重做

用户认为初版的线框容器过于简陋，要求更接近原设想图。调研 Magic UI / GlassKit 后，按用户图中玻璃培养皿重绘原生 SVG：厚边、高光、水面、底部折射、立体能力球与柔和漂浮；卡片增加明暗材料、状态图例、两栏实际统计与紧凑收起状态。没有复制第三方代码或新增依赖。

只改展示及现有截图采集，不修改后端、协议、代码锁、任务或账号数据。光学层没有假能力或关系；球体来自当前快照，未知数字仍为破折号。只提供认证状态，未伪造能力层级或演化次数。

桌面构建和12项检查通过，现有 Electron 回环15组通过，控制台错误0。检查了浅色、深色和收起截图；系统减少动态效果通过 CSS 关闭漂浮。此次没有重跑全量回归，上一节失败边界继续有效。

本轮日志 `summary-build.log`、`summary-check.log`、`summary-renderer.log` 在 `.local/debug/motif-library-ui/`；截图和回执在 `apps/desktop/.local/validation/renderer-e40b4794-47bd-4745-9f72-7e265db85a48/`，含 `motif-summary-light.png`、`motif-summary-dark.png`、`motif-summary-collapsed.png` 和整体页面。先前自动审批超时后重试成功；没有真实模型请求、生产部署、安装包构建或上传。
