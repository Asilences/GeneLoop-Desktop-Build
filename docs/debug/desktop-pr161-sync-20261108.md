# Desktop preview.22：PR #161 客户端适配

- 上游锁定：[PR #161](https://github.com/jingyio/GeneLoop/pull/161)，`225d7b557b640a7e66610077b9694c781da8cf37`（2026-11-08）。本轮仅桌面客户端，不整包合入后台、隐私核心、场景配置或认证库，不改正式服务。
- 已接入：`/api/harless/motif-catalog` 的`geneloop-runtime-motif-catalog-v1`目录与`geneloop-motif-evidence-v2`只读证据，原工作区Coding v1读取保留。来源可切换，展示实际工具流、版本兼容来源、任务和对照原始用量；Data旧回执保持“旧格式已登记”，缺少调用/收益证据时保持未知。
- 桌面兼容投影和v2 Schema位于`apps/desktop/motif/`，来自该提交原只读模块/Schema；为保持后台代码锁和其他对话的范围，未改根目录共享投影器。后续上游协议升级同步这份兼容副本；后台完成统一整合后再评估去重。
- 现有圆角来源菜单复用`choiceControl`。服务端准入与“本机可用性待核验”分别显示；目录读取不授权本机执行，不改本机Runtime认证、模型通道或可选共享同意流程。
- 原桌面能力保留：本机/云端工作区、草稿、场景同步、已有任务与PPT预览；安装器沿用用户确认的540×360紧凑单栏，无装饰图、场景列表或“开源许可”入口。

## 验证

- 桌面构建、原14项桌面检查、7项只读协议/网关隔离检查通过；v2的执行授权、伪认证和断开版本证据被拒绝，v1边界保留。
- Electron隔离界面回归通过，控制台错误0，覆盖三库切换、版本页、原任务/对照用量、503缓存警告/恢复、401清理、PPT预览/下载、草稿、本机工作区绑定与主输入框。私有回执：`apps/desktop/.local/validation/renderer-dc1f9383-68fe-4b85-b1cb-7e722c967d84/`。
- `tests/fixtures/motif-catalog-pr161.json`由隔离的原PR源码、原加载器/目录投影器读取公共库生成（PPT2、Paper1、Data10项），附来源提交；客户端检查消费固定公共快照，不冒充当前生产账号或实时服务器验收。临时源码解压在受限环境遇到Windows路径访问拒绝，普通本机环境重跑通过，未放宽原加载器。
- 本轮模型请求0，没有重复六场景真实模型任务。后台新目录接口须由PR #161的服务端版本提供；本轮未部署或证明正式站已提供该接口。本机Runtime活证据桥/重新认证仍由执行链另行验收。

## 交付状态

preview.22客户端已适配并完成上述检查。用户已明确授权仅在桌面网络用途清单追加`/api/harless/motif-catalog`这一条只读地址；脱敏、采集、共享同意及后台核心/配置没有改动。应用源码`b2373232953c017308ae9e74b312bcce15f7c0ec`，交付记录`ad0b7887`已按用户要求推送团队origin的`codex/desktop-local-runtime`；构建镜像`6d45b864777104068a0e4744d0bf5132b93a3213`。未上传安装包、合并远端PR或部署服务。

三个完整离线安装包已取回外层仓库私有`.local/desktop-releases/0.3.0-preview.22/`，各目录保存SHA256SUMS、验证回执和使用说明：

| 平台 | 安装包字节 | 工具文件 | SHA256 |
| --- | ---: | ---: | --- |
| Windows x64 EXE | 754,723,328 | 25,666 | `67954abe412bacb74e141980afee6749d2e1d0ac800e7e52a80828023f654a30` |
| Apple Silicon DMG | 665,068,991 | 26,220 | `1b4003d3bef8c7b0218385176c400fe7289b777fdd1f1e90acaecac0ca7b4394` |
| Intel Mac DMG | 683,477,105 | 26,219 | `4893362b55cf0074da4fb81e5f62447b7bee40146a6466ced6638c2ed4addf84` |

Windows完整工具逐文件SHA与既有已验收六包一致（零差异），包内Runtime入口和新界面匹配源码；最终EXE的`--check-ui`通过，未安装或重新计时。Mac使用公开标准免费`macos-15`和`macos-15-intel`，run`42475444604`两架构成功：DMG复制应用、卸载镜像后运行核心MCP、PPT/PDF、Remotion、统计/转换及浏览器依赖检查，全部通过，工具复制前摘要一致。本轮没有重复真实模型任务，亦未做Mac人工UAT、Apple签名或公证。

安装包未发布Release；Mac授权临时Actions产物已全部取回、核对并删除，本地四份中转ZIP也已删除。Actions恢复原关闭状态，默认分支/允许列表不变，免费构建新增计费预留0，历史15美元账本保持。私有回执位于桌面工作区`.local/mac22-pr161/`及`.local/pr161-update/windows-payload-proof.json`，旧preview.21交付与用户安装保留。正式服务器的新目录仍需PR #161相应版本，客户端展示通过不等于正式部署或本机Motif重新认证通过。

## 源码推送与未合并PR范围复核

2026-11-08实际读取GitHub当前开放PR、fetch最新引用，并核对提交祖先及变更文件内容：

| PR最新提交 | preview.22的包含范围 |
| --- | --- |
| [#161](https://github.com/jingyio/GeneLoop/pull/161) `225d7b55` | 旧`998cb505`已进入桌面历史。最新客户端读取/展示已适配；`src/adapters/harless_motif_catalog.ts`、新库注册及相关后台变化未整包合入，最新PR head不是桌面祖先。 |
| [#162](https://github.com/jingyio/GeneLoop/pull/162) `ecf449cc` | 此前`7fbe8874`已集成；最新R5策略、检测器及核心更新尚未集成。不能将现有共享界面等同于最新隐私核心。 |
| [#163](https://github.com/jingyio/GeneLoop/pull/163) `8988de79` | 最新PPT轨迹学习、原生认证与连续修订实现未集成；现有本机PPT工具适配不代表已包含该PR。 |

桌面自身后端源码（`scripts/harless_desktop_model.mjs`，网关已挂接）和旧只读`/api/harless/motif-library`（`scripts/harless_motif_view.ts`）在分支中；最新`/api/harless/motif-catalog`后台由PR161提供。此轮仅回答包含范围，没有自动合并其他负责人PR或重做安装包。初次源码推送的远端自动流程为`startup_failure`（run42477299663），未当作CI通过证据；已有本地/公开免费构建回执不变。本次后续仅文档记录，检查diff与链接，不重复付费模型或平台构建。
