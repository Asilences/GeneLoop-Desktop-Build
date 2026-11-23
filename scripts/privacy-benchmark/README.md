# 公共脱敏模块冻结评测

当前修复版源码为`bd0ba90c`，使用官方spaCy3.8.18及匹配依赖，规格为`env-r5-repair-v5.json`。旧R5的3.8.7状态污染已复现并停止，9,634条部分结果保留，不当作完整成绩。`protocol-r5-repair-default.json` / `protocol-r5-repair-candidate.json`和对应两个`credential-budget-r5-repair-*.json`固定相同依赖下的默认规则与附加模型对照；输入、模型权重、类别、识别和采用门槛不变，不把依赖升级的效果归给新检测器。

修复版先用`CANDIDATE_PYTHON`运行默认组合，再运行候选；该变量指独立验证通过的新解释器。先按本页隔离要求设置Home/临时目录、固定Gitleaks、只读输入及评测依赖，`PYTHONPATH`含应用和本目录。以下输出都须新建，串行重基准后再运行完整工程检查：

```bash
unset SSS_RSI_PRIVACY_CANDIDATE_CONFIG SSS_RSI_PRIVACY_CANDIDATE_SHA256
"$CANDIDATE_PYTHON" "$DRIVER/run_pii.py" --root "$INPUT_ROOT" --config "$DRIVER/protocol-r5-repair-default.json" --output "$NEW_DEFAULT_PII" --workers 16
"$CANDIDATE_PYTHON" "$DRIVER/run_official_pii.py" --repo "$APP_ROOT" --root "$INPUT_ROOT" --config "$DRIVER/protocol-r5-repair-candidate.json" --settings "$CANDIDATE_SETTINGS" --baseline-results "$NEW_DEFAULT_PII" --output "$NEW_CANDIDATE_PII" --workers 16
"$CANDIDATE_PYTHON" "$DRIVER/prepare_official_credential_scans.py" --repo "$APP_ROOT" --root "$CRED_DATA_ROOT" --scoring "$CRED_SCORING_ROOT" --output "$NEW_NATIVE_RESULTS"
mkdir "$NEW_DEFAULT_PRIOR" "$NEW_CANDIDATE_PRIOR"
: > "$NEW_DEFAULT_PRIOR/module-file-records-private.jsonl"
: > "$NEW_CANDIDATE_PRIOR/module-file-records-private.jsonl"
"$CANDIDATE_PYTHON" "$DRIVER/run_credentials_bounded.py" --root "$CRED_DATA_ROOT" --config "$DRIVER/protocol-r5-repair-default.json" --method "$DRIVER/credential-budget-r5-repair-default.json" --prior-output "$NEW_DEFAULT_PRIOR" --scan-output "$NEW_NATIVE_RESULTS" --output "$NEW_DEFAULT_CREDENTIALS"
export SSS_RSI_PRIVACY_CANDIDATE_CONFIG="$CANDIDATE_SETTINGS"
export SSS_RSI_PRIVACY_CANDIDATE_SHA256="$(sha256sum "$CANDIDATE_SETTINGS" | cut -d' ' -f1)"
"$CANDIDATE_PYTHON" "$DRIVER/run_official_credentials.py" --root "$CRED_DATA_ROOT" --config "$DRIVER/protocol-r5-repair-candidate.json" --method "$DRIVER/credential-budget-r5-repair-candidate.json" --prior-output "$NEW_CANDIDATE_PRIOR" --scan-output "$NEW_NATIVE_RESULTS" --output "$NEW_CANDIDATE_CREDENTIALS"
SSS_PYTHON="$CANDIDATE_PYTHON" node "$DRIVER/check_official_entries.mjs" "$APP_ROOT" "$NEW_ENTRY_RESULTS"
```

两个凭证模式均16worker/120秒、空prior；原生报告在本次真实重扫后供两种模式共同评分，不使用R1–R5旧命中。默认PII沿用原直接评测器，候选使用120秒联合观察器，二者并发均16；耗时/未知数不作为唯一检测器差异的因果证据。`compare_frozen_runs.py`对相同完成/准入子集另算得失与残留，未知和异常单列。修复后的137条原故障顺序及独立环境回执也须保存；不得以导入、定向或历史R4回归冒充最新完整通过。

R5增加默认关闭的官方Privacy Filter原始权重与CredSweeper适配，设计/版本见[候选说明](../../docs/research/rsi/privacy-official-tools-r5.md)。实现`0ddc7f2d`、评测配置冻结`5d7698e2`；配置为`protocol-r5.json` / `credential-budget-r5.json`。600条历史PII与24组语义控制先检查候选，再用同一配置评测全部13000条PII及11030个CredData文件；已见数据和上游训练重叠均不能称独立验证。候选检查的金标外遮盖/正文保留门槛已经失败，仍不设为默认。

复现R5须先准备通过`witness_official_tools.py`的独立解释器`CANDIDATE_PYTHON`、官方离线资产及私有宿主配置`CANDIDATE_SETTINGS`。配置绝对路径和实际字节SHA须配对；不是给任务增加可控开关。`APP_ROOT`指冻结检出，`DRIVER`指相同版本的本目录，`R4_PII`指已保留的R4逐条结果。`PYTHONPATH`依次包含应用、评测脚本、冻结评测依赖及原CredData源码。以下所有输出路径必须不存在，依次执行，不覆盖旧结果：

```bash
"$CANDIDATE_PYTHON" "$DRIVER/run_official_pii.py" --repo "$APP_ROOT" --root "$INPUT_ROOT" \
  --config "$DRIVER/protocol-r5.json" --settings "$CANDIDATE_SETTINGS" \
  --baseline-results "$R4_PII" --output "$NEW_PII_RESULTS" --workers 16
"$CANDIDATE_PYTHON" "$DRIVER/prepare_official_credential_scans.py" --repo "$APP_ROOT" \
  --root "$CRED_DATA_ROOT" --scoring "$CRED_SCORING_ROOT" --output "$NEW_NATIVE_RESULTS"
mkdir "$NEW_PRIOR"
: > "$NEW_PRIOR/module-file-records-private.jsonl"
export SSS_RSI_PRIVACY_CANDIDATE_CONFIG="$CANDIDATE_SETTINGS"
export SSS_RSI_PRIVACY_CANDIDATE_SHA256="$(sha256sum "$CANDIDATE_SETTINGS" | cut -d' ' -f1)"
"$CANDIDATE_PYTHON" "$DRIVER/run_official_credentials.py" --root "$CRED_DATA_ROOT" \
  --config "$DRIVER/protocol-r5.json" --method "$DRIVER/credential-budget-r5.json" \
  --prior-output "$NEW_PRIOR" --scan-output "$NEW_NATIVE_RESULTS" --output "$NEW_CREDENTIAL_RESULTS"
SSS_PYTHON="$CANDIDATE_PYTHON" node "$DRIVER/check_official_entries.mjs" "$APP_ROOT" "$NEW_ENTRY_RESULTS"
```

PII评测只在同一条观测的原生/内核/公共准入视图之间复用刚计算的相同原文预测，不复用其他记录、字段、规范化字符串或旧运行。该观察器节省重复测量开销；其模块耗时不能当作独立产品时延。`check_official_entries.mjs`另以真实公共Web结算投影器和离线CLI验证Paper、PPT、Coding三类合成输入，不启用观测器；Web首条包含冷启动、后续复用有界worker，离线逐次冷启动。没有启动HTTP服务、桌面或付费模型。原始事件摘要、准入/拒绝、输出、任务要求与邮箱残留逐项核对，失败仍写回执并退出1。其他场景公共接线由完整回归另核对，不能把这9对样本当作全场景真实任务验收。

原生OPF八标签和项目七标签单列；日期仍按冻结策略处理，不因benchmark标签而扩大禁止类别。CredSweeper原生CLI按原文件路径和默认过滤扫描，与公共模块的内存文本准入不同，文件命中率不能当作实体召回。金标外字符遮盖是误删代理，也可能包含未标注PII；没有人工核验时不把全部金标外遮盖直接叫真实误删。

R5冻结之后增加两项补充检查，均不改检测器、类别或采用门槛。`audit_prediction_components.py`只读两侧逐条预测，核对新增金标外遮盖与原生八标签有效操作的重叠，并另报旧遮盖字符丢失。有效操作已经过渲染，不能据此完全拆分原始模型与渲染器责任。默认与候选的逐条PII结果都必须完整存在，输出使用新路径：

```bash
"$CANDIDATE_PYTHON" "$DRIVER/audit_prediction_components.py" \
  --previous-pii "$NEW_DEFAULT_PII" --current-pii "$NEW_CANDIDATE_PII" --output "$NEW_COMPONENT_AUDIT"
```

`check_all_scene_wiring.mjs`在重计算结束后分别以默认/候选检查6个已注册场景及聊天、Coding、未来MCP共9组。输入包含用户文字、嵌套工具参数、工具结果和模型回复；核对Web结算、SDK/离线导入操作、最小共享投影、工具节点/任务要求及原件摘要。它复用真实公共worker，不使用benchmark预测缓存；3场景9对离线CLI冷启动检查仍由上面的`check_official_entries.mjs`单独完成。默认模式先在子shell取消附加模型配置；候选模式继承已成对核验的宿主配置。所有输出目录必须不存在：

```bash
(
  unset SSS_RSI_PRIVACY_CANDIDATE_CONFIG SSS_RSI_PRIVACY_CANDIDATE_SHA256
  SSS_PYTHON="$CANDIDATE_PYTHON" node "$DRIVER/check_all_scene_wiring.mjs" "$APP_ROOT" "$NEW_ALL_SCENE_DEFAULT" default
)
SSS_PYTHON="$CANDIDATE_PYTHON" node "$DRIVER/check_all_scene_wiring.mjs" "$APP_ROOT" "$NEW_ALL_SCENE_CANDIDATE" candidate
```

这两项属于事后归因/入口接线检查，不能当独立未见评价、真实HTTP/桌面/接收端验收或性能对照。回执与每个case的失败均保留；执行脚本结束不等于质量通过。

R4新增 `protocol-r4.json` / `credential-budget-r4.json`，核对公共运行时策略语义SHA256，保留原数据/金标/类别及32个PII、16个凭证worker/120秒预算。PII、凭证、完整回归分时执行，所有模块调用用空prior重新运行；最终检测内核与导入编排版本分别记录，见[R4记录](../../docs/experiments/privacy-benchmark-20261108-r4.md)。下方R1–R3命令保留为历史复现，不覆盖原目录。

R4最短重放如下：`APP_ROOT` 为独立的冻结检出 `a4923292`，`DRIVER` 为本PR的评测脚本目录，`INPUT_ROOT` / `CRED_DATA_ROOT` 指原已核验数据，`EVAL_DEPS` 包含冻结评测依赖。`R4_NATIVE` 必须先在新目录用固定Gitleaks真实扫描并生成报告及核验回执，不能复制旧R1–R3命中作新扫描。所有 `NEW_*` 路径必须不存在，Home/临时目录沿本节隔离要求单独配置。

```bash
set -euo pipefail
source "$APP_ROOT/.local/remote-env.sh"
export PYTHONPATH="$EVAL_DEPS:$APP_ROOT" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
"$SSS_PYTHON" -m unittest discover -s "$DRIVER" -p 'test_*.py' -v
"$SSS_PYTHON" "$DRIVER/run_pii.py" --root "$INPUT_ROOT" --config "$DRIVER/protocol-r4.json" --output "$NEW_PII_RESULTS" --workers 32
mkdir "$NEW_PRIOR"
: > "$NEW_PRIOR/module-file-records-private.jsonl"
"$SSS_PYTHON" "$DRIVER/run_credentials_bounded.py" --root "$CRED_DATA_ROOT" --config "$DRIVER/protocol-r4.json" --method "$DRIVER/credential-budget-r4.json" --prior-output "$NEW_PRIOR" --scan-output "$R4_NATIVE" --output "$NEW_CREDENTIAL_RESULTS"
"$SSS_PYTHON" "$DRIVER/run_semantics.py" --config "$DRIVER/protocol-r4.json" --cases "$DRIVER/semantic-cases-r1.json" --output "$NEW_SEMANTIC_RESULTS"
```

R4采用决定在看到全量成绩前冻结：保留成熟上下文模式候选，`GLiNERRecognizer`的PERSON-only研究配置因金标外遮盖及120项任务要求门槛失败而不采用，不加入产品依赖。复核用 `run_model_candidates.py --candidate gliner_person --config model-person-r4.json`；独立模型环境、离线权重及输入参数沿用下方候选命令，输出必须新目录。它用官方分块接口和明确容量/全文覆盖检查；未知不按截断前缀计分。`score_model_candidates.py --baseline-results <r4-cohort-records> --baseline-name r4_context`将金标交独立评分过程，保留原R2参数兼容。候选并集是文本层重放，不是完整模块默认集成。

`diagnose_credentials.py`对已知残留文件按固定seed/hash抽样复核，只公开类别/长度等聚合；不能把诊断样本当总体成绩，也不能将残留标注行当不同秘密。`compare_frozen_runs.py`在全量完成后对相同金标核对旧完整遮盖的得失、同准入残留、拒绝/未知迁移及原生预测漂移，不重调检测器。示例参数为 `--previous-pii ... --current-pii ... --previous-credentials ... --current-credentials ... --output <new-json>`；输入目录仍为私有。

R3 产品固定 `ea819fc6`，只补原文姓名识别，并保留原有规范化命中、过滤与拒绝。使用 `protocol-r3.json` / `credential-budget-r3.json` 在新输出目录重新调用全部样本；R1/R2 不覆盖。规则归因和独立解释器的成熟识别器对照见 [R3 诊断](../../docs/experiments/privacy-diagnosis-20261108-r3.md)。`policy-scope-v1.json` 仅固定评价范围，不替代公共运行时字段契约。

[R3完整结果与核验](../../docs/experiments/privacy-benchmark-20261108-r3.md)另记录运行时配置修复 `4f6adedb`、基准结束后的完整复验和先前失败。在相同已核验输入/原生扫描上最短重放如下；变量均指向隔离目录，输出/prior必须新建，先在应用检出加载私有环境。原生扫描的配置、输入规范路径与 `data_digest` 必须核验，不能将缺失报告写成空结果。

```bash
set -euo pipefail
source "$APP_ROOT/.local/remote-env.sh"
export PYTHONPATH="$EVAL_DEPS:$APP_ROOT" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
"$SSS_PYTHON" "$DRIVER/run_pii.py" --root "$INPUT_ROOT" --config "$DRIVER/protocol-r3.json" --output "$NEW_PII_RESULTS" --workers 32
mkdir "$NEW_PRIOR"
: > "$NEW_PRIOR/module-file-records-private.jsonl"
"$SSS_PYTHON" "$DRIVER/run_credentials_bounded.py" --root "$CRED_DATA_ROOT" --config "$DRIVER/protocol-r3.json" --method "$DRIVER/credential-budget-r3.json" --prior-output "$NEW_PRIOR" --scan-output "$R3_NATIVE" --output "$NEW_CREDENTIAL_RESULTS"
"$SSS_PYTHON" "$DRIVER/run_semantics.py" --config "$DRIVER/protocol-r3.json" --cases "$DRIVER/semantic-cases-r1.json" --output "$NEW_SEMANTIC_RESULTS"
```

本轮按配置并发执行PII/凭证以保留原方法，运行时回归也曾与基准重叠，性能比较受负载干扰；最终工程复验与入口检查在基准结束后顺序完成。复现时将工程回归与这些大规模数据调用分开，不靠延长120秒或覆盖旧输出求通过。`check_entries.mjs` 对不一致、原件变化或固定样本的预期准入不符返回非零；仅退出0不替代逐项回执核验。

候选研究不安装到产品解释器。先按已保存的候选依赖清单准备独立 CPU 环境和经过固定来源摘要核验的 safetensors/config/tokenizer；不下载仓库代码或 pickle 权重。分别运行 GLiNER 与 OpenMed，金标不传给检测器：

```bash
"$SSS_PYTHON" "$DRIVER/prepare_model_inputs.py" --root "$INPUT_ROOT" \
  --protocol "$DRIVER/protocol-r2.json" --comparison "$DRIVER/model-comparison-r3.json" \
  --semantics "$DRIVER/semantic-cases-r1.json" --output "$NEW_PRIVATE_INPUTS"
# CANDIDATE_PYTHON 指向相应隔离解释器；GLiNER 与 OpenMed 的 Transformers 版本不同。
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$CANDIDATE_PYTHON" "$DRIVER/run_model_candidates.py" \
  --models "$VERIFIED_MODELS" --config "$DRIVER/model-comparison-r3.json" \
  --inputs "$NEW_PRIVATE_INPUTS/inputs-private.jsonl" --candidate gliner --output "$NEW_GLINER_RESULTS"
# 使用 OpenMed 解释器，另一次调用选择 --candidate openmed 和新的独立输出目录。
"$SSS_PYTHON" "$DRIVER/score_model_candidates.py" --config "$DRIVER/protocol-r2.json" \
  --inputs "$NEW_PRIVATE_INPUTS/inputs-private.jsonl" --gold "$NEW_PRIVATE_INPUTS/gold-private.jsonl" \
  --semantic-controls "$NEW_PRIVATE_INPUTS/semantic-controls-private.json" --r2-results "$R2_PII_RESULTS" \
  --candidate-results "$NEW_GLINER_RESULTS" "$NEW_OPENMED_RESULTS" --output "$NEW_AGGREGATE_JSON"
```

`VERIFIED_MODELS` 的 `gliner/`、`backend/`、`openmed/` 各保存固定官方 API `source-metadata.json` 和所需文件；运行器再次核对官方 Git blob/LFS 摘要与比较配置中的 revision。模型容量不足列为未知；不得将缺失预测当作安全或用截断前缀评分。600 条来自已见过的回归数据，开发/确认分组不提供未见保证。纯模型和 R2 合并结果仅作文本层研究，不代表产品已切换；本轮直接合并造成正文额外遮盖，尚未采用。

R1 产品规则固定 `68a4e4d7`，结果见 [R1 实验记录](../../docs/experiments/privacy-benchmark-20261107-r1.md)。R2 使用修复后的 `d832be12` 和 `protocol-r2.json` / `credential-budget-r2.json`，根据 R1 错误开发，因此属于回归评测，不是新的未见评价。本目录只提供离线评测适配、配置和检查，没有新训练的 PII 模型。

## 上游工具与数据

- 识别/替换：[Microsoft Presidio](https://github.com/microsoft/presidio) 2.2.365、中英文 small 模型 3.8.0；凭证：[Gitleaks](https://github.com/gitleaks/gitleaks) 8.30.0。R1–R4和旧R5使用spaCy3.8.7；当前R5修复版固定3.8.18及完整兼容依赖，不能混用成绩。产品依赖由根目录 `requirements-rsi-privacy.txt` 管理。
- 实体评分：[nervaluate](https://github.com/MantisAI/nervaluate) 1.2.1，MIT，复用 SemEval strict/exact/partial/type 及每类分数，不另写 F1。原拟用的 Presidio Research 0.3.2 会额外引入 Pandas 3/Transformers 5 等未冻结依赖，因此未安装到推理环境；这次换用独立评分依赖，原环境实际 NumPy 2.4.6 保持不变。
- 凭证评分：固定 [Samsung/CredData](https://github.com/Samsung/CredData/tree/86a918283f086baf9ca896a892519cd8462dfe0a) 的 `read_meta`、`move_files`、`obfuscate_creds(noise=0)`、`Result`。仓库代码/元数据 Apache-2.0；来源文件保留各自许可，原文件及逐条报告不进 Git。
- 中文：[PII Bench ZH](https://huggingface.co/datasets/wan9yu/pii-bench-zh)，正式 5000/聊天 3000；英文：[Gretel PII Masking EN v1](https://huggingface.co/datasets/gretelai/gretel-pii-masking-en-v1)，官方 test 5000；两者均为 Apache-2.0 合成数据。版本和 SHA256 见 `protocol-r1.json`。
- `duckdb` 只读 Parquet，不升级冻结推理环境的 NumPy；评分依赖与 Linux CPython 3.12 wheel 摘要见 `requirements.txt`、`evaluation-deps-lock.json`。

## 最短复现流程


R2 的最短重放在相同已核验输入上使用新输出目录：应用检出 `d832be12`，本目录评测器检出 `ca083357`；`PYTHONPATH` 必须将应用检出放在其他项目源码之前。本轮服务器独立根、完整命令/方法摘要和回归收集清单见 [R2 正式记录](../../docs/experiments/privacy-benchmark-20261107-r2.md) 的核验回执；以下变量指向隔离路径。

```bash
# DRIVER 为 ca083357 的本目录；R2_NATIVE 为本轮已重扫核验的私有原生报告目录。
# R2_NATIVE 中须有 gitleaks-modern-private.json 和 credential-frozen-snapshot.json。
# dir 输入须先 realpath 解析 CredData-scoring/data，避免跳过 symlink；
# 原生扫描 exit 1 表示命中，其他错误不得当成空结果。先核验 data_digest。
"$SSS_PYTHON" "$DRIVER/run_pii.py" --root "$EVAL_ROOT" --config "$DRIVER/protocol-r2.json" --output "$EVAL_ROOT/results/pii-r2-new" --workers 32
mkdir "$EVAL_ROOT/empty-prior-new"
: > "$EVAL_ROOT/empty-prior-new/module-file-records-private.jsonl"
"$SSS_PYTHON" "$DRIVER/run_credentials_bounded.py" --root "$EVAL_ROOT/CredData" --config "$DRIVER/protocol-r2.json" --method "$DRIVER/credential-budget-r2.json" --prior-output "$EVAL_ROOT/empty-prior-new" --scan-output "$R2_NATIVE" --output "$EVAL_ROOT/results/credentials-r2-new"
"$SSS_PYTHON" "$DRIVER/run_semantics.py" --config "$DRIVER/protocol-r2.json" --cases "$DRIVER/semantic-cases-r1.json" --output "$EVAL_ROOT/results/semantics-r2-new.json"
```

这组命令重跑模块，不表示再次执行原生扫描。重新扫描须用固定 Gitleaks 在新目录生成报告，记录完整参数、规范输入路径、二进制/报告摘要、墙钟及全部输入摘要；不要重新准备或改写已经混淆的数据。R1 旧 wrapper 审计在 R2 中只作历史引用。下方保留 R1 准备与未限时尝试的原步骤，不与 R2 空 prior 调用混用。

入口补充检查与检测 benchmark 分开运行：使用当前分支的 `check_entry_boundaries.py --code-root "$APP_ROOT" --output "$EVAL_ROOT/results/entry-boundaries-new"`（项目 Python）及 `node check_construction_export.mjs "$APP_ROOT" "$EVAL_ROOT/results/construction-export-new"`。10 项只验证研究/公开出口的接线，原生脱敏工具保持真实，模型/产物装配替身与合成 seed/registry 的范围见正式回执；不计入 benchmark 分母或完整测试收集数。


在独立代码检出、Home、依赖及输出目录运行。先按项目约定加载私有 `remote-env.sh`，准备本地 Presidio 模型和固定 Gitleaks；不要加载生产服务配置或用户原始轨迹。下列路径变量都指向本次独立评测目录。

```bash
source .local/remote-env.sh
export HOME="$EVAL_ROOT/home"
export PYTHONPATH="$EVAL_ROOT/deadline-deps:$EVAL_ROOT/deps:$PWD"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export CRED_DATA_CODE_ROOT="$EVAL_ROOT/CredData"
"$SSS_PYTHON" -m pip install --require-hashes --no-deps --target "$EVAL_ROOT/deps" -r scripts/privacy-benchmark/requirements.txt
"$SSS_PYTHON" -m pip install --require-hashes --no-deps --target "$EVAL_ROOT/deadline-deps" -r scripts/privacy-benchmark/requirements-deadline.txt
"$SSS_PYTHON" -m unittest discover -s scripts/privacy-benchmark -p 'test_*.py' -v
"$SSS_PYTHON" scripts/privacy-benchmark/run_pii.py --root "$EVAL_ROOT" --config scripts/privacy-benchmark/protocol-r1-evaluator2.json --output "$EVAL_ROOT/results/pii" --workers 32
"$SSS_PYTHON" scripts/privacy-benchmark/prepare_creddata.py --root "$EVAL_ROOT/CredData" --workers 8
# 若 GitHub 归档遗漏 export-ignore 文件或截断大树，恢复同提交的 blob，核验摘要后再继续。
"$SSS_PYTHON" scripts/privacy-benchmark/recover_creddata_files.py --root "$EVAL_ROOT/CredData"
"$SSS_PYTHON" scripts/privacy-benchmark/run_credentials.py --root "$EVAL_ROOT/CredData" --config scripts/privacy-benchmark/protocol-r1.json --method scripts/privacy-benchmark/credential-protocol-r1.json --output "$EVAL_ROOT/results/credentials" --workers 16
"$SSS_PYTHON" scripts/privacy-benchmark/run_semantics.py --config scripts/privacy-benchmark/protocol-r1.json --cases scripts/privacy-benchmark/semantic-cases-r1.json --output "$EVAL_ROOT/results/semantics.json"
```

`EVAL_ROOT` 下需事先放入三个 PII 文件和解压后的固定 CredData 源码。中文文件名/Gretel Parquet 名称必须与配置相同；先运行 `run_pii.py --audit-only` 核验全文和跨度。Gretel 的实体列表可能使用 Python 字面量编码，仅用 `ast.literal_eval` 解析数据，不执行代码。精确定位原始值的全部出现位置，不 trim、不改金标；无法定位、多标签、重复和重叠均单列。

`prepare_creddata.py` 若发现缺失会拒绝准备，不调用上游会重命名/排除金标的分支。恢复后 `run_credentials.py` 从原件重新复制并调用上游混淆；始终保留原 337 份 CSV 和哈希。不对下载的来源代码执行安装或运行，不尝试验证凭证是否有效。

**凭证大 JSON 的执行边界：** `run_credentials.py` 是没有总体 deadline 的 Python 直调观测，不应假定它一定及时结束。本轮已保存这一尝试的部分结果；最终另外使用冻结的 120 s 评测预算完成遍历。预算参考现有 TypeScript worker，但 warm pool 不等于在线每次冷启动，不能据此声称所有 Web/离线大文件行为完全相同。

控制器复用 [Pebble](https://pebble.readthedocs.io/en/latest/) 5.2.1（LGPL），只装入独立评测依赖，不是产品运行依赖。已返回、同规则同数据且耗时不超过 110 s 的观测可复用；其余重新评测。超时和执行错误的 `accepted` 为 `null`，是未知结果，不能计作隐私拒绝、实体 TP 或安全通过；完成子集矩阵与全量分母分开报告。

在已准备的相同数据和原生扫描报告上续跑，输出目录必须换名：

```bash
"$SSS_PYTHON" -m pip install --require-hashes --no-deps --target "$EVAL_ROOT/deadline-deps" -r scripts/privacy-benchmark/requirements-deadline.txt
export PYTHONPATH="$EVAL_ROOT/deadline-deps:$EVAL_ROOT/deps:$PWD"
"$SSS_PYTHON" scripts/privacy-benchmark/run_credentials_bounded.py --root "$EVAL_ROOT/CredData" --config scripts/privacy-benchmark/protocol-r1.json --method scripts/privacy-benchmark/credential-budget-r1.json --prior-output "$EVAL_ROOT/results/credentials-r1-execution2" --scan-output "$EVAL_ROOT/results/credentials-r1" --output "$EVAL_ROOT/results/credentials-r1-budget120-new"
```

本轮实际的两个输入目录分别保存已返回观测和已完成的原生 Gitleaks 扫描。若规则或输入变更，须新实验 ID 并禁用旧记录复用，不能把旧输出冒充新规则实测；全量新调用可提供一个只含空 `module-file-records-private.jsonl` 的独立 prior 目录。

最终 PII 评分使用 `protocol-r1-evaluator2.json`。原 `protocol-r1.json` 保留给凭证/语义检查复用类型映射和模型配置，其中旧 mask 坐标方案不用于最终 PII 成绩。实际传输配置与仓库 LF 配置如存在换行差异，结果回执同时记录字节摘要和 JSON 语义摘要。

## 指标边界

- 原生 Presidio 使用相同中英文 NLP、0.4 阈值和原生 recognizer；邮箱使用随包后缀表，关闭联网更新。公共文本层使用实际 `anonymize_text`，不向检测器输入金标。观测官方 Anonymizer `_operate` 的替换前坐标，按 Python Unicode 字符计数，再将半开区间转换为 nervaluate 的闭区间；私有接缝仅用于离线观测，固定版本和签名，不改变调用或输出。首个 mask 适配在重叠类型时长度假设失效，整次结果弃用并保留失败记录。
- 原生实体标签统一映射，但未支持标签保留在全标签评分，另报当前文本类型支持子集。full/partial、字符遮盖和实体完整遮盖分别报告；partial 命中不等于隐私完整移除。
- 固定扁平映射没有按实测结果合并原生 `URL`/`ORGANIZATION`/`UUID` 等层级标签；strict 分数有类型粒度限制。主要隐私比较使用不区分预测类型的完整遮盖，F1 分差不能直接等同于少泄漏了多少身份。
- 完整 `learning_view({text: 原文})` 分开报告拒绝、错误和准入后的实体值字面残留。拒绝不是实体 TP；字面残留是诊断，不能证明重新识别风险为零。JSON 内容有字段提示时会在同一公共入口解析，而识别层分数保持独立。
- CredData 当前旧 Gitleaks wrapper 未传 Category，而原 checker 要求 Category 相等。保留原 wrapper 的兼容性审计，不能将其全零分当作新版 Gitleaks 的真实表现。主比较使用已标注的精确行区间/文件，T 为阳性、纯 F 为阴性，X 不确定项排除并计数，公式复用上游 `Result`。未标注命中单列，不能全部当 FP；文件拒绝率不能冒充实体召回率。
- 非 PII 原文片段保留与 `semantic-cases-r1.json` 的公式/协议等检查都是代理指标。`check_entries.mjs` 对固定公开样本运行真实 Web 结算投影器与离线 CLI，检查输出、拒绝和原件摘要；未启动 HTTP 服务、未调用模型，不代表桌面 UAT 或真实 RSI 后继收益。
- 识别层时延含替换前坐标的轻量观测；完整模块按实际内核调用计时，Web/离线 worker 冷启动单列。并行压力下的延迟不能当作单用户生产 SLA。
- 失败尝试及资源探测保留在私有目录，正式结果不混入未完成记录。看过错误后改规则须启用新版本/实验 ID；R1 冻结后没有调参，R2 根据 R1 错误开发后另行冻结，不称未见评价。

R2 保持相同数据、标签映射、模型、阈值和成熟评分器。凭证使用空 prior，所有 11030 个模块调用重新执行，仍为 16 worker / 120 s；原生 Gitleaks 也重新扫描并核对命中位置。PII 仍为 32 worker。配置中的 `module_residual_by_gold_type` 仅在完整模块返回后按现有字面残留定义分组计数，不向检测器传入金标，不改变 R1 默认输出或 F1 口径；总量与分组加和另行核验。
# R7修复验证

运行时配置须指向环境目录的真实路径，例如`SSS_PYTHON="$(realpath "$PRIVACY_CPU_ENV")/bin/python"`，并设置相同的`SSS_PURE_CODE_PYTHON`。不要对`bin/python`本身做`realpath`后丢失venv；不要解除沙箱的真实目录或版本守卫。先加载隔离检出的`.local/remote-env.sh`，再覆盖这两个变量。

候选配置可选`device: "cuda:0"`、`gpu_memory_fraction: 0.22`，CPU默认不变。Torch构建分别核验`2.5.1+cpu`和`2.5.1+cu118`；V100使用显式禁用Triton、compile、低精度attention和TF32的参考路径，不静默回退。`decode_mode`仅允许官方`viterbi`或`argmax`；默认Viterbi不变，任何新模式使用独立配置摘要、开发对照和完整回归。

PII驱动的`--gpu-devices 0,1,2,3`及凭证驱动的`GENELOOP_PRIVACY_BENCHMARK_GPUS=0,1,2,3`仅用于隔离评测worker分配。每个worker只见选定物理卡；超时替换worker继续按进程身份轮转，不能假定始终一进程一卡，须记录实际分配和显存。它们不是用户轨迹可选择的配置。保留原120秒观察期限、全部输入和金标；长输入不截断，超时仍是未知。

Web/离线检查现在记录固定的`offline_rejection_reason`，不记录上游原始异常。完整基准的拒绝记录增加固定检测器归因`decision_detector`；文件级拒绝指标仍不能当作凭证实体召回。新结果不覆盖R1–R6。
