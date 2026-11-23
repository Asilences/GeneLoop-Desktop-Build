# PPT Agent 当前交接

- 桌面安装与验收见[桌面 PPT 接线清单](ppt-desktop-install.md)。草稿提供构建时完整资源入口，Windows 和 Mac 安装包验收由桌面端接手。

- 更新时间与交接人：2026-11-11，Codex。
- 本次范围：PPT 附件预处理、缓存与交付收尾。明确文字替换走目标页 OOXML，超过 12 页的 PDF 走本地索引和指定页像素，已有同版图像去重。真实制作对照用 PPT162/Paper164。PPT164/Paper166 加入 Windows 解析器兼容和同一文本框内的组合替换收尾，并在隔离实例重启验证。发布候选 PPT165/Paper167 将长 PDF 索引放进 PPT 专属模块，沿用 File 的原 PDF 读取实现和原证书。
- Motif：最终候选的两条发布来源读取 Motif 由在线目录核验。原轨迹零模型重认证后，隔离账号四条试用程序通过重启读取和 Runtime 工具契约验证，覆盖一次整稿预览与三种修订预览。各账号独立管理试用程序。
- 本轮真实验证：新长 PDF 生成和新 PPTX 改页各做一次修复前后同材料对照，四份成品均交付且独立 Judge 通过。首个制作请求从 64–67 秒到 1–2 秒，整体耗时分别下降 26.3% 和 21.9%，制作 39→15 次，已知估费 USD 0.173914308→0.074964936，修复前另有 2 次用量不可估费。可计量缓存命中率 15.73%→34.16%，未命中输入降 57.2%。独立 Judge 4 次、USD 0.024552552，原四条程序重认证新增模型请求 0。最终收尾修复以实际参数和成品做了零模型回放。见[实验记录](../experiments/ppt-input-delivery-20261111.md)。
- 继承与新验证：两批历史材料顺序重认证后，整稿预览和单页修订预览保留，新增两条多页修订预览。独立的生成、编辑两题合计4份PPTX/PDF/PNG均交付，Judge四维均通过。生成优化侧触发3次学习续接，编辑使用 `edit_ppt_native`。两侧各22个制作请求，已知估费B/O为USD0.069762216/0.098759382，各3次异常用量。Judge独立4次/USD0.008931636，学习新增模型请求0。Windows Python37、Linux Python58和Node15项定向通过。
- 分支：`codex/ppt-managed-learning-20261104`，基线 `main` 的 `e2494b0d`。候选提交和 Windows/Ubuntu CI 见 [PR #163](https://github.com/jingyio/GeneLoop/pull/163)。
- 已实现：ppt_deck_engine.ts/contract.ts/tool.ts原生整稿、稳定ID和整数revision改页、同稿补页、整稿来源备注、精确字段错误；共用Office/当前成品/缓存。旧SVG和导入PPTX保留，SVG与JSON工程不能任意互转，仍有真实混合路线未交付负例。
- 学习模块：Python从正常轨迹识别独立并行读取，唯一绑定当前回执、完整集合及实际图像SHA；两种长度归纳逐项读取，第三来源认证。TS沿原执行器续接；保留视觉判断，不是任意Skill编译或手写整稿RSI。
- 真实认证：ppt_flow_9f55843764648345663d8578为build后完整预览读取，ppt_flow_b230f6896c1959db50b2f1d0为patch后1张变化页读取。最终PPT160/Paper162已用原材料重认证，新增模型0；隔离账号内probation，尚未证明普遍收益，未发布为所有新账号默认库。
- 真实材料：L01/L02/C01N完成4/5/6页及同会话只改第2页；非目标XML/备注/像素完全一致。C01N限定原生文字/表格，是格式约束认证材料。采集196请求、配置估费USD2.250969546含全部失败，不计入制作对照，实付未知。
- 首对负例：PPT157的PB01普通52/优化37请求均未交付，估费USD0.703600680、未知usage0；另发现未启用的create_ppt_page被错误要求，导致程序回退。原首对及费用留pilot-v157，不混最终15题、不作为正例认证。
- 最终修复：ppt_workflow_host.ts只列可用工具，程序真实依赖仍核验；无关调用不解析workflow。ppt_master_recovery.ts及dsh_web_tasks.ts允许有工具进展却只叙述计划的未交付任务续接一次，拒绝/澄清/取消/已交付不触发，费用归制作；JSON/SVG导出指令分开。strict未填独立target时保持提交页数，表格分页增页仍拒绝。
- 已验证：Linux完整Node1816 passed/11 skipped、相关Python47 passed、smoke/motif/rsi均exit0。Python运行/测试文件与3282 passed/225 skipped完整回归的SHA一致，仅兼容导出器变化且已重验，没有重复23分钟Python。Windows相关29项通过；Windows Office与Mac实机UAT仍未完成。
- 桌面：local-ppt-deck.mjs及stage-ppt-deck.mjs按需复用同源码，宿主负责目录授权/字体/主题/Office/发布；新增常驻MCP=0，运行时不装包、不调用模型。未自动接入同伴前端。
- 已结束：`ppt-presentbench15-20261111-final-v160`，五领域各3题。B1 实际交付5/15，O 为6/15。含失败和恢复，B1 共1147请求、已知配置估费USD17.390840418，O 为887请求、USD9.940385310，分别有9次、7次用量未知。O 续接5次，66次子读取内部模型请求0。原题、生成版本、学得库和45分钟时限按实验记录冻结，PB01为回归样本。
- 评测：11份成品均尝试独立Judge，8份缺评分内容，3份无法通过结构或证据校验。质量均未知。评审请求11次，已知估费USD0.2535948，另1次估费未知。原结果及可复查的辅助证据已同步至私有实验目录。赛后学习新增模型请求0，两条修订预览程序获结构认证，旧整稿读取未纳入赛后试用库。本批观察及学习材料此后仅供开发与回归。
- 配置/数据：上游commit f2263f5260cf9453d1ad5d3c9a85c55ee3999c70、MIT和原/适配摘要在third_party/dsh-ppt，npm锁定@office-kit/pptx0.21.0。旧 15 题和本轮的输入/轨迹分别位于私有 `.local/ppt-presentbench15-20261111` 和 `.local/ppt-input-delivery-20261111`。服务器目录名仍v156，以本轮冻结清单和生效配置为准。
- 运行定位：既有Linux BASE下ppt-native-deck-engine-v156-20261111，run 9d484b8f52834c44815bac9ca4ba9dd5，端口38213；既有官方Web开发入口launch.py --benchmark-frozen-learning --resume，并非正式发布。先读study-phase.json/queue-state.json/study-client.log，按保存task_id只读恢复，不盲目付费重提。
- 接手下一步：先保留本轮真实结果及旧 15 题失败记录。后续正式合入时用正常流量核对组合文字替换能否直接收尾，继续记录未缓存输入和上游时延。当前可判断本轮本地输入路径改善，上游缓存比例仍需持续观测。
- 权限/费用：真实Kouri deepseek-v4.1-flash/off、393216，原请求/费用限制null，累计账本延续。制作、旧试跑、材料采集、赛后学习和Judge各自记账，实际账单未知。所有失败、恢复和未知用量保留。最终候选验证仅切换隔离实例。
- 回退：PR163的PPT153/Paper155及旧服务不变；PPT154–159和首对失败均保留，不手改旧证书/指针，不覆盖私人原件。源码及匹配兼容库须成套使用。
- 记录：[继承验证与性能诊断](../experiments/ppt-workflow-retention-20261111.md)、[原15题](../experiments/ppt-presentbench15-20261111.md)、[引擎吸收](../experiments/ppt-native-deck-engine-20261111.md)、[实施方案](../experiments/ppt-dsh-engine-adaptation-20261111-plan.md)。
