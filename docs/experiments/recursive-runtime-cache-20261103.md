# 递归组合 Runtime 请求内验证缓存：零模型性能重放

实验 ID：`recursive-runtime-cache-20261103`；日期：2026-11-03。

在同一个已发布 D、相同输入和材料库上，缓存修复使 Runtime root 耗时中位数从 **22.958 秒降到 6.150 秒**，完整驱动 wall 从 **23.771 秒降到 6.944 秒**。两侧各 12 次运行全部通过原有确定性质量检查，配对结果摘要一致。该结果支持减少重复验证的工程收益；创造价值、跨代自主构造效果和全系统 ROI 未由本实验验证。

问题是假定每次守卫仍核对当前真实字节，能否只在单次请求内复用相同材料的解析与完整验证结果，减少组合图中的固定开销。若结果、质量、依赖调用或守卫行为发生变化，则不能据此确认这项优化有效。

两侧分别使用 `853f6abeb0bef98aa34a23a838e7ee82c734af38`（私有检出 `code-22`）与 `2ab970cc55750f268cf4160c4dfc2a4f727478b1`（`code-23`）。重放复用已有 D，没有重新构造、认证或筛选候选，也没有删减六份原生 library。两组使用同一 V2 驱动；先完整运行 before，再运行 after。输入为两个既有项目的四组相邻版本对，每组重复三次，因此是 **12 组配对测量、4 组不同输入**，不是 12 个独立任务。

冻结对象的摘要如下；能力和 snapshot 使用协议内容摘要，其余为 SHA-256。

| 冻结对象 | 摘要 |
| --- | --- |
| 已发布 D | `c962563a382f4c1d2e1f598cbffb73a55babbeebfcad08a0bfd600f75475cb5d` |
| snapshot | `cef90f7b839214debfd0b5b0a50dc453b45701ec160ff555398eecee03103600` |
| 六份 library 的有序 SHA 列表 | `cc068d643773058d0b5f011f80bef49ac37cf9171ee9161a4e3871777c04b7fa` |
| `runtime-cache-probe-v2.py` | `8e5753eb8040f8fb466c365ba839050762b2b98b5959feb26c81f0b5f8e18be1` |
| before Runtime 源码 | `6b681153746655fd8d42ad834cc35983831758b229af1439a6921bd3fe75c0cf` |
| after Runtime 源码 | `78455c5abf0cee98f07c3dc43332c64f728aa39b34fd03aec727e87f6590891e` |

library 列表摘要计算为 `SHA256(JSON.stringify(libraries.map(row => row.sha256)))`，保留 manifest 顺序、不包含私人路径。完整 manifest、输入证据、逐次结果与 trace 摘要保存在私有 summary。

| 指标（12 次运行的中位数） | before | after | 变化 |
| --- | ---: | ---: | ---: |
| Runtime root | 22.958 s | 6.150 s | 降低 73.21%，3.733× |
| 完整驱动 wall | 23.771 s | 6.944 s | 降低 70.79%，3.423× |
| 七个原生叶的累计 inclusive 时间 | 1.5265 s | 1.5745 s | 未观察到下降 |

逐对计算 `before / after`，root 加速的中位数为 **3.744×**，范围 **3.695–3.900×**；wall 配对加速中位数为 **3.423×**。表中的 3.733× 是两侧 root 中位数之比，与配对比值的中位数分别报告。

root 取根 receipt 的 `duration_ms`；wall 从调用 `execute` 前计时，包含执行、独立 oracle 检查及质量记录保存。原生 inclusive 时间为七个叶 receipt 中 `native_receipt.elapsed_ms` 之和，包含原生执行器内的启动、沙箱与程序执行开销，不能当作纯算法 CPU 时间，也不能再加到已包含子调用的 root 上。原生时间基本保持同一量级，结合代码改动，支持主要收益来自宿主重复读取后的解析、catalog/library 验证和 registry 验证开销减少。

两侧各 **12/12** 通过既有 D oracle；所有 12 对 `result_digest` 一致，每例均为 **2 次 C 调用、7 次原生叶调用**，D、snapshot、材料库及驱动摘要一致。这是既定任务的确定性回放验收，未开展新的人工盲评。模型请求数为 **0**，没有模型输入输出或付费模型费用；开发和维护投入未计量。

缓存仅存在于一次 `runScriptCapability` 请求内。每次守卫仍读取真实材料或 registry 字节、核对 SHA；字节变化重新验证，executor/policy 代码变化拒绝继续执行。权限、grant、输入版本、撤销和生命周期检查继续执行；原生证书身份与旧兼容白名单未修改。该改动不接管生产，也不以跳过守卫换取速度。

诊断失败保留如下，未混入 V2 的 12 组配对结果，也未启动新的模型候选构造或候选评测：

- **V1 before/after 统计失败。** `backend_receipt` 可以为 `None`，V1 对 `r.get('backend_receipt', {})` 继续调用 `.get`，触发 `AttributeError`。错误发生在原生重放及该次质量记录保存之后，属于诊断聚合器失败；两份目录与日志保留，没有形成完整统计。V2 改为 `(r.get('backend_receipt') or {})` 后，在新目录完整重跑两侧。V1 驱动 SHA 为 `7e7d30a61e305609b48b5db8f7941b2d632e018018d95886b407288a66d2aafb`。
- **after V2 首次启动失败。** 误用服务器系统 `python`，解析 f-string 时即 `SyntaxError`，未执行任何 case、未建立结果目录。保留该日志后，改用私有环境配置的 `SSS_PYTHON`，以新日志启动相同 after label；没有覆盖失败记录。

实际执行环境为 Linux `4.15.0-213-generic x86_64`、Node `v22.23.3`、项目 Python `3.10.21`。本驱动不调用模型或 DSH 语义端口；相关包未单独采集版本。复现需要授权的私有原始材料和已配置隔离环境。加载既有 `source .local/remote-env.sh` 后，在两份冻结检出中分别执行：

```sh
cd "$RSI_EXPERIMENT_ROOT/code-22"
PYTHONPATH=. "$SSS_PYTHON" ../runtime-cache-probe-v2.py --label before-v2-853f6abe
cd "$RSI_EXPERIMENT_ROOT/code-23"
PYTHONPATH=. "$SSS_PYTHON" ../runtime-cache-probe-v2.py --label after-v2-2ab970cc
```

驱动要求输出目录不存在；重复复现须使用新的 label，保留已有结果。该测量采用固定先后顺序，没有单独隔离宿主负载，因此不主张精确的跨环境加速倍数。它也未比较有 C 与无 C 的自主构造成本，未验证节余再投资或更长期能力增长。

私有证据均以检出根的匿名相对路径定位，原始日志和私人源文件不进入版本控制：

| 相对路径 | SHA-256 |
| --- | --- |
| `.local/recursive-construction-20261103/server-evidence/runtime-cache-before-v2-853f6abe/summary.json` | `77db5629628855c8701cd9d8d685316b57502b5361c253b68b5650835c80671b` |
| `.local/recursive-construction-20261103/server-evidence/runtime-cache-after-v2-2ab970cc/summary.json` | `8c64e087e97a9426c23329cb28d3a1aee6495e8aa64a21f1f9b48550a49266e4` |
| `.local/recursive-construction-20261103/server-evidence/runtime-cache-v2-comparison.json` | `276cd2dcf8ee5cc699b87298720ca0616dbb8051ad4b20465222dc9baae7236d` |
| `.local/recursive-construction-20261103/runtime-cache-before-stderr.log`（服务器） | `7cf7ffe0f8f09ce5a121900697e486b3c0b6848d56f2e55437537eaafbe3856c` |
| `.local/recursive-construction-20261103/runtime-cache-after-stderr.log`（服务器） | `5e701f0057a627c553e94789ddbeda6bccce80eb68b944bda9e633bb5215f886` |
| `.local/recursive-construction-20261103/runtime-cache-after-v2-2ab970cc-stderr.log`（服务器首次启动） | `dfa17115ade09ca71ae351070f880d901f077f40a77298375ca19f6a276528b5` |

完成的 after 日志为私有 `runtime-cache-after-v2-2ab970cc-run1-progress.jsonl` / `run1-stderr.log`，原生 trace 与质量记录均保留在对应结果目录。下一步应在新的真实任务流上检验该工程优化的维护成本与持续时延，并在另一个冻结对照中研究 C 的创造价值。
