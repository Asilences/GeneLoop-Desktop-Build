# 研究Harness整段限时

本轮真实制造业任务在原600秒agent时限下运行685.6秒。原因是SDK的`request_timeout_seconds`只限制RPC等待，`Session.run`订阅通知没有同等的整段deadline。

## 修复

`ResearchHarness`按原任务`timeout_seconds`启动Timer。默认研究窗口为28800秒，正数且有限的任务时限原样使用。Timer从本会话MCP及Runtime启动前计时，到期通过公开`HarnessClient.request`调用`session/cancel`，RPC等待上限10秒。Timer结束与join发生在本会话Runtime退出前，完成的会话不会向后继会话发出取消。

实际安装SDK的JavaScript启动接缝返回`unknown DeepSeek Harness SDK runtime method: session/cancel`。因此保留该真实错误，并通过公开`DeepSeekHarness.close()`关闭当前会话独占的Runtime。SDK自身处理有界shutdown与进程退出。该兼容边界没有修改上游代码。

结果新增`timed_out`、`session_timeout_seconds`和`cancel_evidence`。超时状态为`timeout`，部分回答、原工具记录和原费用快照保留。取消、关闭错误均写入证据。原`gate.costs`在finally执行，`gate.current`在更内层finally恢复，未重建费用账本或退还未知费用。

独立评分可使用超时前真实生成的产物，研究调用方负责判定是否具备真实Provider证据及原verifier成功。原整段运行与修复后的限时协议分别保存实验ID。

## 验证

本地23项Harness诊断通过，包含原SDK、原预算代理与loopback合成慢Provider联调。3秒deadline触发取消RPC错误及Runtime关闭后，整段等待在6秒内结束，原请求ID和未知费用保留。该诊断没有付费模型请求。

与SkillsBench适配器36项及汇总20项合计79项通过。原SDK本地socket诊断需允许127.0.0.1监听。Linux回归和真实R3重跑由主任务在冻结代码后执行。

## 边界

实际退出耗时包括SDK有界shutdown及回调服务器关闭，故会略超模型阶段deadline。已发出的供应商请求可能晚于取消结算，仍由原账本保留并在最终汇总核对。当前Runtime不支持session取消的事实继续保留，后续升级SDK须重新验证。
