# 超限请求的结构化413与有界连接回收

- 实验ID：`gateway-oversize-drain-20261102`。类型为本地HTTP/原生TCP回归，模型请求与新增模型费用均为0；不作为RSI效果实验。
- 问题：模型请求体超过128MiB且客户端已经开始发送时，网关立即结束`Connection: close`响应；未消费完的请求字节可能使TCP连接重置，客户端在收到结构化413前得到`ECONNRESET`。旧失败与隔离诊断保存在`.local/efficiency-rsi-pr-20261102/`。
- 修改：413响应使用精确`Content-Length`，立即发送完整JSON；随后无缓冲丢弃排队输入，收到请求结束/取消或最多5秒后结束响应与连接。客户端不必上传完整个超大请求便能获得明确错误；128MiB容量、授权、正常转发和费用策略保持原值。
- 回归：原失败用例保留并通过，同时检查后续正常请求；新增原始TCP用例验证未发送请求体也能先读完整413，服务器随后按时关闭连接。macOS/Linux各10项传输检查通过；原竞态单项另连续10次通过。
- 场景兼容：复用既有重导出器生成Paper v44/PPT v41，仅核对网关文件变化；原library/online-manifest/task/tool-schemas/source-evidence五项逐字节保留，旧版本不修改。58项既有产品兼容检查通过，无训练/模型调用。
- 配置：模型传输容量仍来自`config/geneloop-transport.json`的134217728字节。这里限制的是整个模型HTTP请求体，不等于单个上传附件大小。Linux使用现有项目隔离环境和依赖，代码位于独立`.local`目录，正式服务未重启或部署。
- 证据：`.local/gateway-oversize-drain-20261102/`保存完整日志、源码归档、10次竞态复核及Linux结果。另一个会话同时修Windows/UTF-8，最终提交验证使用`7fdac81`加本修复文件的隔离导出，不纳入对方工作区改动。
- 最终隔离全量：Python1809通过/237跳过，Node1508通过/19跳过/0失败；smoke及motif:check通过。与另一会话Windows提交叠加后的58项产品兼容复核也通过。Linux执行的网关/测试源码SHA与本地逐字节一致。

复现命令：

```sh
node --test tests/test_model_transport_gateway.mjs
npm test
npm run smoke
npm run motif:check
```

当前只验证代码与HTTP行为；未在生产复现或发布，不宣称真实用户任务、模型质量或费用改善。PR、最终全量结果以主线交接及最新提交为准。
