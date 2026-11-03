# GeneLoop Desktop 独立前端诊断

实验ID：`geneloop-desktop-independent-20261103`。类型：工程/协议诊断，不是模型效果或成本对照。

## 问题与实现

用户要求独立桌面应用，0.1.5顶部黑条修复版只冻结作基线。0.2.0自行实现页面、组件、样式与交互状态，只参考网页视觉/六类场景，通过公开API复用同一服务器。没有打包DSH网页、客户端模块图或远程UI脚本；没有修改服务器或上游Harness。安装产物若仍包含这些网页/插件资源，或必须借用源码Node依赖启动，即不满足本轮工程目标。

独立UI覆盖账号表单、工作区与会话、逐轮场景、模型选择、上传、历史/实时回复、双路结果、文件预览、权限和人类问答、主题及设置。服务器仍拥有Agent循环、场景实现、账本、归属/版本守卫与用户数据；客户端不自动批准写操作，不自动重发消息。

## 配置与复现

代码分支 `codex/geneloop-desktop-independent-ui`，工作区 `.local/desktop-independent-20261103`；冻结基线 `15af73e`、原核实main `2f29d34`。本轮GitHub代理/直连查询均失败，未重新核实远程tip。Windows x64、Node24.19.0、Electron45.2.1、builder26.18.0；固定DSH0.1.5-rc.3只用于开发Host诊断，产品生产Node依赖为空。有效安装资源manifest包含代码commit/dirty、独立前端逐文件SHA256和公共场景目录。

```powershell
npm --prefix apps/desktop run check
npm --prefix apps/desktop run smoke:account
npm --prefix apps/desktop run smoke:renderer
npm --prefix apps/desktop run smoke -- --public
npm --prefix apps/desktop run dist -- --config.electronDist=node_modules/electron/dist
npm --prefix apps/desktop run smoke:packaged
```

本机开发依赖通过已有检出的node_modules目录联接复用，未把开发依赖当作产品依赖。安装检查必须复制到祖先无node_modules的独立临时目录启动。构建使用已有Electron和NSIS离线缓存；第一次误选缺少NSIS的缓存触发失效代理连接，随后使用已核实缓存。不执行安装器，不改注册表或用户安装。

## 结果与失败

- 定向12项通过：本地UI白名单/禁止远程UI、Origin/凭据/body、网络错误、日志替换/重连、逐轮场景与长文本、紧凑流、主题IPC、URL/下载/设置。
- 原网关合成账号4项通过：错误密码拒绝、独立表单登录、HttpOnly Cookie/刷新和退出。原来源校验不改；夹具未启动Agent，认证后工作区API错误不作为工作区成功。
- 原项目隔离Host8项通过：独立DOM无DSH boot/模块加载器或Node、原生工作区/会话/重命名、真实上传合成文件、主题/托盘/连接设置和重连，正式站只读未登录账号检测。该Host配置mock，但未发送模型消息；PPT和视频依赖缺失正确保持不可用。
- 合成协议UI6项通过：历史/安全Markdown/双路结果、交付字节预览、明确写权限确认、模型保存后发送/逐轮重置、人类多选label答案、设置导航/账户表单。回答是夹具，不是模型验收。正常quit连续3次exit0；测试曾在强制destroy/exit路径出现3221225477，负面证据保留，没有声称复现用户旧安装问题。
- 原生RPC首次诊断发现list参数必须为 `_request`；修正后通过。表单/动画等待竞态通过明确等待服务器确认和仅对自己诊断窗口关闭后台节流处理。
- 预构建安装资源ASAR检查与独立目录启动4项通过，确认无网页、插件、生产Node依赖或私有数据。最终构建及全量回归记录在交接收尾补充。
- 全仓Python1825通过/246跳过/16失败/30错误；`npm test`因此未继续Node，补跑Node全量1399通过/46跳过/69失败。桌面12项在全量中及收尾专项均通过；其他失败未逐项归因，不能报告全仓通过。未修改这些失败用例或删除其检查。
- 收尾修正多轮对照的消息位置与阅读滚动状态，合成UI再次通过；安装探针发现DOM初始化前读取body的竞态，显式等待DOM后通过，并额外核验打包应用正常退出码0。
- 最终应用源码6b09d43，构建exit0、sourceDirty=false；121366739字节安装器SHA256 `b681cd9ac73b5ed3ab1bb015971dd72216dc904e8e2b0a1dcef83d4cfab48f2a`。最终ASAR四项独立启动通过，退出码0；安装器内直接解出的EXE/ASAR与独立运行文件逐一SHA相同。未执行安装/卸载。证据、完整源码与可审阅文件位置见当前交接；冻结0.1.5哈希重核未变。

证据目录均为 `apps/desktop/.local/validation/<RUN_ID>/`；具体ID见[当前交接](../handoffs/desktop.md)。原始日志、截图、合成账号不提交。原生账号/Host诊断与合成渲染分开记录。

## 成本与结论边界

真实模型请求0、模型费用0；无API缓存/token/模型耗时收益结论。开发维护时间没有计入模型费用，也不宣称降本。工程检查支持独立客户端与原协议可连接、安装资源不借用源码；不支持正式账号/所有场景真实交付质量、生产部署或本机Agent执行结论。

下一步使用隔离正式账号与服务器真实API验收普通Chat、六场景及持久操作，沿用原账本并记录质量、失败、请求和账单。旧基线、正式服务及用户当前安装保持不动。
