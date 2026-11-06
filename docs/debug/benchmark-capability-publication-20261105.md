# Benchmark递归候选的原Store发布接线

## 当前结论

已接通原learner候选到原CapabilityStore的适配。输入投影、通用arguments分派与空Store读取诊断共29项通过。真实Script材料的正例发布由服务器已有实际调用轨迹继续验收。

## 数据流

`publish_recursive_candidate` 接收原learner候选和实际轨迹FileRef，重建原learner结果，核对同一候选与训练／heldout来源。当前支持Script后端的JSON value调用；文件路径绑定需要额外恢复时保留pending。

适配从learner的 `source_input_bindings` 还原候选参数，冻结heldout原Runtime输出。新Node桥通过原Script Runtime的validate模式执行，再用独立代码比较原结果，经原Store.publish发布。原Store内部完成验证与发布，API没有独立stage方法。

发布认证范围为heldout source-equivalence。原benchmark质量与独立后继消费分别记录，后继尚未运行时明确pending。没有手写后继算法，候选来自原learner。

## 入口

- `src/adapters/benchmark_capability_publication.py` 提供预检、输入投影与发布适配。
- `scripts/benchmark-capability-store.mjs` 仅桥接原Store与原Runtime。
- `BenchmarkScriptMaterials.publication_store` 指向原Store目录，catalog调用原constructionLibrary合并发布能力。
- `execute_arguments(ref, arguments, directory, task_id, inputs=())` 直接执行原Capability输入，组合的 `p0_*` 参数保留原形式。

旧execute继续支持叶value／paths输入，遇到composition转通用参数入口。无模型调用，账本与生产路径保持原入口。

## 验证

命令为 `.venv312/bin/python -m pytest -q tests/test_benchmark_capability_publication.py tests/test_benchmark_script_materials.py`，结果29项通过。Node语法、Python编译及diff空白检查通过。

这里的注入执行器只用于参数分派诊断。原Store正例认证要求真实Script库和原Runtime执行，不使用测试后端证书。
