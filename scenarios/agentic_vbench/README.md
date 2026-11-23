# AgenticVBench 视频侧 P0 实验适配

本目录提供官方任务 IO、原生图像工具接线和原学习器的证据投影，不另建 Agent 循环、Miner、Store 或 Runtime。
官方任务与素材留在私有实验环境；研究范围为 Assembly 及两项 Sequencing 适用性检查。

```sh
python scenarios/agentic_vbench/preflight.py \
  --official-root "$AGENTIC_VBENCH_ROOT" \
  --trace "$VIDEO_RUN/native-tools.jsonl" \
  --output "$DIAGNOSTIC_OUTPUT/preflight.json"
```

`--trace` 可省略。输出采用排他创建，不覆盖已有诊断。原生工具事件必须来自正常 Harness
执行；预检把成功调用的原始命令交给原 `script_motif_compiler.extract/compile_script` 和
`artifact_motif_compiler.validate_source`，不会伪造边界快照或将静态准入视作认证。
它只读官方题面、环境 recipe、任务调度配置，不读取 Oracle、参考顺序或评分答案。

官方当前目录为 `steps/solve/{instruction.md,tests/}`，而 `BenchmarkHost.trial()` 的
`SkillsBenchTrial` 需要根目录 `instruction.md/tests/`，且当前 ResearchHarness 的
callback 工具只返回文本。不能直接以原图任务已经接入该宿主作结论。
现有私有 `run-video-task.py` 使用原 `create_harness()` 与 TypeScript 原生
`execute/read_image`。`trial.py` 把同一接缝公开为薄场景适配：完整官方题面、
实际图像、正常文件操作及求解结束后才注入的官方评分；不在求解阶段挂载答案。

## 正常执行、学习与后继

正常 Agent 自己决定镜头和程序算法；适配要求实例数据与程序分开，并在原生调用前后
采集有界、真实文件快照。大视频留在同一隔离任务的媒体区域。原 `collect_shell_call`
提取实际执行的程序，`advance_execution_learning` 独立认证后写原 Capability Store。
后继仅获得冻结库及原 `capability_list/capability_call`，原 Runtime 负责实际产物。
求解失败、静态候选或工具成功均不等于合格能力或效率收益。

`learning.py --runtime ... extract` 仅接受有完整事件/文件边界的正常来源，拒绝从后继题学习。
原始边界保持不变；历史快照缺少的空 `command-tmp` 只在逐文件验 SHA 的派生执行副本中
补齐。`certify` 要求不同的合格来源/认证题；准入沿用原 BenchmarkHost 的完成且 reward>0，
这允许部分得分来源，但不能把部分得分写成完整任务成功。最终质量仍由后继独立评价。

原学习链依赖显式研究 Runtime `c2f332b`，主线尚无该完整入口；本目录不复制其实现。
当前Task14冻结Runtime为`a073381`：包含公共参数学习接线、原任务参数证据绑定修复及
严格提案转义兼容，另叠既有Luna传输/记账适配。实际归档与覆盖SHA见各实验
`source-manifest.json`，不能只同步场景文件就宣称完整可运行，也不能在配对中途换版本。

### 独立的清单局部任务

`--component-only --roles scenarios/agentic_vbench/component-roles.json --goal-file ...`
启用单独编号的配置到清单任务。它用实际媒体测量独立核对当前配置、镜头顺序、完整源区间和
连续输出时间线，不评价选片语义，也不把旧视频的零分变为成功。已有正常 Agent 产生的程序
保持冻结；来源重取、不同素材认证和封存后继分别记录。

`learning.py ... certify --admission component` 只接收独立检查通过且绑定实际输入、程序和
交付文件的候选，之后仍走原编译、原生认证和 Store。默认整题准入保持不变。后继两侧使用
同一冻结配置、模型、工具 schema 和质量条件；空 Store 对照也暴露同样的 Capability 工具。
局部能力是否被采用及是否降费须由真实后继对照决定。
新实验的材料准备同时保留原`inputs/media.json`及无损`inputs/media-records.json`数组视图。
后者把实际文件名放在每行的`name`值中，其余测量字段不变，使普通程序可以直接查表，
无需模型重复抄写duration；来源SHA在`media-view-provenance.json`。两侧共享该视图，
不把材料表示改进计为Motif收益；旧冻结运行不覆盖。原精确输入契约不变。
服务器先加载项目 `.local/remote-env.sh`，再在已准备官方素材镜像的隔离环境运行：

```sh
"$SSS_PYTHON" scenarios/agentic_vbench/trial.py \
  --runtime "$GENELOOP_RESEARCH_RUNTIME" --official "$AGENTIC_VBENCH_ROOT" \
  --native-tools src/adapters/research_native_tools.ts \
  --ledger-root "$GENELOOP_EXISTING_LEDGER" --output "$NEW_VIDEO_RUN" \
  --model gpt-6-luna --model-config config/research-gpt-6-luna.json \
  --image geneloop-avb-assembly-task2:20261109 \
  --task 2 --role development --request-recovery --call-model
```

这是付费入口；原费用/请求累计账本不重置。Luna 经原 Harness pi-ai adapter，
wire 为 `reasoning_effort:none`、`max_completion_tokens:128000`，不发送 DeepSeek thinking。
模型配置只在该研究进程生效；其中价格为 OpenAI 官方参考价估算，非 Kouri 账单。
`--request-recovery` 启用原 Harness 的 normal 5 次请求重试，失败、重试和未知费用均保留。
1800 秒为本场景诊断墙钟；后继 Baseline/Reuse 必须采用同一模型、配置和质量条件。
Task2/6/13 的来源、认证及封存后继角色固定在 `roles.json`；不得用后继修库后仍称未见评价。
新Task14对照见`method-roles.json`，900秒/侧；两项原计划Sequencing适用性见
`sequencing-roles.json`，按7段、13段顺序，先完成Task14配对及零模型环境核对再启动。
Sequencing沿用同一入口的`--family sequencing`，无需新增Runner或执行后端。

### 原参数学习与值输入

`learning.py ... parameterize --source "$QUALIFIED_EXTRACTION" --trial "$SOURCE_TRIAL"`
另需`--store --output --ledger-root --model-config --owner`；默认只预览，真实调用加
`--call-model`。该薄适配调用原`learn_pending_parameters`，只接受独立配置到清单检查
通过的正常来源，拒绝封存后继/失败完整视频。`--feedback`可追加实际只读经历证据。
`no_change`原样保留，不以重复提案或手写程序制造新C。

`trial.py --store "$FROZEN_STORE" --artifact-value-inputs`在原工具管理器中启用既有
Artifact JSON值入口；Baseline使用相同开关和原账号空库。文件入口继续保留，Agent自主
选择。`value.output`是原Runtime私有路径（如`/work/outputs/result`），当前容器交付位置
由`export_directory`指定。文件/value入口若引用同一原程序，不能计作两个学习成果。
当前Task14实际采用文件入口，JSON值绑定修复不应被写成该次采用的唯一原因。

目前执行边界：Script 为受限 Python；Artifact 拒绝 `subprocess` 且固定输入为有界 UTF-8
文件；Source 仅支持 TSX/JavaScript 实例化，已有 Remotion 学习/认证依赖真实 TSX 渲染回执。
这些接口均不自动成为 ffmpeg 视频后端。发现不兼容时保留拒绝，不放宽沙箱。

定向检查：

```sh
python -m pytest -q tests/test_agentic_vbench_preflight.py \
  tests/test_artifact_motif_compiler.py tests/test_script_motif_compiler.py
```

结果、费用、来源及继续条件见[实验记录](../../docs/experiments/agentic-vbench-efficiency-20261109.md)，
当前状态见[场景交接](../../docs/handoffs/agentic-vbench.md)。


首次写码要求先把上下文变量集中到配置/输入区，程序开头读取，再写稳定函数；不散落当前值、
不固定镜头数。正常开发修订可用 `--continue-trial "$PRIOR_RUN" --followup "$PRIVATE_FOLLOWUP"`：
只允许同题、同模型、development来源，复制工作文件，保留旧session/产物/事件，使用原SDK
的新会话入口；钉住SDK没有持久会话恢复接口。追加费用仍入同一账本，续修不是独立样本。
反馈只能是允许的开发诊断，不把正确答案或评分器原件送进求解上下文。

正常项目计划范围另见`plan-roles.json`，不把配置项目完成写成官方选片通过。
`plan_evaluation.py --trial "$TRIAL" --extraction "$RAW_EXTRACTION" --checker "$OFFICIAL_GENERIC_CHECKER" --output "$QUALITY"`
检查当前IDs/原测量、manifest与concat的同一视频时钟、真实工具消费和全部配置段的帧对应/完整视频解码。
`--delivery-relative`仅定位Actor实际声明的交付子目录，不搬移旧文件或改原trial。
官方checker只经AST取五个通用帧函数和三个数字常量，绝不执行其score/main/预期顺序。
随后`learning.py --runtime "$RUNTIME" qualify-plan --source "$RAW_EXTRACTION" --report "$QUALITY/qualification.json" --output "$QUALIFIED_EXTRACTION"`
重验数据与所有证据SHA，保留原提取/结果不动。不同Task6以同一冻结源码和检查器完成相同检查后，
沿原`certify --admission component`注册；此路径不新建学习器、执行后端或放宽模块/文件契约。
同一认证项目发生普通媒体恢复时，可用`--media-trial "$SAME_PROJECT_RECOVERY"`
及`--frozen-frame-worker "$FIRST_QUALITY/generic-frame-check.py"`关联质量证据：任务/素材/
配置/测量/源码及两份计划必须一致，恢复实际消费逐SHA核验，帧检查worker字节必须不变。
仍使用首次真实Artifact producer认证，原失败不改、恢复不算另一独立样本；关联不负责挖掘程序。

97ef631将续修工作副本中的旧program-output树归档到媒体区，避免旧视频导致小程序边界不完整；
原工作区/结果/快照不改。历史布局投影保留空目录，fresh output必须是实际尚不存在的目录。

固定决策后执行阶段对照使用 `execution-roles.json`，沿已有 `--component-only
--goal-file --instance-file`（scope=`configured_full_clip_plan_v1`）提供明确的当前剪辑请求。
它借用新的公共素材，不运行/声称原官方选片或排序验收；双方同给定ID顺序、测量和媒体质量门槛，
仅当前认证C目录与空库不同，C可选。具体任务/配置/检查器/库在任何一侧前冻结，后继禁止学习。

预声明的次级repair-inclusive分析可沿原 `--continue-trial --followup` 加
`--baseline-recovery-report` 引用原不合格清单证据。仅同固定执行阶段的空库Baseline、
同goal/task/model/runtime/原始素材和空库snapshot可恢复一次；timeout不得超过原墙钟余额。
原主配对、R原产物和费用不改；恢复费用/请求/耗时累计到同一个B，sealed后继继续禁止学习。
