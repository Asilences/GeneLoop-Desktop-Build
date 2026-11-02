# Script 材料接入与执行兼容修正

- 实验 ID：`efficiency-rsi-script-20261102`；基于本地 `8a414dd`，分支 `codex/efficiency-rsi-20261102`。本轮不部署、不推送，不修改旧库、原件或累计账本。
- 类型：合成输入的原生沙箱诊断，组合提案为确定性夹具。不是新模型学习、自然任务流或收益实验。
- 问题：既有 Script 编译结果能否进入公共能力池，被组合、独立验证、发布、在不同输入上执行，并重新进入下一轮 Builder？外围编译代码变化是否必须废掉旧执行证书？

## 改动

1. `script_runtime_compatibility.ts` 将四个离线学习/编译/认证文件的历史哈希保留为来源记录。其余已有锁继续核验；`config/script-runtime-compatibility.json` 只接受精确旧/新哈希转换，不能由库或模型提交豁免。当前白名单只覆盖本次 loader 校验策略改动，执行主体、绑定、沙箱和回执逻辑原样保留；没有批量放行历史未知版本。
2. `script_capability_runtime.ts` 复用原 `loadScriptLibrary`、`runCertifiedScript` 和沙箱，新增 `script_motif` 叶后端、目录及实际执行入口。任务固定 owner、根、参数、库和输入字节；每次叶调用使用独立工作目录，只复制批准输入。取消传递到子进程组。
3. 公共材料登记支持 Script。原证书、程序身份及库字节保持不变；当前支持只读文件程序，联网/argv 程序明确列入 excluded，不影响其旧路径。
4. 论文 `capability_adapter.py` 复用公共发现、Builder、反馈与 Store。`publish_capability.mjs` 复用公共发布生命周期；检查器复用已有 BibTeX 解析器，独立检查条目数、唯一键数、重复键。验证和后继须使用不同文件内容。
5. 论文缺原语路由调用原 `learn-script-motifs.py`，第一任务专用于原生认证，后续为训练；绑定 owner/任务证据，登记后由公共控制器重新评价机会。没有新模型循环。这条真实历史任务获取路径尚未端到端运行；不能用下面的直接原生认证诊断代替它。

## 验证与反例

- Linux 原生执行及旧沙箱：21 项通过。包含新组合实际调用，以及旧写入、越界读取、网络限制、输入变化等检查。
- Linux 论文测试：4 项通过。由原编译器从合成脚本见证提炼程序，经原认证器在两个不同输入上实际沙箱复验，再经公共控制器组合、验证、发布、不同输入复用和构造池读取；双价值反馈记录有实际写入。
- 论文验证与后继分别检查 4 项。输入内容、native receipt、trace、发布记录保留在私有目录。机械检查只覆盖字面 BibTeX 盘点，不认证文献真实性或完整报告。
- 首次本地定向失败：使用了 Harness 当前 schema 子集不支持的 minItems/maxItems；改为原生绑定时精确检查数量，不放宽执行约束。修订后本地 6 项通过，1 项 Linux 专项跳过。
- 首次论文发布失败：检查结果遗漏 Store 要求的 `observation`，错误为 `capability_store_shape_invalid`。补充每项实际/期望观察后，使用新目录重跑通过；旧失败日志保留。
- 首次全量 Python：1789 通过、236 跳过、1 失败；旧测试将 Script 当未知后端，已改用 `unknown_backend`，保留未知后端拒绝断言。最终全量结果见本记录后续补充及交接。
- 最终全量：Python1793通过/237跳过、Node1495通过/18跳过/0失败。Linux smoke通过，SDK初始化成功、付费调用0。旧上传ECONNRESET本次未出现，但没有针对它修复。
- 本轮诊断发布摘要：`c1248bde88f533d923456dd888b5e68b0219e15db56fc9cb6eae32e96de73ef3`。验证得到4条/3唯一键/重复P，后继得到5条/4唯一键/重复T；各1次原生叶执行，均通过4项检查。

## 配置、费用和复现

本地 `.local/efficiency-rsi-script-20261102/` 保存源码归档、摘要、完整回归日志和同步回来的 Linux 诊断产物。服务器使用独立代码目录及现有项目 Python/Node/依赖；先加载私有 `.local/remote-env.sh`。没有服务重启或发布。

```sh
node --experimental-strip-types --test tests/test_script_capability_runtime.mjs
RUN_SCRIPT_CAPABILITY_SANDBOX=1 node --experimental-strip-types --test tests/test_script_capability_runtime.mjs tests/test_script_motif_sandbox.mjs
RUN_SCRIPT_CAPABILITY_SANDBOX=1 "$SSS_PYTHON" -m pytest -q tests/test_paper_capability.py
```

这些命令没有模型调用；新增模型请求/费用均为 0，未重置或写入原累计账本。机器和开发成本未货币化。构造能力、效率增量、创造价值的因果贡献与大规模泛化均待真实任务验证，不否定此前程序复用已有的局部效率收益。

下一步：固定已有真实论文任务的训练/认证输入，运行原生获取路由，再让真实 Builder 构造；如果失败，按缺口识别、材料学习、组合、验收四层定位。默认聊天接管、任务结束自动采集、任意 MCP 和主动资源再投资不在本轮范围。
