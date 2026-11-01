# paper-web-v32

基于 paper-web-v31 的用量查询兼容版本。只修复统计查询临时超时导致对照任务误报失败：保留已有计数、标记统计未同步，并在后续查询恢复。模型准入、权限、取消及 Motif 匹配、学习、版本守卫不变。

原 library、manifest、task、tool schema、source evidence 字节保持一致。零新训练、零模型调用；不代表质量或成本效果晋级。验证记录：docs/experiments/postdeploy-stress-20261031.md。
