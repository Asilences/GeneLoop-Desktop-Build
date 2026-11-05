# GeneLoop Desktop preview.10 隔离验收

- 实验 ID 为 `desktop-preview10-20261105`。Windows x64 工作树基于 `c803ae1`，使用当前候选改动。试用通过 V100 回环网关和原有账本。模型为 `deepseek-flash`，`reasoning_effort=off`，沿用试用配置和十分钟任务授权。范围为六场景功能交付及单条只读 Motif 结构认证。
- 使用合成文件和独立 Agent 会话。实际安装布局为 `.local/desktop-preview10-verified/win-unpacked`。记录 `.local/desktop-preview10-real-1793816091534/summary.json` 包含测试输入摘要、模型请求增量、实际工具和报告文件名。测试使用独立打包布局，未覆盖日常安装。
- 六场景验收分别为通用对话 1 次、文件 3 次、CSV 分组 3 次、LaTeX 引用核验 4 次、PPT 3 次、视频 5 次真实请求。正式复验合计 19 次，调试调用另有记录。源文件摘要逐项检查。PPT 保留模板的母版和版式，Windows LibreOffice 实际生成 PDF，检查输出文字与产物摘要。视频在 V100 无网络的用户命名空间中实际渲染，客户端完整解码。FFprobe 核对 640×360、H.264、30fps、30 帧。
- Linux 渲染使用 Playwright 系统镜像摘要 `sha256:ee15712262f017b8157421b212b12099146645f44b1bc5c0514cbbe6a229b1d0` 和 Remotion 4.0.539。单独的 Remotion 探针先完成真实渲染，再验收模型生成的 TSX 和素材确认。正式试用没有改变正式站点。
- Motif 实验冻结 `desktop-motif-contracts.json`、版本字段、实际工具 schema 和 ASAR 摘要。合成任务稳定性、活性保留和对照组人数分别运行独立会话，前两条训练、第三条独立认证，实际 9 次请求。仅从观测到的临时来源凭证传递提取候选边，保留一条结构认证通过的只读边。共享在线执行器以实际本机文件验证一次摘要一致的复用，属于无模型的确定性诊断。
- 证书、锁及诊断在私有 `.local/desktop-preview10-motif-v3/`。旧云端证书继续依原执行范围。当前只认证本机 PPT 来源读取，不包含写入、任意页语义推断、质量或成本对照。未进行人工盲评、账单核对或测量人工作业时间。
- 安装包 547,687,936 字节，SHA-256 为 `8f5d218a943c7e48bc59fc6ad3fd6c1c4cbcf23b6c9eb18d5eb70ea2a63dfd53`，已验证内嵌安装引擎一致。候选未签名、仅本地保存。自动复用仍限独立诊断，普通桌面对话使用正常 Harness。
