# 演化机制与同条件比较运行记录

## 问题与目标

2026-11-05北京时间00:08开始八小时实施窗口，08:08检查。用户确认Skill∞论文复现版，同模型、任务和评分条件，费用和请求次数不限。优先验证同质量效率与后继能力构造，按真实复用结构及当前学习后端选择场景。

## 配置与复现

起始远程main为`f3289a213666d49e7529029be972dcd323c7a4b3`，研究分支整合提交为`f46d0e64`。实验源码和公开数据放独立研究目录，正式服务沿用其既有版本。

服务器加载项目私有remote-env，通过`node scripts/project.mjs python`执行。实际模型为`deepseek-flash`，`reasoning_effort=off`，`max_tokens=393216`，费用及请求次数不限。原累计账本基点为3375请求、代理计量USD3.2624273760000007，实际账单未知。

SkillEvolver数据版本为`16f3cc6392a5bb296231fc352ed0654312caab4e`，SkillsBench固定版本为`5544ce7c2708c231099d974089e7c9e81e67ee7a`。训练与canonical交集83题。每次运行另保存有效配置、原输入及评分器哈希。

## 首批运行与失败

- `pilot-dialogue-001`在Docker构建阶段遇到daemon镜像源403，模型调用0。
- 通过独立实验进程从可用公共镜像源准备原基础镜像，记录digest和本地标签。构建使用`DOCKER_BUILDKIT=0`，原Dockerfile保留。
- `pilot-dialogue-002`在原600秒构建时限内未完成Graphviz系统包安装，模型调用0。按慢任务规则暂缓，保留下载与超时记录。
- Three.js两题并行完成环境和原oracle预检，原verifier均得到1.0。该预检模型调用0，oracle数据排除在学习索引外。
- 原评分脚本的uv安装器遇到GitHub下载超时，采用其支持的`UV_DOWNLOAD_URL`指向官方release镜像，原评分脚本保留。有效环境在两侧一致并记录。
- `pilot-threejs-001`沿干净训练数据完成真实模型任务。原reward为1.0，模型86请求、代理计量USD0.12637326，模型会话303.39秒、端到端340.34秒。该运行提供vanilla质量与成本基点。
- 独立审计发现首轮在评分后采集工作目录，会包含评分器生成的ground truth。该轮模型执行在评分前完成，质量与模型费用保留；其post-verification文件索引排除在Evolution和学习输入之外。后续改为模型结束后先冻结产物，再运行原评分器，并新增旧索引拒绝及顺序回归。原始失败材料保留。
- `baseline-manufacturing-family-001`使用冻结R2源码启动，但在meta层首个seed评价结束。唯一模型会话130请求，代理精确计量USD0.19500395，全部请求已settled，账单实付未知。任务会话685.60秒，超出原600秒时限，后51次execute均被宿主deadline拒绝。SDK的RPC等待参数没有约束完整工具循环，现增加本会话总deadline。原SDK不支持`session/cancel`，研究适配器保留该公开请求的错误，并通过公开`Harness.close()`结束本会话独占Runtime。真实SDK加本机慢Provider诊断通过，详见[限时记录](research-harness-deadline-20261105.md)。
- 该轮verifier在`apt-get update`下载约10.2MB索引时耗时4分59秒，触发原300秒verifier时限，未进入pytest且无reward。优化器尚未收到提案请求，不能据此评价Skill∞优化效果。原始R2结果和费用保留为实现及环境诊断，修复后的对照使用新冻结源码和新运行ID。

## 实现与诊断状态

分层调查、原Harness工具循环、原生skill目录加载、原账本归属、Skill∞两层复现、共享benchmark和策略异步采用均已有定向诊断。原生Script材料获取及调用沿现有编译、认证与Runtime接线，真实调用及递归学习另行验收。

全量首次受本机端口沙箱限制。允许回环后发现旧库锁与整合源码差异，已沿原exporter生成独立新版本，旧版保留。macOS临时目录使用`TMPDIR=/private/tmp`复核。整合阶段全量2632项Python通过、261跳过，1662项Node通过、23跳过。该成绩对应本轮整合时源码，后续native工具与Gold顺序修复另有定向检查，最终全量待源码收敛后追加。

## 结果口径与下一步

任务原始reward、论文positive-reward指标及完整质量门槛分别报告。调查、生成、学习、验证、review、失败和最终测试费用完整保留，一次性投入与后继运行分开。

主结果需要真实模型与独立评分。演化成果可见、读取、实际采用、执行节省及后继构造收益分别记录。失败、未激活、`no_change`及未知费用同样进入后续分析。

## R3真实调查与R4修复

R3源码为`7d5a811b8796b04670dc8acb48830b6bd506c89a`，完整归档SHA256为`a323aa8e912472b5785767c8153e7bfcf174c0455a7a5323d05960ea0f6dba79`，Linux252项专项通过。

`gene-manufacturing-family-001`两个development任务均完成原评分。Codebook为14/16项通过，未通过语义支持比例及station_scope，119请求/USD0.16313097。Equipment为3/4项通过，TAL计算未过，13请求/USD0.01637601。原二值reward均为0，未更改原评分标准。

随后Evolution自主调查40请求，53次工具操作，11次提交全部因证据ID或候选格式拒绝，未产生新能力或策略准入。调查代理精确计量USD0.06947338，142.35秒。首个输入1905 tokens，单次最大112677、中位54625.5；累计输入2314072 tokens为40请求之和，包含缓存命中2221696。初始概要984 UTF8字节，主要膨胀发生在后续证据读取和工具历史。

定位与修复集中在通用接缝。宿主补齐已选观察对应的scope/evidence_ids，模型只生成实际改进决策；原生helper固定协议由宿主补齐；提交回执不重复回显源程序，完整原件按需读取。原评分操作和stdout/stderr明确进入可读取证据，Skill∞优化器新增同范围read_evidence，双方保留无oracle约定。新源码继续复用原两条真实经历，原始失败和费用保留。

R3最终canonical FJSP在基础镜像下载阶段失败，模型请求0、质量未知。已按原Dockerfile补齐python:3.12-slim并完成353.01秒环境预热，见[环境记录](skillsbench-adapter-20261105.md)。`baseline-manufacturing-family-002`在公共依赖安装120秒准备时限失败，模型请求0。R4将该准备阶段的apt时限设为600秒，各题执行及评分时限沿原task.toml。此前将各题概括为600/300秒不准确，FJSP实际为900/450秒，Lab实际为1800/1800秒，运行均使用原实际值。

R4的首个真实策略已越过格式和证据检查，进入FJSP训练变体独立验证。任务模型12请求、代理费用USD0.0081221，在原900秒处超时（900.885秒含退出），原评分0、策略未加载。后续FJSP探索按慢任务与适用性判断暂缓，操作员中断原研究进程，保留原请求归属、两次候选及不完整结果。唯一残留自有容器已停止，先保留取消时产物后清理；这些产物未进入学习证据。R4没有新策略准入或新能力结论。

R5修复独立验证失败后的证据返回，质量、加载状态和原诊断可在同轮继续读取；历史summary改为事实卡，正文与JSON局部通过分页读取；下一CLI继承原材料目录与实际后端。每个局部调查最多两次真实候选构造/验收，费用与请求仍不限，格式错误及不支持类型保留原诊断。

跨代学习现累计原真实调用并保留split/source/snapshot，逐组交原learner；历史canonical重放只作历史source-equivalence，新的语义质量继续等待新任务。汇总修复了失败模型reward可能被误计full-quality的问题，并将实际依赖预热配置纳入配对条件。

独立草稿[PR156](https://github.com/jingyio/GeneLoop/pull/156)已创建。四个GitHub job在启动前因账号付款或Actions消费额度阻挡，steps均为空，未执行远程测试。需要账号管理员处理Billing后重跑，不能把该状态解释为测试失败或通过。服务器与本地验证继续保留独立证据。

## R7：参数依赖、评测角色与请求预检

R7补公共接缝，不增加新的场景求解器：

- `capability_call` 新增显式 `input_binding`，与 `value`、`input_file` 三选一。直接复用原Binding的step／object／array／literal，step只能引用同一任务、输入指纹和snapshot内已有成功调用；调用前重新核对原Runtime回执，再由原binder解析完整Runtime参数。禁止根据值相等推断依赖，也不允许没有来源的input绑定。调用失败仍保存原尝试；已产生的原生失败回执留在图中作为原learner的边界，无原生回执的尝试单独索引，保留 `runtime_started` 的执行不确定性。修复绑定错误后发生的真实成功调用不会被一并丢弃。
- 数据集来源 `dataset_split` 与使用角色 `evaluation_role`（development／validation／final）分开保存。显式配置允许同题族canonical输入用于validation；按输入文件字节指纹检查，防止训练和验证只是题面或任务名不同。同轮final拒绝已用于development或validation的输入。递归采样按原输入指纹去重，validation反馈不能因来自test目录而冒充最终留出；旧记录只从原manifest重建身份并标注推断角色。
- 汇总按角色隔离比较，同时保留各阶段全部费用。final复用已观察validation数据会明确标记，final角色本身不构成新留出证据。跨运行的完整暴露历史仍需实验者核对，汇总不会凭目录名证明泛化。
- 调查候选缺字段时返回具体missing／unexpected字段，保留原假设和证据选择；避免所有提交错误都被笼统解释成证据ID错误。
- 费用gate兼容工具Schema中数组／对象形式的 `type`，真正媒体内容仍按原逻辑预留；触发的新库兼容更新详见[库记录](overnight-library-compat-20261105.md)。

本地R7定向375项通过，候选字段诊断21项通过；日志分别为 `.local/overnight-20261105/r7-final-targeted.log` 与 `r7-field-diagnostics.log`。首轮全量的两项兼容测试配对错误已修正；最终Python2856通过、261跳过，Node1662通过、23跳过。`smoke`、`motif:check`、`rsi:check`、`rsi:efficiency:check`、`rsi:rae:check` 均通过；日志为 `full-regression-r7-final.log` 与 `r7-mechanism-checks.log`。这些检查属于无付费机制诊断；其中显式绑定及C→D学习链只说明宿主能够保留并使用依赖，不证明模型自主选择、跨代创造或效率收益。R7真实模型实验结果另按冻结源码、运行ID、原评分和完整账本追加。
