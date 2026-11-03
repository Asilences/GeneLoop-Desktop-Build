# 能力更新后的机会重新评价：机制验收

- 实验ID：`real-evidence-replay-001`，2026-11-03；源码`e789e0287e28faa12ab1a66aa56f388d7991274e`，基于远程main `eea8c558`。
- 问题：认证发布C后，真实未满足需求能否进入单次机会提案、独立宿主筛选、原Builder及验证发布，而不增加第二套Agent循环？
- 本轮范围：PR1机制验收。没有开启再投资、动态策略、生产任务接管或大规模模型实验。

## 任务、提案与验证边界

沿用历史真实科研项目的只读材料、验证/后继输入，以及此前模型生成的C、D算法。使用全新私有Store和工作目录，不修改旧项目、原轨迹、原发布和累计账本。初始池保留已有认证叶程序及比较程序；C和D在新Store中重新经过原独立验证发布。

目标提案是明确标记的固定诊断输入，D及其算法不是本轮模型自主提出。已有比较程序也不是本轮新学习。因此本次不能证明目标空间扩大、新能力获取成本下降或自供给式演化。没有新的盲测项目或同质量成本对照。

## 实际事件

1. 原Builder编译既有C算法，原Script Runtime执行并通过独立验证/后继，Store发布C。
2. 需求上下文仍有open need；新旧能力池不同，触发一次机会重新评价。没有按周期创建独立Agent。
3. 固定诊断提案`goal-61076befb14b1f52b81ad6e0`进入账本，记录需求原证据、前后snapshot与预期C依赖。
4. 固定宿主采用原验证器与冻结条件筛选该提案，通过后进入同一控制器队列。
5. 原Builder编译既有D算法，沿原Runtime/Store独立验证与发布；验证回执实际调用C **2次**。

C与D各有验证和后继，共 **4次独立检查均通过**。账本分别保留预期依赖、编译依赖和回执观察到的实际依赖。预期C与实际C在本例相符，但没有执行回执的记录保持null，不据模型描述计递归。

原证据位于私有`.local/capability-opportunities-20261103/server-evidence/real-evidence-replay-001/`。摘要SHA256：`fafe0eb04f6163b3e9ac7880df2744414a781686efaefe257a41e0af2281babe`。原输入、算法、上下文、检查、代码与环境版本由摘要及其引用定位，不提交原始项目或日志。

## 回归和费用

- 本地完整：**2174 Python通过/241跳过，1543 Node通过/21跳过**。
- Linux定向：**107通过**，包含原公共原生学习/认证整链；正式服务未动。
- 确定性回归覆盖：已有暂缓重试、相同更新去重、无需求/默认关闭、范围与版本变化、预期依赖不充当实际依赖、权限/质量拒绝、异常认领不重发，以及有限gate按单次提案开关。
- 此后仅将材料获取结果单独索引，避免当成独立质量验证；该账本元数据修正及相关逻辑另经25项定向回归。
- 新增真实模型请求 **0**，新增模型API费用 **USD0**。原模型获取费用未重算为本轮费用；CPU、人工与总经济成本未知，总墙钟耗时未完整采集。
- 私有证据采集脚本曾因导入路径及与标准库同名失败；修正采集入口后只重读结果，未重发任务、修改验证器或改写实验结果。

## 复现与后续接口

服务器先加载项目私有`remote-env.sh`，在本轮不可变代码目录运行：

```sh
node scripts/project.mjs python examples/capability-scenes/replay-opportunities.py \
  --c-plan "$PRIOR_C_PLAN" --c-attempt "$PRIOR_C_ATTEMPT" \
  --d-plan "$PRIOR_D_PLAN" --d-attempt "$PRIOR_D_ATTEMPT" \
  --output "$EXPERIMENT_CODE/.local/real-evidence-replay-NEW"
```

四个PRIOR变量定位私有摘要所引用的原计划/提案，不指向生产服务。输出必须是新目录。有效环境：Linux、Python3.10.21、Node22.23.3；具体系统及SDK包版本见私有摘要。

PR2可消费每轮`request/response/decisions/result`、每次构造`construction_result/acquisition_result`原引用、请求ID/费用，以及独立`verification`和执行trace引用。本PR不把这些事实转换为可支配信用。机制验收支持后续研究接线，不支持自主行为或效率增长的结论。
