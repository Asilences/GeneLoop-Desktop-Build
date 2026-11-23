# ChartMimic 效率 SI 价值预检（2026-11-09）

## 问题与冻结条件

检验正常 Agent 绘图程序是否包含能由原学习器自动参数化、认证并在新图任务中替代重复源码生成的结构。先检查真实程序，不预写 renderer/Motif，不启动 Evolution，也不扩 C→D→E。

冻结官方代码 `92ba5b97b908c607f630c3ffbb5043de9de62b76`、ICLR 数据包和 `scenarios/chartmimic/roles.json`。学习为 `line_1/line_5/line_10`，独立认证保留 `line_2`，后继保留 `line_13/14/15`，log 轴变化负例保留 `line_6/9`。先从普通单轴多折线任务取样；没有真实可认证候选则不启动后继配对或扩样。认证/后继尚未运行时不能记为通过。

输入、官方工具和评分核查见[场景说明](../../scenarios/chartmimic/README.md)。Direct 只有图像和尺寸；Customized 存在原图与目标图、参考数据后处理差异，本轮拒绝未完成的适配。官方低层实际评分是文本、图表类型、颜色、布局四项；legend/grid 被实例化但该官方任务并未调用它们。高层保留原六项视觉标准与原 judge，尚未具备其独立实测结果。

## 环境与来源

- Git 分支 `codex/chartmimic-efficiency-si-20261109`，从 `5e21c75` 快进最新已核实 main `e2494b0d0df64d0e63949a9e36823ad973fd5b61`，没有复制共享脏树；只新增 ChartMimic 场景、检查与独立文档。
- 普通学习入口来自独立干净候选 `c2f332b72997bb82b532ed4f13d0b04eea10df9e`。将其已提交 `src/scripts/schemas/config/scenarios` 与依赖清单归档到本场景隔离 runtime；1163 个文件 SHA 核对一致。该候选不是本 PR 的新算法或 main 已有功能。
- Linux 私有实验根标识 `efficiency-si-chartmimic-20261109`。不改正式服务/账号 Home/库。相邻视频实验独立目录；共享原 `remotion-motivation-20261027-v1` 连续账本，只在原 `capability-proposal.lock` 独占 Gate 中串行付费，历史不清零。
- 有效配置拟采用 Kouri AI `deepseek-v4.1-flash`，SDK `deepseek-flash`，推理 off，输出 393216，费用和请求 `null`；单题诊断期限 600 秒，原 Harness cancel。逐次真实 effective、请求、事件、SHA、token/缓存/费用与取消证据留私有结果。
- Linux Node 22.23.3 / Python SDK 环境 3.10.21；求解容器 Python 3.11，绘图 Matplotlib 3.8.4 / NumPy 1.26.1 / SciPy 1.12.0 / Pillow 10.2.0。不是原完整 conda 环境复刻，需保留 Python/字体/间接依赖差异。

数据包 SHA256 `a9b774a165e2e534f02b269285736cb2eed6bdb433d603a66e835fd768336866`；Direct 题面模板 SHA256 `dafb51d44fe8e128df36bea8b76f36f84514c65338924ddb05265653ed241e14`。实际绘图 image ID `sha256:c181a5a04993b11742db8c1784ae7933ddeae232d170151c060d2951602fc218`，完整间接依赖见私有 `environment-pip-freeze.txt`。

## 三题真实结果

| 训练题 / 运行 ID | 实际交付 | 请求 | 已知输入 / 输出 token | 已知代理费 USD | 时长 |
| --- | --- | ---: | ---: | ---: | ---: |
| `line_1` / `learning-line1-001` | `plot.py`、PNG、PDF，模型回看成图 | 4 | 9142 / 1398 | 0.0044202 | 70.39 秒 |
| `line_5` / `learning-line5-001` | 无程序/成图；10 次命令在像素测量后 HTTP 502 | 11 | 34336 / 4270（仅10次已知） | 0.0154248 + 1次未知 | 175.73 秒 |
| `line_10` / `learning-line10-001` | `plot.py`、PNG、PDF，模型回看成图 | 5 | 10022 / 1337 | 0.0046110 | 81.01 秒 |

本轮真实请求 `6826–6845` 共20次，19次已知输入53500、输出7005 token，缓存命中0；已知代理费合计 USD0.024456，另有请求6840的用量/费用未知。该502请求保留 USD0.4968123 上界预留，不退款、不当实际费用。原账本总请求6825→6845，保守累计97.93920876→98.46047706，含本轮及以前未知预留，均不是 Kouri 实付。首个启动另有宿主缺 `dotenv` 的零模型失败，读取方式修复后首次真实启动成功；该错误日志保留，不增加或虚构模型请求。

两个完整任务都真实执行了普通绘图程序，没有人工写入解题数据或标准答案。`line_1` 源码1402字节，SHA `98d72dd3d4c00f5b450ad43be834ee52cd044c68ae8d1669793b25cea91ff779`；`line_10` 1181字节，SHA `ae230852e73a1e5bc9698f62febd5a6908ef84ba9dbe142ed0faeec808fbe21f`。原程序见各运行 `workspace/code/plot.py`，私有，不入 Git。

实际图像链已核对：工具将冻结 PNG 送入原 attachment service，后续真实请求确有 `image_url` 像素。原 Harness 仍预处理图像：`line_1` 942×710 PNG→921×694 JPEG（请求6827），`line_10` 948×710→924×692（请求6842）。原 effective 中 `original_bytes_no_resize_no_description` 只准确描述场景→attachment 的入口，不能用于端到端声明；保留原快照，用 `wire-image-audit.json` 追加更正，没有回写旧证据。当前代码已将该字段改成明确 SDK 可能预处理。

## 原学习器结果与真实阻断

两份完成程序经原 `collect_shell_call()` 提取均为 Script0 / Artifact0。完整命令的 `mkdir + cat heredoc + cd + python` 外壳被原解析器以 `single_python_invocation_required` 拒绝；第三题的图像测量还触发 PNG 不能按 UTF‑8 读取的原限制。失败题只保留 `skipped_unqualified_source`，未成为合格训练材料。

为避免停在外壳错误，追加了零模型源码诊断：对 after-boundary 中逐字出现在真实命令的源码核验 SHA，再直接询问原 `bind_observed_files()` / `validate_source()`，没有改写算法、制作新 Motif 或颁发认证。两份源码分别有5/4个直接数组赋值、2次 `savefig`；原文件绑定器均返回无见证文件输入/输出接口，未经改写的源码又被 `program_unbound_external_literal` 拒绝。现有绑定器只识别有限 file IO，不识别 `Figure.savefig`；现有普通参数学习还要求至少一个已见证输入 role。原图是供模型理解的 PNG，不能伪装成 UTF‑8 数据接口。

观察到的重复模型工作是：从图读取当前数据/样式后，再次生成 NumPy/Matplotlib 数据数组、单轴曲线、标签/图例、轴范围及两种格式导出。`line_5` 还反复生成像素测量程序。源码中的相似结构不自动构成已学得抽象；本轮具体卡在**正常程序到受限参数接口/候选的提取与编译**，同时存在普通任务未交付与评价未完整的阻断。没有证据将其归因为匹配失败、Runtime接管失败或学习费用过高，因为这些阶段尚未启动。

没有合格候选，因此没有认证、Store 发布、冻结 C 或后继调用；这些均为“未运行”，不是认证失败。预留认证/后继/负例题未求解、未用于修库。本轮停止扩样，不手工补 renderer，不放宽旧 Script/Artifact 沙箱。后继零替代调用是事实；同质量前向收益、冷启动摊销与累计净收益尚不可估计。

## 独立评分与质量边界

官方原低层评分器在新的评分副本中运行，未改源码或标准：

| 题目 | Text F1 | Chart type F1 | Color F1 | Layout F1 | 高层视觉 |
| --- | ---: | ---: | ---: | ---: | --- |
| `line_1` | 0.545455 | 1 | 1 | 1 | pending |
| `line_10` | 0.384615 | 1 | 0.967601 | 1 | pending |
| `line_5` | 未评分（无代码/图） | 未评分 | 未评分 | 未评分 | 未评分 |

高层原 judge `gpt-4-vision-preview` 没有在本实验配置，保留原 prompt SHA `38410b6ca93249f66b04f23f768377d742efe685915bd1d87be012d092ccf08e`。未改用 Kouri 自评分或只看三项较高分就宣称质量等价。官方 TextEvaluator 依赖生成源码中 `plt.savefig` 的定位；本轮普通模型用了 `fig.savefig`，已保留原评分类输出而未改写源码求高分。科研视觉质量、数据准确性和统一合格率未完成独立验收。

## 复现、检查与交付

场景入口和最短命令见[README](../../scenarios/chartmimic/README.md)。完成版本基于初始场景提交 `0b3d439`，真实运行另含单密钥读取小修；实际 `trial.py` / `native_tools.ts` 字节 SHA 在每份 `effective.json`，提取诊断新增代码对应 `extract-line1-002`、`extract-line10-001`，均不改变真实求解。旧提取失败 `extract-line1-001` 保留。

本地原始镜像位于 `.local/chartmimic-20261109/snapshot/`，归档 `evidence-complete.tar.gz` SHA `1fbc9c79c0536b5f2aea562640e7693d2b0e7744c016b3f91cfc73a60f40b632`，不包含 dsh credential目录和评分临时副本。另存当时真实使用的四份场景源码 `source-used.tar.gz`，SHA `a81bc180ca9395035d2aca6f6182c1c700901907ebe819c67efd74699fd08a0a`；已复核三份 effective 中的 `trial_adapter` SHA 均匹配该原件。源路径 FileRef 仍保留原Linux路径；本地审阅按该实验根→`snapshot/` 映射，不改写摘要。后续代码为新运行增加独立 source-snapshot，不改变本轮输入或费用。服务、私有原件、旧Store与账本历史未修改。

场景定向检查涵盖任务/答案隔离、禁止角色重叠、路径越界、拒绝未审计 Customized、后继拒绝进入 learner、原图工具与原生图片内容；Linux已完成 SDK 预览、绘图环境和四个原评分器导入、1163份runtime文件摘要复核、两份实际输出的完整低层评分。`npm run smoke` 通过，模型0。

初次本地 `npm test` 在系统Python缺pytest时未启动；换已安装Python3.12环境后全量3042通过/272跳过/1失败，唯一失败为 `/var` 临时路径重定向守卫。该项在真实TMPDIR定向复验通过。单独Node先1644通过/25跳过/25失败；真实TMPDIR后1665通过/25跳过/4失败，其中两项为子Python未继承环境，修正后定向19项通过。

最终在本工作树 `npm ci` 独立安装锁定依赖后再次执行 `npm test`，Python3043通过/272跳过/2失败，Node未继续。两项为临时目录放在仓库 `.local` 内导致“外部路径”负例实际处于允许范围；切换仓库外真实路径 `TMPDIR=/private/tmp` 后两项与本场景5项共7项定向通过。未修改生产路径守卫或测试，保留所有失败日志；没有再把这次分段复验写成一次完整全绿运行。最终独立Node结果在PR及交接中记录。

后续只值得先在原 Artifact 学习器检查 Matplotlib 输出绑定及没有现成文件输入时的模型自主参数化入口，再用独立认证题验证。不得让手写 renderer 进入库冒充自动学习；通过原认证后才补原 Runtime 的普通后继可见/自主绑定接线。完整高层质量与A/C同题对照成立前不主张收益。开发人工、机器与维护投入未计价，Kouri账单实付仍未知。
