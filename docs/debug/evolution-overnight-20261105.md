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
