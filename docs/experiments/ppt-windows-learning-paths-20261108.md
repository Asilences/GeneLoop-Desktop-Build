# Windows 深目录学习、认证与晋级修复

## 目标与边界

修复[上一轮后端记录](ppt-production-closure-20261108.md)中Windows完整学习失败的问题，保留原账户、证据、认证和晋级规则。只做文件访问修复及必要的无模型回归；前端、单结果入口、正式/隔离运行服务均不改，暂不PR。

分支`codex/ppt-managed-learning-20261104`，HEAD仍`8988de79bc97d7a7a8a4410fe0f4e91688fecc95`及此前/本轮未提交修改。最终本地兼容候选PPT120/Paper122；旧库、原始失败和评分均保留。服务器运行实例仍为PPT114/Paper116，没有切换源码或重启。

## 根因与实现

本机`LongPathsEnabled=0`。保留失败夹具后定位到实际失败文件：质量证据JSON路径266字符，随后还有更深的认证输入/导出文件。旧错误仅保留160字符，表现成“文件不存在”，不能靠缩短一层测试目录解决。

- `src/adapters/filesystem_paths.py`复用pathlib：仅Windows文件访问使用原生扩展路径，字符串、相对路径、来源引用和证书仍保留正常逻辑路径。未改系统注册表，没有全局替换pathlib，没有创建短目录别名或搬迁旧数据；Linux/Mac仍使用标准Path。
- 学习入口、证据、公共质量记录、候选读取、工作流学习/认证及编译/导出子进程复用这一适配。规范化模块加载路径，避免Windows访问前缀进入模块根目录和源码锁。
- PNG检查改为打开文件流后交给Pillow，避免库内部转回普通长文件名。哈希、内容/来源版本、账户边界、独立决定、硬链接、反馈撤销和失败回退检查均保留。
- 原测试的`node-ppt-learning/<完整UUID>`目录已恢复；不保留上一轮临时缩短目录的做法。新增用例覆盖310字符以上目录中的中文文件、原子替换、目录遍历及拒绝越界/篡改/硬链接；完整闭环明确断言实际认证库路径超过260字符，持久化记录不带Windows访问前缀。
- 新文件加入实现签名和兼容库源码锁。兼容导出保留原MCP schema、读取IR及来源证据，不构成新RSI机制、真实训练或收益晋级。

## 验证与复现

| 环境 | 检查 | 结果 |
| --- | --- | --- |
| Windows，Python3.11.7/Node24.19.0，系统长路径开关未启用 | 原始深目录：单路轨迹→学习→独立认证→后继晋级→重启读取→负反馈停用及完整性检查 | Node 4通过，0失败/跳过 |
| 同一本机 | 长路径、学习证据、用户轨迹准入、工作流/写页发现、共享质量/协议和进程锁 | Python 141通过，0失败/跳过 |
| Linux，Python3.12.15/Node22.23.2 | 相同学习闭环 | Node 4通过 |
| 同一Linux独立副本 | 新路径适配检查 | Python 3通过 |

Windows关键命令（实际`SSS_PYTHON`指向本机解释器）：

```powershell
$env:GENELOOP_PPT_COMPONENT_LEARNING_POLICY=''
$env:GENELOOP_PPT_REVIEW_POLICY=''
node --experimental-strip-types --test tests/test_harless_ppt_learning.mjs
python -m pytest tests/test_filesystem_paths.py tests/test_ppt_learning_evidence.py tests/test_web_ppt_learning.py tests/test_ppt_workflow_learning.py tests/test_ppt_write_learning.py tests/test_rsi_quality.py tests/test_rsi_protocol.py tests/test_file_lock.py -q
```

这是合成冻结轨迹、真实本机文件、已有离线编译器和TypeScript准入的诊断，不是新模型生成PPT、真人质量评审或实际降费实验。没有跑全仓回归；Mac及Windows其他Python版本未做实机验收，UNC仅测试路径格式，没有测试网络共享部署。

Linux使用新建的`ppt-windows-path-regression-20261108`诊断副本，312项同步源码逐SHA核验，不改旧诊断或运行服务。私有原错误、开发中间失败及最终Windows/Linux日志在`.local/ppt-windows-learning-paths-20261108/`。

## 成本、结论与交接

制作、学习、Judge新增云请求均0，原账本仍18921；本轮没有新的真实任务或费用对照。测试的合成训练/留出数据只用于回归，不回灌用户学习库；CPU、开发及人工时间未折价。

**在当前Windows本机和恢复的原始深目录下，学习、独立认证和后继晋级已跑通；Linux相关回归也通过。** 不需要用户开启系统长路径支持。认证/质量条件没有降低，没有手动启用旧停用程序，缺评分仍不代表质量通过。

本次仅修复平台文件访问问题，不宣称全部桌面PPT功能或真实模型收益已验收。前端及单结果模式接线仍由另一对话负责；未来启用新源码时，旧学习能力按原版本规则重新认证，不能直接改旧指针。源码和匹配库成套回退，旧证据和账本不改。
