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
