# paper-web-v43

从 paper-web-v42 兼容重导出；仅审阅共享 Remotion 启动器新增的可选容器名称/nonce 标签。未设置这两个专用环境变量时保持原启动行为；设置时只隔离容器归属，避免旧实验清理命中新 worker。

Source库只解码一次，保留旧路径调用并追加版本绑定；原程序、参数替换与渲染语义保留。

原 library、online manifest、task、MCP schema 与 source evidence 逐字节保留，旧版本全部保留。新报告保留全部历史字段并追加兼容记录。零模型调用、零新训练、零原始轨迹重放；不认证新 Capability 内核，也不宣称任务质量或效率晋级。

验证记录：docs/experiments/efficiency-rsi-script-20261102.md。
