# 能力结果交接到研究容器

本轮基于 `986fa295`，修改研究用 `benchmark_capability_tools.py`。Runtime 已产生的 JS、OBJ 或 JSON 结果可通过当前 trial 的文件接口直接交付，减少模型转抄。

调用使用可选的 `export_result`。

```json
{"capability_id":"<现有能力ID>","value":{},"export_result":{"path":["value","source"],"container_path":"/app/generated.js"}}
```

`path` 沿用原 Binding 的对象字段路径。字符串原样编码为 UTF-8，其他结果采用键排序的紧凑 UTF-8 JSON。宿主从原执行回执取值，写入私有文件，通过现有 trial 操作复制到当前容器，再回读核对字节与摘要。`export.json` 保留原 Runtime receipt、产物与操作引用。

导出调用返回 `exported_file` 摘要及原 receipt，大结果留在原执行记录。普通调用继续返回原结果。`exported_file.status` 独立记录交接结果，交接失败后真实 Runtime 成功步骤与后续 `input_binding` 保持可用。请求格式错误保留为未执行尝试。文件操作沿用当前 trial 的存活状态与容器边界。

定向验证命令如下。

```sh
node scripts/project.mjs python -m pytest tests/test_benchmark_capability_tools.py -q
```

工具专项 52 项通过。覆盖字符串及换行保真、JSON、摘要和回执、紧凑返回、非法路径、已结束 trial、复制或校验失败、导出记录写入失败，以及失败后继续引用真实计算结果。原 Runtime 算术夹具提供实际执行回执，容器文件操作采用内存诊断替身。模型/API 与 Docker 调用均为 0。端到端质量与效率由后续真实研究运行评价。

工具、材料适配器、原 Motif 学习器、Host、Gene、CLI 与调查流程联动共 263 项通过，耗时 47.98 秒，`git diff --check` 通过。
