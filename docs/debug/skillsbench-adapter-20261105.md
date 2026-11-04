# SkillsBench 任务适配与静态预检

- 日期为2026-11-05，代码基点为`f46d0e641e9faff5ef4166ecf750c94d3c82ee35`。
- 范围为公开数据固定版本、CPU候选任务、隔离Docker适配与评分诊断。
- 代码为`src/adapters/skillsbench_trial.py`，针对性诊断为`tests/test_skillsbench_trial.py`。
- 私有数据清单及完整文件哈希保存在`.local/overnight-20261105/skillsbench-selection.json`，公开数据检出位于其`deps/`。

## 数据版本与划分

SkillEvolver固定提交为`16f3cc6392a5bb296231fc352ed0654312caab4e`，其准备脚本指定SkillsBench提交`5544ce7c2708c231099d974089e7c9e81e67ee7a`。训练变体与canonical任务的交集核对为83题。两个检出仅用于研究依赖。

训练／测试共用原task identity，具体输入文件分别保留哈希。训练变体、测试样本及同题多次尝试的来源关系可追溯。

来源见[数据准备脚本](https://github.com/THU-AICosmos/skillevolver/blob/16f3cc6392a5bb296231fc352ed0654312caab4e/scripts/setup.sh)与[固定任务目录](https://github.com/benchflow-ai/skillsbench/tree/5544ce7c2708c231099d974089e7c9e81e67ee7a/tasks)。

## 静态任务选择

选择依据来自题面、输入结构与原Dockerfile，模型成绩尚未用于选择。首个连通性任务为`dialogue-parser`，其输入跨训练与测试变化，任务需要可参数化的文本解析与图结果。

效率RSI主线优先考虑当前Python、只读输入与结构化结果后端可支持的局部过程。

| 任务族 | 共同处理结构 | 实现与耗时条件 |
| --- | --- | --- |
| `manufacturing-codebook-normalization`、`lab-unit-harmonization` | CSV记录解析与标准化，后续还需要语义映射或单位判断 | 前者仅Python与pandas，agent600秒／verifier300秒；后者科学栈较重，二者均1800秒 |
| `enterprise-information-search`、`parallel-tfidf-search` | 文本／JSON读取、检索与查询结果组织 | 前者环境较轻，二者超时600秒；后者agent／verifier900秒，需要8CPU及真实性能计时 |
| `threejs-to-obj`、`threejs-structure-parser` | 场景遍历、世界变换与OBJ输出，再到分组组合 | 策略迁移备选，JS辅助代码超出原Python学习后端，Three.js版本分别0.175与0.170 |

共同结构只提供真实调查机会，具体算法、候选边界和后继目标由Agent基于运行提出。只读能力可以返回结构化结果，最终文件交付仍由原任务执行过程完成。

`citation-check`依赖外部书目服务核对，`software-dependency-audit`构建需要下载大型漏洞数据库。`taxonomy-tree-merge`安装sentence-transformers等较重依赖。它们在首次纵切之后再按剩余时间安排。

## 技能安装与镜像隔离

`prepare`复制原`environment/`到独立trial目录，替换副本中的`skills/`，原Dockerfile保持字节一致。安装位置从原`COPY skills`语句记录。提供候选技能且原Dockerfile缺少此入口时，在fresh容器中显式复制同一候选包到便携目录`/root/.agents/skills`，manifest标为`portable_runtime_copy`，两侧使用相同安装方式。

安装方式按每一split的原Dockerfile确定。canonical `dialogue-parser`和`lab-unit-harmonization`缺少此入口，使用上述显式安装，并由共享runner提供相同的按需技能读取。`prepare`返回容器内`skill_root`和每个包的宿主／容器路径映射，便于原Harness将资源相对路径指向实际容器文件。输入支持技能根目录或直接包含`SKILL.md`的单个包。

每次trial创建独立容器并记录镜像ID。Docker可复用构建缓存，容器可写状态隔离。清理限定为该trial容器，镜像与其他trial保留。候选技能的实际安装可通过容器内读取操作核对，真实核对结果在服务器运行后追加。

用于后续调查与学习的运行顺序为模型执行、`collect_artifacts`、评价、关闭。采集读取镜像的`Config.WorkingDir`并复制该工作目录，生成含文件哈希与来源身份的`artifact-index.json`。空目录或`/`返回待指定工作目录。采集标为宿主动作，快照同时包含初始输入与生成文件，后续调查通过真实执行事件识别生成来源。

采集结果明确保存`collection_phase`。评价前为`pre_verification`，评价后为`post_verification`。后者保留作工程诊断，Host将其排除于Evolution输入与学习，避免原Three.js验证器在工作目录生成的`ground_truth`进入模型上下文。此前pilot的评价后快照保留并隔离，质量与费用原记录保留。

## 评分与超时

模型执行阶段仅构建原环境。评价阶段复制原tests并运行原`/tests/test.sh`，收集原reward与日志。构建和verifier超时读取原`task.toml`。verifier超时后停止容器，收集已有日志并清理，结果保留为`verifier_timeout`。

共享Harness还需以原`agent.timeout_sec`限制整题运行时间。适配器的单条命令timeout只约束该条工具执行，整题时限由调用入口执行。

任务命令超时后，适配器使用`docker stop --time 0`停止本任务容器，保留容器文件与部分输出，记录`execution_timed_out`及停止证据。之后禁止继续执行任务命令，宿主仍可在评分前采集产物。原verifier评价前仅在停止成功得到确认时启动同一容器，原任务exec进程已被停止。停止或重新启动失败时质量保持未知，最终`close`才删除本任务容器。38项无模型适配器诊断覆盖超时后采集、原评价、禁止后续任务执行及停止／启动失败。

V100另完成真实Docker诊断。独立容器内命令先写部分文件再等待，宿主命令达到1秒限时后停止容器，在stopped状态复制原文件，重新启动后核对旧进程未继续写后续文件，检查通过。唯一诊断容器已清理，无模型调用或服务改动。私有结果为`.local/debug/skillsbench-timeout-20261105/v100-docker-diagnostic.json`。

评分同时保留数值与状态。原dialogue评分可产生部分reward，论文avg成功条件为reward大于零，完整通过情况应单列。缺失、非法或评分运行失败保留未知。

## 验证状态

本地36项诊断通过，使用合成Docker执行器，覆盖原字节、技能替换、安装入口、原评分器、数值、来源变化、超时停止、容器隔离及采集阶段。真实Docker和原oracle可运行性见下方服务器预检，模型行为与效率效果由正式对照运行确认。具体诊断命令为`.venv312/bin/python -m pytest -q tests/test_skillsbench_trial.py`。

## Three.js 无模型环境预检

独立实验根为服务器`.local/overnight-20261105/threejs-preflight`，同步内容仅公开固定版两题训练材料和本次适配器。原oracle运行标记为环境诊断并从学习经历排除。

首次启动因正式旧checkout缺少新反馈模块，在导入阶段停止。修复为从本轮隔离代码快照加载原依赖。统一入口Python为3.10.21，新增`tomllib`到`tomli`兼容导入，条件依赖锁定服务器已有`tomli==2.5.0`。

两题首次Docker构建均在Ubuntu24.04基础镜像元数据阶段失败，daemon的Aliyun mirror返回403。直接Docker官方registry连接超时，公共镜像源`docker.m.daocloud.io`可拉取。仅预取公共镜像并添加原标签，后续构建使用单命令`DOCKER_BUILDKIT=0`，保留原Dockerfile。

| 原标签 | 公共镜像源digest | 已核对版本 |
| --- | --- | --- |
| `python:3.12.8-slim` | `sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0` | Python3.12.8 |
| `ubuntu:24.04` | `sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852` | Three.js原基础标签 |
| `node:20-bookworm-slim` | `sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0` | Node v20.20.2 |

基础镜像元数据和失败／pull日志保存在实验根的`network/`与`runs/`。legacy builder下两题环境均构建成功，实测Node v20.20.2，Three.js分别为0.175.0与0.170.0，原oracle均返回0。首次评分均在下载uv 0.9.7的GitHub二进制阶段达到原300秒限时，结果为`verifier_timeout`，reward未知。

原安装器支持`UV_DOWNLOAD_URL`。核对其官方自有`releases.astral.sh/github/uv/releases/download/0.9.7`下载入口可访问后，通过新增的`verifier_environment`运行配置设置该变量。原tests保持字节一致，运行配置保存到manifest，所有对照组采用相同设置。重跑评分结果完成后继续追加。模型调用为0。

官方uv镜像设置下的后续预检完成。

| 训练题 | 原oracle | 原verifier | 本次端到端耗时 | 成功run后缀 |
| --- | --- | --- | --- | --- |
| `threejs-to-obj` | 返回0 | reward1.0，passed | 138.58秒 | `threejs-to-obj-1793811814176324162` |
| `threejs-structure-parser` | 返回0 | reward1.0，passed | 73.19秒 | `threejs-structure-parser-1793811818342081563` |

耗时包含此次缓存构建、原oracle和依赖安装／评分。初始冷构建及两次uv超时另行保留。两题模型调用仍为0，结果支持环境与评分器可运行性。JS生成程序进入原Python学习后端的接线仍需单独实现。

成功镜像分别为`sha256:334765d57ffdb880e3a8b2cff131a44dbd3077d4219abccc25bd05b8f17b26a9`与`sha256:f542ee1100836285ce9962729957d34a93af891be0da1f6664537f4ff03459c4`。只清理本轮trial容器，镜像保留。必要公开预检日志同步到本地`.local/debug/threejs-preflight-20261105/server-results/`，全部标为oracle环境诊断并排除于学习。

### 清洁数据复核与后继入口

初次macOS传输附带`._*`资源叉元数据文件。已核对全部原清单文件的字节哈希一致，旧目录与结果保留。后续使用`COPYFILE_DISABLE=1 tar --no-xattrs --disable-copyfile`同步到新目录，并确认无此类附加文件。

服务器训练根为实验根下`data-clean/`，canonical测试根为`data-test-clean/`。两根均已同步Three.js两题及`manufacturing-codebook-normalization`、`lab-unit-harmonization`原材料。模型试验读取这两根，oracle预检记录位于独立`runs/`。

清洁数据上两题再次通过原oracle和原verifier，reward均为1.0。`threejs-to-obj-1793812191870074772`耗时133.52秒，`threejs-structure-parser-1793812209616811371`耗时124.19秒，模型调用均为0。镜像在oracle执行前构建，预检代码与输出只存在于随后清理的trial容器及独立诊断记录。

Python主任务族已预取原`python:3.11-slim`和`python:3.9.19-slim`基础标签。前者公共镜像digest为`sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893`，后者为`sha256:69e712dbe4c4a166527cbf69374533125cfb6ee93a5e39031a0191c741d386d7`。

`manufacturing-codebook-normalization-1793812548441839372`完成原环境、oracle与原verifier预检，reward1.0，原oracle返回0。实测Python3.11.18、pandas2.2.3，冷端到端576.88秒，镜像为`sha256:cd4bb2081a1419f4b272aa882eb83eb27d528053682917fd09804f616690bb34`，模型调用0。

`lab-unit-harmonization-1793812554319345621`在原600秒构建限时超时，未进入模型或oracle。Debian apt update下载9.4MB用了约298秒，随后需要123MB系统包，失败发生在系统依赖下载阶段。原限时与评分器保持，建议本轮先暂缓该慢任务，使用已缓存的manufacturing环境推进受支持Python链。原stdout／stderr和结果保留，模型调用0。

### 制造业Python后继候选

按静态任务结构补选`manufacturing-equipment-maintenance`和`manufacturing-fjsp-optimization`。两者沿用Python3.11-slim、最小apt依赖和pandas2.2.3，增加pytest8.4.1。前者从生产CSV和handbook PDF形成分组关联审计，后者从CSV／JSON／文本形成约束调度结果。可观察的共同处理包括结构化记录读取、字段对齐、分组与关联。具体能力由真实构造经历决定。

相较之下，`weighted-gdp-calc`需要LibreOffice与公式评价，`invoice-fraud-detection`包含较大的PDF／XLSX依赖栈，作为后续备选。上述选择先于新任务模型成绩，保留PDF阈值读取及调度搜索本身的成本差异。

新增两题的训练与canonical材料已同步到相同清洁数据根，完整哈希追加到本地selection文件，当前为12题、24个manifest。

| 新增训练题 | 原oracle／verifier | 实测运行栈 | 本次端到端耗时 |
| --- | --- | --- | --- |
| `manufacturing-equipment-maintenance` | 返回0，reward1.0 | Python3.11.18、pandas2.2.3 | 107.21秒 |
| `manufacturing-fjsp-optimization` | 返回0，reward1.0 | Python3.11.18、pandas2.2.3 | 90.92秒 |

前者run为`manufacturing-equipment-maintenance-1793813505267439067`，镜像为`sha256:93598ffc44f5cfe628a9c5c5f0aaaf82a7dee6ec76ee69e1e52329a03d08a228`。后者run为`manufacturing-fjsp-optimization-1793813533114743855`，镜像为`sha256:05c826f759a8ce3450f8dfcd991539e5da335f540cdc2c24a221eeb36413aed3`。原环境、oracle和评分器预检均通过，模型调用0，材料继续与真实学习输入隔离。
