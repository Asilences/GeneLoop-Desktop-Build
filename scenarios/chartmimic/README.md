# ChartMimic 效率 SI 场景诊断

此目录负责官方任务输入隔离、原 Harness 的一次正常任务、原学习/认证接线及冻结后继对照。当前支持 Direct Mimic 的小规模价值预检，尚未证明同质量效率收益。

## 公共实现复用

- 正常求解：原 `harness_runtime.create_harness()` 和 `CumulativeProposalGate`。工具经公开 `ctx.tools.register()` 原生注册，保留原 Harness 会话、取消和供应商记账。
- 离线提取：`extract.py` 直接调用既有 `execution_learning_bridge.collect_shell_call()`，不生成或改写绘图算法、参数或候选。
- 后续认证与入池：已有 `execution_learning_pipeline.advance_execution_learning(..., backend='artifact_motif')`、`certify-artifact-motifs.mjs` 和 `CapabilityMaterials`。没有候选时不制造认证输入。
- `learn.py` 将真实Artifact候选交给原参数学习、认证及Store；`capability_tools.ts` 冻结原Store的完整library refs与学习描述，当前文件调用原 `artifact_capability_runtime.ts`，可选JSON值调用原 `script_capability_runtime.ts`。空Store Baseline暴露相同四个工具schema。已有C2/C4/line31三程序入原Store；line33完整程序复用但更贵且漏参考线，line35原value初稿成功后仍回退新程序，尚未证明同质效率收益。

已经核对 `BenchmarkHost.trial()`：主线与已查候选都硬绑定 `SkillsBenchTrial` 目录契约及文本 `execute` 回调，不能直接传 ChartMimic 原图；此场景沿其相同的底层 Harness/Gate 薄接线，不另建 Agent 循环。计划所称 `advance_execution_learning()` 不在 main `e2494b0`，存在于干净候选 `c2f332b72997bb82b532ed4f13d0b04eea10df9e`；实际实验将该候选用 `git archive` 放入独立 runtime，全部文件 SHA 另存私有 `source-manifest.json`。本 PR 不复制候选公共实现，也不声称该依赖已合入 main。

## 官方契约与隔离

上游：[ChartMimic](https://github.com/ChartMimic/ChartMimic)，本次核对 commit `92ba5b97b908c607f630c3ffbb5043de9de62b76`，数据使用 `dataset-iclr.tar.gz`。新版子集为 `direct_600/direct_1800/customized_600/customized_1800`，仓库示例仍有 `ori_500` 等旧路径。

Direct 的模型输入是 PNG 和官方 `DirectAgent` 题面中的尺寸，没有表格数据。`prepare.py` 只将 PNG 与格式化题面写入 `solver/`；参考代码单独写入 `evaluation-only/`。元数据 JSONL 自身含 `code`，不能直接装入求解容器。`roles.json` 在运行前冻结学习、认证、后继和负例身份；本代后继不得进入学习。

Customized 的 `EditAgent` 输入是原图和修改指令；官方 `code_interpreter.py` 对 chartedit 还会注入参考代码的 Data Preparation 段。不能将 customized 目标图当作原输入，也不能把注入的参考数据当作模型学得结果。本入口拒绝 Customized，待独立审计该官方执行契约后再扩展。

`native_tools.ts` 的 `read_image` 将原始图像字节送入原 Harness attachment service，场景不进行答案描述、缩放或像素替换。实际请求审计确认 SDK 后续仍会缩放/编码 JPEG：本轮原图 942×710 / 948×710 到模型时分别为 921×694 / 924×692。图片确实进入真实模型请求，但不能声称端到端保持 PNG 原字节。正常命令在断网 Docker 容器中运行，只能看到任务参考图及新工作目录。命令前后按原 `SkillsBenchTrial.capture_learning_boundary` 的 `/work` 命名空间与 1 MB 单文件/8 MB 总量/256 文件界限复制证据；超界标记 incomplete，不能作为完整学习见证。

## 最短复现

原始数据、轨迹和私有配置都放 `.local/`。Linux 先加载已有 `source .local/remote-env.sh`，以下 `python` 使用该环境的 `$SSS_PYTHON`。`RUNTIME` 是已安装锁定 Node/SDK 依赖的现有代码目录，`LEDGER` 必须是原有连续账本目录；不能新建或清零。

```sh
python scenarios/chartmimic/prepare.py --official "$OFFICIAL" --archive "$ARCHIVE" \
  --roles scenarios/chartmimic/roles.json --output "$FROZEN"
docker build -t geneloop-chartmimic:20261109 scenarios/chartmimic
python scenarios/chartmimic/trial.py --runtime "$RUNTIME" --inputs "$FROZEN" \
  --task line_1 --ledger-root "$LEDGER" --output "$NEW_TRIAL"
# 预览后，在另一个全新输出目录显式加 --call-model；私有凭证可用 --env-file 指定。
python scenarios/chartmimic/extract.py --runtime "$RUNTIME" --trial "$TRIAL" --output "$NEW_EXTRACTION"
python scenarios/chartmimic/evaluate.py --official "$OFFICIAL" --frozen "$FROZEN" \
  --trial "$TRIAL" --output "$NEW_EVALUATION"
```

`trial.py` 每次只调用一次 `client.run()`，由原 Harness 自主调工具。没有冻结库时只运行 baseline，不能用它报告 successor reuse。`--program-layout parameter-files-v6` 将数据/样式/布局作为当前JSON输入，在入口集中绑定命名配置；静态API和执行控制流保留Python，禁止JSON代码或通用执行器。实际程序和接口由正常Agent自行生成。`--resume-trial` 只允许继续同一学习题的真实程序/JSON，反馈和旧文件均保存来源，不能借此修复后继后仍称未见。隔离研究可用 `--model-profile luna`；不改变生产模型默认。

`extract.py --runtime` 要求既有普通执行学习候选；缺模块应先核对依赖版本，不能改用手写 Motif。未完成来源只记录跳过原因；后继输入默认在加载 learner 前拒绝。完整命令被拒后，原文件绑定器可对命令中逐字见证的实际源码做诊断，这条路径不产生已入池候选。`learn.py` 对原契约展示schema，不给原本opaque配置对象添加首例固定深层键；原生契约及守卫不变。`evaluate.py` 在新副本中运行官方 `TextEvaluator(use_position=False,use_axs=False)`、`ChartTypeEvaluator`、`ColorEvaluator`、`LayoutEvaluator`；与原 `Code4Evaluation` 实际调用一致。原文件不被评分执行改写。

若已完成配对与评价的正常 Reuse 经历用于下一代，须同时传入 `--next-generation "$NEW_GENERATION" --retirement-evidence "$CLOSED_PAIR_ASSESSMENT"`。`source_use.py`核对原两侧任务、模式、终态与引用哈希，仅允许已完成的Reuse侧成为未来来源，Baseline不进入学习；原角色、结果、分数保持不变。`extract.py`、`learn.py parameterize`和同题`trial.py --resume-trial`共享这一显式接线。它声明来源用途，不代替原程序准入、认证或质量接受。新序列的题目按`roles-sequence-20261110.json`固定，每题在开始前冻结当时的原Store；两侧及评价关闭后，才能从该题Reuse经历更新下一题的库。

官方高层视觉评审使用 `GPT4EvaluationAgent`，六项总分100。旧GPT‑4 Vision已[退役](https://developers.openai.com/api/docs/deprecations)，本轮另获授权采用固定 `gpt-4o-2024-11-20`：保留原agent/LLM类、原rubric及原图在前的图像顺序，temperature .1/top_p .95/max_tokens4096。这是“官方rubric + GPT‑4o 2024‑11‑20替代judge的新评价”，结果独立追加；旧结果的pending不改。line14两侧均获新judge100分，但人工观察发现其漏看蓝线线型差异，保留原分与差异，不能据此宣称完美或严格同质。

参数学习须指定真实已完成学习来源，认证应显式传入同一绘图环境：

```sh
python scenarios/chartmimic/learn.py parameterize --runtime "$RUNTIME" --model-profile luna \
  --observations "$OBSERVATIONS" --source-trial "$LEARNING_TRIAL" \
  --materials-root "$MATERIALS" --owner "$OWNER" --ledger-root "$LEDGER" \
  --render-python "$RENDER_PYTHON" --output "$NEW_PARAMETER_RUN"
# 默认仅预览；实际提案在新目录加 --call-model。--proposal-response 仅重放已有真实模型回复。
python scenarios/chartmimic/trial.py --runtime "$RUNTIME" --model-profile luna \
  --inputs "$FROZEN" --task line_31 --program-layout parameter-files-v6 \
  --capability-catalog "$ORIGINAL_STORE_CATALOG" --capability-owner "$OWNER" \
  --render-python "$RENDER_PYTHON" --ledger-root "$LEDGER" --output "$NEW_REUSE_TRIAL"
# 空库侧省略 --capability-catalog，保留 --expose-capability-api，其他条件一致。
python scenarios/chartmimic/delivery.py --trial "$TRIAL" --output "$DELIVERY_AUDIT"
python scenarios/chartmimic/evaluate.py --official "$OFFICIAL" --frozen "$FROZEN" \
  --trial "$TRIAL" --delivery "$DELIVERY_AUDIT" --output "$NEW_EVALUATION"
```

`delivery.py`按预先固定的最终回答/最后读图/原Runtime回执顺序定位交付，核对PNG/PDF、原源码和实际绑定输入哈希。官方低层评价沿实际native argv槽位绑定当前文件，支持已有多输入程序；评分器本体未改。它不按评分选择成品，也不把一次调用或普通源文件组合记成认证子Motif。

下一序列的启动提示只显示原冻结库的操作/完整适用边界、输入角色、产物菜单及编译器已确认的可选kwargs。完整卡、原约束、原库和缓存源码仍在原`capability-bundle.frozen.json`；`capability_list()`返回菜单，`capability_list({capability_id: "..."})`返回该ID的执行接口：原输入契约、去重后的observed类型及原docstring字段语义；`include_audit: true`返回完整原卡。它不做相关性检索、重新排序或自动选C；带库/空库侧沿相同的可选ID/audit schema。已有JSON value入口启用时，同program/library版本只展示一项操作，保留文件别名，不算新增Motif。减少目录呈现负担是场景改动，本身不算Motif收益，旧冻结对照不回写。

独立输入绑定通过认证阶段专属`submit_binding`直接提交各真实角色的JSON值，复用Harness的原JSON schema校验并序列化为已声明文件；不让模型再写保存JSON的Python/转义脚本。错误正常返回原会话，由Actor自己纠正；工具不填默认值、不推断视觉参数、不运行待认证程序。单文件接口沿用`/work/plot-spec.json`；若原编译接口确有多个JSON角色，接口卡的`binding_files`及`runtime_input_schemas`按真实槽位列出角色、`/work/*.json`路径和原契约。原完整接口与实际工具调用/文件SHA保留，认证器复制原样当前文件到输入域，仍由原契约匹配各槽位。该工具不进入后继对照，两侧仍使用相同的原四工具条件。

新高层评审在隔离环境安装官方SDK版本 `openai==1.2.0 httpx==0.27.0 PyPDF2==3.0.1`，使用含 `config/research-chartmimic-judge.json` 及对应Gate修复的独立runtime：

```sh
python scenarios/chartmimic/judge.py --runtime "$JUDGE_RUNTIME" --official "$OFFICIAL" \
  --reference "$REFERENCE_PNG" --generated "$DELIVERED_PNG" --python "$JUDGE_PYTHON" \
  --ledger-root "$LEDGER" --env-file "$PRIVATE_ENV" --output "$NEW_JUDGE_PREVIEW"
# 预览不请求API；固定两侧图片哈希、顺序和相同配置后，在新目录加 --call-model。
```

独立judge沿原累计Gate，SDK不加reasoning/thinking字段，单次尝试、180秒请求超时，原响应和用量保留。参考估费取[固定模型配置](https://developers.openai.com/api/docs/models/gpt-4o)，供应商实付未知。API、SDK环境或模型变化使用新实验身份。

Docker 使用 Python 3.11，关键绘图/低层评分包按官方 `environment.yaml` 固定；不是官方整个 Python 3.9 conda 环境的逐项复刻。额外间接依赖随 image ID 与 `pip freeze` 保存，字体差异需单独记录。

首轮结果见[实验记录](../../docs/experiments/chartmimic-efficiency-si-20261109.md)，参数化、原认证与后继的续调证据见[参数文件记录](../../docs/experiments/chartmimic-parameter-files-20261109.md)，当前任务见[交接](../../docs/handoffs/chartmimic.md)。

原Store可用既有`BenchmarkScriptMaterials(..., artifact_value_inputs=True).catalog()`只读暴露已认证程序的原生JSON value视图；`capability_call`的`values.input0/input1`直接绑定当前JSON，原Runtime导出真实输入侧车、原源码及成品，不需要另写保存JSON的脚本。图像判断和参数选择仍由正常Agent完成。每次渲染/改参须用新的未占用输出目录，实际最终交付由原`delivery.py`核对。请求归因、共享字段消费、零模型负担对照及待审真实复测方案见[调用负担诊断](../../docs/debug/chartmimic-request-burden-20261110.md)。
