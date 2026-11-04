# 夜间演化与main整合的库兼容

## 触发与范围

远程main `f3289a21` 合入当前分支 `f46d0e64` 后，保留main原有的 `ppt-master-v77` 和 `paper-web-v79`。策略演化接线改变了五项原代码锁，导致默认库载入及相关负向守卫回归失败。

五项差异为 `scripts/harness-web.py`、`scripts/reexport-ppt-managed-compat.py`、`src/adapters/capability_construction_history.py`、`src/adapters/capability_proposal.py` 和 `src/adapters/dsh_web_tasks.ts`。

## 处理

沿原重导出流程新增 `--overnight-evolution-integration` 模式，从main原版本生成独立 `ppt-master-v78`、`paper-web-v80`。原库保留，默认配置选择新兼容版本。

原 `library.json`、`online-manifest.json`、`task.json`、`tool-schemas.json`、`source-evidence.json` 逐字节保留。新认证记录精确五项源码差异与新增策略依赖锁，独立加载验证继续执行。模型请求和新增训练任务为0。

## 复现与验证

预览命令为 `.venv312/bin/python scripts/reexport-ppt-managed-compat.py --overnight-evolution-integration --preview`。

写入命令在源码冻结后执行，使用 `--write --update-registry --validation-record docs/debug/overnight-library-compat-20261105.md`。已有目标目录时拒绝覆盖。

## 验证结果

重导出与默认配置更新已完成，新PPT库为 `ppt-master-v78`，新Paper库为 `paper-web-v80`。原库完整文件哈希复核一致，五项核心IR与来源文件逐字节一致，新库经原加载器以execute模式载入。

首次四文件定向回归为60通过、1失败。失败来自macOS默认临时路径的 `/var` 重定向，触发原preset目录守卫，与库认证无关。使用规范 `TMPDIR=/private/tmp` 复跑原61项全部通过，守卫保持原逻辑。

兼容回归表追加原77→78及79→80两项，继续覆盖新默认选择、原认证引用与IR／来源字节不变。最终定向命令为 `TMPDIR=/private/tmp .venv312/bin/python -m pytest -q tests/test_harless_paper_product_bundle.py tests/test_harless_rsi_bundle.py tests/test_harless_scenarios.py tests/test_harless_models.py`。

最终上述Python定向63项通过。跨语言契约与策略Node定向16项通过，执行时用 `SSS_PYTHON` 指向项目 `.venv312/bin/python`。首次直接Node调用使用系统Python缺少jsonschema，失败证据保留，切换原项目解释器后通过。

原训练与质量结论保持其来源范围，本次模型请求、新训练与原始轨迹重放均为0。未推送、未合并、未部署。

## R7：工具Schema媒体检查兼容更新

R7修复 `deepseek_cost_gate._image_count` 对合法JSON Schema的处理：`type` 可以是数组或对象，先确认它是字符串，再判断是否为媒体内容类型，避免 `unhashable type` 在请求预检阶段阻断调用。真正的图片／文件内容继续参与原媒体额度预留，费用账本与预算规则未改变。

该修复改变已认证源码锁，沿同一重导出器新增 `--tool-schema-media-compat`：从 `ppt-master-v78` 生成 `ppt-master-v79`，从 `paper-web-v80` 生成 `paper-web-v81`。审阅变更集合仅含 `src/adapters/deepseek_cost_gate.py` 与重导出器本身。新79／81已成为工作区默认，旧78／80保留；没有原地覆盖旧认证。原MCP schema与在线程序保持一致，写入回执记录模型请求0、新训练任务0、未提升质量或成本结论。

复现沿原入口：`node scripts/project.mjs python scripts/reexport-ppt-managed-compat.py --tool-schema-media-compat --preview`；冻结源码后才使用 `--write --update-registry --validation-record docs/debug/overnight-library-compat-20261105.md`。私有预览与写入回执分别为 `.local/overnight-20261105/r7-compat-preview.json` 和 `r7-compat-written.json`。

R7定向375项通过。首轮全量Python为2852通过、261跳过、2失败；两项失败来自兼容测试误把旧父子配对改成跨版本配对。已恢复原79→80及77→78，并另追加80→81及78→79，继续检查直接父证书及原IR不变。最终全量正在重跑，日志 `.local/overnight-20261105/full-regression-r7-final.log`，完成前不标记全量通过。此更新不表示远程CI通过或生产部署。
