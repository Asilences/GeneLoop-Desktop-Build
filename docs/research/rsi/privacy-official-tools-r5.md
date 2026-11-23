# 公共脱敏 R5：官方专用模型与凭证扫描器

状态：实施和隔离评测中，默认仍使用既有Presidio/Gitleaks规则，PR162保持Draft。R5复现依赖状态污染后改用官方修复及兼容依赖，旧结果保留为不完整诊断；新依赖下的默认组合与附加模型须分开完整复测。用户授权继续在原分支接入成熟工具并运行benchmark；不修改正式服务、原件、证书或累计账本。本页不能作为完整验收报告，后续正式结果另入 `docs/experiments/`。

## 选型及实际兼容性

| 能力 | 固定来源与方式 | 当前边界 |
| --- | --- | --- |
| 上下文PII | [OpenAI Privacy Filter](https://github.com/openai/privacy-filter)官方源码 `f7f00ca7fb869683eb732c010299d901457f19c3`，Apache-2.0；[原始权重](https://huggingface.co/openai/privacy-filter/tree/7ffa9a043d54d1be65afb281eddf0ffbe629385b/original)固定revision，官方PyTorch CPU实现与发布的Viterbi/calibration | Torch2.5.1+cpu、tiktoken0.9.0，完整原文窗口处理；不训练、不改权重、不对benchmark调阈值。官方自报成绩不能当作本项目成绩 |
| 凭证 | [Samsung CredSweeper](https://github.com/Samsung/CredSweeper)1.19.6，MIT，默认过滤及medium模型门槛；Gitleaks8.30.0继续保留 | ONNX Runtime1.20.1在真实ML路径缺少接口，不能以导入或无候选文本证明可用；新隔离覆盖层使用官方1.26.0 manylinux_2_27资产，随机合成控制已实际经过ML |
| 其他已查方案 | Private AI/Limina本地商业容器，Azure Language PII等托管服务 | 未取得商业许可或调用云服务，不上传轨迹，不宣称已对照 |

软件包32份OPF Python源码、188份CredSweeper源码/模型/配置、四份原始模型对象及tokenizer缓存通过 `config/rsi-privacy-candidate-tools.json` 核验。旧NLP/扫描器版本守卫仍独立执行。原生工具依赖先在新解释器实际运行，原环境只读复用，不向正式服务安装。当前只验证Linux x64 CPU；桌面/Mac及资源占用另验。

R5的137条原worker顺序重放复现spaCy3.8.7的`Vocab.get`断言，官方[Issue13924](https://github.com/explosion/spaCy/issues/13924)/[PR13932](https://github.com/explosion/spaCy/pull/13932)确认异常清理缺陷。先试3.8.12与原依赖，真实模型加载因Pydantic/Confection不兼容失败，未仅凭导入成功采用。随后固定官方3.8.18、Thinc8.3.12、srsly2.5.3、Weasel1.0.1、Confection1.3.4及其HTTP依赖，不自行修改词表/分词实现；Pydantic、NumPy及中英文模型保持原版本。八个官方轮子和活动依赖约束已核验，实际中英文异常清理/下一条处理、CPU推理、凭证ML及独立文档复核通过，76项定向通过；完整复测仍待完成。旧环境及失败探针均不改写。

探针保留了中文姓名漏检、含Fictional示例措辞的密码未命中、最初导入路径错误、旧运行库真实ML失败和两次环境转引遗漏。最终独立复核命令实际经过CPU前向、坐标回环及CredSweeper ML，旧失败不覆盖为成功。

## 公共接入

`src/adapters/rsi_privacy_candidates.py`只提供官方检测器适配及宿主作用域。正常任务仍读原件；只有学习/可选共享派生数据进入 `learning_view`。候选配置不能从任务JSON选择。

宿主私有配置的完整字段如下，路径替换为已核验的本机资产位置：

```json
{
  "format": "geneloop.privacy-candidate/v1",
  "text_mode": "r4+opf",
  "credential_mode": "gitleaks+credsweeper",
  "checkpoint": "/private/model/original",
  "tokenizer_cache": "/private/tokenizer-cache",
  "threads": 1
}
```

可单独选择 `text_mode: r4` 或 `credential_mode: gitleaks` 做单因素对照。用环境变量传配置绝对路径及同一文件的SHA256，两项缺失配对、摘要不符、未知字段、版本或文件漂移都不能放行学习材料。两个变量由既有TypeScript/Python worker白名单透传，继续受原120秒外层期限、取消、队列和原子发布约束。

七个OPF标签映射到已冻结的项目类别；`private_date`仍不默认启用，原生八标签在评测里单列。原始字符坐标及tokenizer回环必须一致，替换继续复用Presidio Anonymizer及包内别名。学习准入检测到OPF `secret`同样拒绝整包，不能靠遮盖秘密后把它算作凭证安全准入；原生文本遮盖指标与准入率分别评分。CredSweeper内存文本适配每次清空候选，保留模型不保留上一个包的材料；ONNX telemetry关闭。未配置时不加载附加模型，沿用既有检测规则和修复后的固定NLP依赖。

## 预先固定的比较

配置为 `scripts/privacy-benchmark/model-official-r5.json`，环境为 `env-r5.json`。继续保存R1–R4、同一原始数据/金标及原10类声明，不删困难类别。600条历史开发样本及24组语义控制用于候选检查，均已见，不能称独立留出。

初步624条全部完成、0超时/处理错误。文本替换重放的R4并集新增596处完整遮盖，旧完整覆盖丢失0，120/120任务要求保留；但新增金标外遮盖为中文正式21.76、聊天14.02、英文1.40个百分点，超过原0.1个百分点门槛。中文正式8个长正文片段由8保留降为0，聊天2个仍保留2，英文586个中由537降为512。不能把这几个代理指标与实际任务要求混为一谈，也不能只展示更好的召回。

因此当前配置不默认采用，继续以独立候选进行三套全量及真实公共准入对照。全量仍需报告原生Presidio/OPF/Gitleaks/CredSweeper与公共模块、完整/部分漏遮、金标外字符、正文与任务要求、准入后残留、拒绝与未知、冷/热耗时和资源。CredSweeper官方训练流程使用CredData，保留该基准作回归，不能据此宣称独立泛化。独立新来源、真实RSI后继质量、桌面和正式接收端验收仍待完成。

官方仓库另有ONNX量化资产。本轮只下载并检查官方发布版本，未自行量化。四个合成样例的标签和边界与参考实现相同，但未提供充分的质量/性能替换证据，仍保留原始权重；探针不能当作完整量化模型验收。
