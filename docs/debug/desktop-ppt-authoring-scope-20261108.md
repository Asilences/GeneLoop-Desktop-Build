# 桌面 PPT 制作范围与 DSH 重工具核对

- 日期：2026-11-08；桌面分支 `codex/desktop-local-runtime`，本轮基于 `9761bdb7`。
- 用户最新范围：PPT 只制作、编辑和核验演示文稿；不要旁白、配音、演示视频、录屏或字幕。此前提出的语音服务器接线随此范围撤回，不新增该服务。
- 状态：当前源码候选已收窄，Windows 定向诊断通过；preview.19 三份已交付安装器、公开工具包、账号与正式服务器均未修改，未制作或上传新安装器。Mac 新源码尚未原生回归。

## 为什么出现语音目录

此前桌面适配为覆盖锁定 PPT Master 6.6.0 的可选 `video_subtitles.py`，把 stable-ts、Whisper base 和完整 CPU Torch 加进了独立 speech 目录。这是桌面适配的打包决定，不是同伴的服务器部署要求，也不是制作或编辑 PPT 的必需依赖。上游该脚本的用途是：把冻结的旁白 SRT 文字与演示视频实际音轨对齐，输出真实时间戳字幕；不能因上游附带脚本就默认纳入 GeneLoop PPT 产品范围。

已交付 Windows preview.19 清单显示：语音包压缩 448,467,729 字节，解压 3,679,255,589 字节。Whisper base 权重约145 MB；`.lib` 静态链接库合计 2,772,443,590 字节，`torch/lib/dnnl.lib` 单个约2.33 GB。它不是一份3.68 GB的语音模型。此前照单分发完整 wheel，包含了制作PPT不需要的开发／编译资源。

新客户端不生成、不分发 speech，也不安装 edge-tts。旧缓存不主动删除，旧安装器和公开七包保留作为回退；新工具集须重新构建并使用新的摘要／目录，不能冒充旧版本。

## 同伴服务器的代码证据

只读 fetch 的最新 main 为 `1d1e16f4bde7f980127a53ead305e0e5d8b08b86`。在受查 `scripts`、`src`、`scenarios`、`config`、交接／运维目录中没有找到 Whisper、stable-ts、SenseVoice 的依赖或语音部署记录。

[`scenarios/remotion_edit/tasks.json`](https://github.com/jingyio/GeneLoop/blob/1d1e16f4bde7f980127a53ead305e0e5d8b08b86/scenarios/remotion_edit/tasks.json) 的 `t05_captions` 已给出字幕文字和时间，明确不调用语音识别。这是该合成任务的条件，不是服务器安装清单，也不是所有任务永久禁用语音的证据。当前PPT制作范围按用户最新指示确定。

main 的 PPT 场景通过 `scenarios/ppt_master/scenario.json` 提供技能／来源读取；`scripts/install-ppt-master.py` 校验和复制字节锁定的 Skill，没有安装语音依赖的命令。上游脚本存在、某台服务器手工安装过依赖、正式网页已经启用语音，是三种不同事实。

因此不能确认同伴服务器已经部署语音，也不能从GitHub得出其安装体积。V100是用户自己的测试服务器，不能拿它的状态代替同伴的服务器。本轮没有改同伴或V100服务。

## DSH 逐项参考

核对官方 `deepseek-ai/deepseek-harness` 固定提交 `fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`。本项目仍锁定 DSH `0.1.5-rc.3`，本轮没有升级 Agent Runtime。以下区分实际机制与未找到的现成业务服务：

| 项目 | 官方可核对处理 | GeneLoop 当前决定 |
|---|---|---|
| Office／PDF | [workspace dependencies](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/skill/tool-workspace-dependencies/README.md) 返回固定随包运行时；Office 使用独立 Kit 能力 | 保留本机制作和预览；精简 Kit 候选见本轮前一记录 |
| 语音输入 | [SenseVoice Provider](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/experimental/speech-to-text-sensevoice/README.md) 用 sherpa-onnx／ONNX Runtime，默认 INT8 权重239,233,841字节，显式准备、摘要校验、缓存、空闲释放；不要求Python／Torch | 这是独立语音输入，不能直接替代冻结旁白的字幕对齐。本轮两者均不引入PPT |
| 批量扫描／OCR | 受查 primary-runtime 锁中没有专用大型 OCR 引擎；存在通用 Skill／MCP／命令执行机制 | 保留当前基础材料读取／OCR，不宣称 DSH 已有可直接复用的重 OCR 服务器 |
| FFmpeg／Remotion | 受查官方源码目录未找到对应专用业务模块；[后台 jobs](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/jobs/tool-jobs/README.md) 可管理执行、等待、取消，远程可用 MCP／SSH | 保留独立视频场景原本的本机剪辑和 Remotion；从PPT排除演示视频扩展 |
| 大型数据分析 | [primary-runtime 锁](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/scripts/primary-runtime/lock.json)包含 NumPy／Pandas；[SSH Provider 家族](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/ssh/README.md)支持本机Harness调用POSIX远程文件、进程、终端和sandbox | 普通分析本机；以后重计算复用远程 Provider，不能把公共框架称为现成数据分析集群 |
| 批量浏览器任务 | [Playwright MCP Provider](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/experimental/browser-use-playwright-mcp/README.md)支持 launch、attach现有HTTP/WS浏览器端点，按Session管理生命周期 | 可参考远程浏览器和会话隔离机制；当前本机共享一份Chromium，不暗中上传登录状态 |
| 大型图像生成等模型 | 受查 primary-runtime锁没有这些权重；[MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/mcp/mcp-client/README.md)支持stdio／Streamable HTTP服务 | 不给基础客户端新增大模型；已有外部服务仍须真实配置，不虚构已部署能力 |

源码目录／包锁的有限核查不证明生态里不存在其他插件。需要接远程服务时优先复用现有 MCP／SSH、生命周期和取消，不重写 Agent 循环。

## GitHub 与分发

Git源码库保存代码、版本锁和下载配置，不提交Torch或模型文件。已交付语音分包约449MB本身可以放GitHub Release；[GitHub官方限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)针对每个压缩资产（低于2GiB），并不是解压后体积。本次不再需要分发该语音包，也未上传新资产。

DSH自己的[发布机制](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/apps/desktop/publishing/README.md)另有对象存储／下载站；不能把它理解成把所有大型依赖提交进Git仓库。

## 当前实现

- `apps/desktop/skills/geneloop-ppt/SKILL.md` 是明确限定范围的 GeneLoop Skill；桌面不再把完整上游 Skill 当默认技能入口。上游字节锁与文件保留作制作引擎和来源校验，不修改其核心。
- `local-ppt-master.mjs` 的上游指南加范围说明；`local-agent.mjs` 明确不采用配音／视频／字幕扩展。
- `desktop_python_entry.py` 对 `narration_sync`、`notes_to_audio`、`powerpoint_video`、`video_motion_plan`、`video_sound_mix`、`video_subtitles` 六个锁定CLI返回明确的范围错误，不要求修复安装或下载依赖。
- 停止Windows／Mac语音准备，删除桌面专用语音打包脚本；依赖清单取消edge-tts。旧Python构建输入中残留的edge-tts模块也不复制到新工具目录。
- 工具分包变成六包：workspace、python、office、browser、media、converters。构建器忽略旧构建输入中的speech，但不删除它；同一workspace包包含新Skill。发布／下载检查按实际包数验证，兼容历史七包。
- 保留原生Office、PDF／PNG检查、源材料、模板编辑、科学计算、FFmpeg与独立Remotion场景。没有新增语音接口、服务器凭证或生产部署。

## 验证与边界

- `node apps/desktop/scripts/check-ppt-authoring-scope.mjs`：六个真实锁定CLI均被拒绝；原件SHA不变；默认直接依赖不含语音组件；0模型请求。
- 六包真实7z小夹具：语音目录未归档，新GeneLoop Skill归档，源speech未删除；回执 `.local/desktop-ppt-only-20261108/pack-scope-receipt.json`。
- 既有Windows原生PPT检查通过：模板填充／普通编辑、原模板不变、真实字体校准、图片／备注、PPTX和PDF交付。DSH公共工具读写、搜索、Python、问题、交付与后台取消通过；均0模型请求。
- 增加实际Skill枚举／读取后，初次诊断暴露上下文未显式取服务，以及只读目录漏掉枚举父目录的问题。修正为显式服务获取、只开放项目自有skills目录的只读访问后，实际目录恰好只有 `geneloop-ppt`，调用 `skill(name='geneloop-ppt')` 成功，路径越界仍拒绝。没有放开整个工具目录；失败与最终结果分别保留。
- 桌面TypeScript与14项前端／宿主检查通过。本轮没有为这些打包和范围改动重跑付费模型任务。
- 按仓库约定启动了 `npm test`，前4%的Python回归已出现多项失败，停止继续扩展运行；尚未逐项归因，不能报告全仓通过。日志保留在本轮私有目录。上述定向原生检查分别报告，不把它们代替全仓结果。
- 以上不是最终安装包或Mac验证。当前已交付Windows清单结合前轮Kit大小推算，新工具下载约370MB、解压约1.63GB；仅为估算，未生成完整新六包，不当作新版本实测体积。其他单包约：Python621MB、Chromium291MB、Pandoc240MB、FFmpeg204MB（解压），不存在与原speech相当的另一个数GB组件。服务器手工安装体积仍未知。

原始合成检查、大小审计、GitHub官方源码快照位于私有 `.local/desktop-ppt-only-20261108/` 与 `.local/dsh-heavy-tools-research-20261108/`。不提交原始日志或二进制。接手应先完成新Mac范围／Kit原生回归，再制作新的三平台工具集和本地安装器；不得复用缺少 `geneloop-ppt` Skill 的旧工具目录冒充新版本。
